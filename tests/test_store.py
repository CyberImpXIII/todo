"""The store: ids, parents, one file per id, and the one way to write a store file."""
import ast
import re

from tests.helpers import ROOT, Case, git_repo


class Ids(Case):
    def test_ids_are_never_reused_after_done(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", "bug")
        self.todo("-C", a, "add", "two", "--kind", "bug")
        self.todo("-C", a, "done", "aa-2", "--resolution", "fixed")
        out = self.todo("-C", a, "add", "three", "--kind", "bug").stdout
        self.assertIn("aa-3", out)
        self.todo("-C", a, "done", "aa-2", "--resolution", "again", ok=False)

    def test_an_id_number_at_or_above_next_is_red(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", "bug")
        data = self.store(a)
        data["next"] = 1
        self.write_json(a / "todo.json", data)
        self.assertFails(a, "ids", "could be handed out again")

    def test_a_foreign_prefix_is_red(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", "bug")
        data = self.store(a)
        data["items"][0]["id"] = "zz-1"
        self.write_json(a / "todo.json", data)
        self.assertFails(a, "ids", "id is not aa-N")


class OneFilePerId(Case):
    def test_an_id_in_both_files_is_red_and_done_finishes_the_close(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", "bug")
        self.todo("-C", a, "add", "two", "--kind", "bug")
        self.todo("-C", a, "done", "aa-1", "--resolution", "fixed")
        # simulate a close interrupted between the two writes: history has it, the store still does
        data = self.store(a)
        data["items"].insert(0, dict(self.history(a)["items"][0], status="open", done=None, resolution=None))
        self.write_json(a / "todo.json", data)
        self.todo("-C", a, "render", "--force")
        out = self.assertFails(a, "ids", "id appears in both files")
        self.assertIn("todo done ID", out)
        self.assertIn("finished an interrupted close", self.todo("-C", a, "done", "aa-1", "--resolution", "x").stdout)
        self.check(a)
        self.assertEqual([it["id"] for it in self.store(a)["items"]], ["aa-2"])

    def test_a_done_item_left_in_the_store_is_red(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", "bug")
        data = self.store(a)
        data["items"][0].update(status="done", done="2026-10-04", resolution="x")
        self.write_json(a / "todo.json", data)
        self.assertFails(a, "schema", "closed items live in todo-history.json")


class Parents(Case):
    def test_a_parent_resolves_across_repos_open_or_closed(self):
        a, b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", a, "add", "root", "--kind", "bug")
        self.todo("-C", a, "done", "aa-1", "--resolution", "fixed")
        self.todo("-C", b, "add", "child", "--kind", "note", "--parent", "aa-1")
        self.check(b)
        self.assertIn("[closed 2026-10-04]", self.todo("-C", a, "tree", "aa-1").stdout)

    def plant_parent(self, d, parent):
        data = self.store(d)
        data["items"][0]["parent"] = parent
        self.write_json(d / "todo.json", data)
        self.todo("-C", d, "render", "--force")

    def test_an_unresolved_parent_is_refused_and_red(self):
        a, b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", a, "add", "orphan", "--kind", "note", "--parent", "zz-9", ok=False)
        self.todo("-C", a, "add", "orphan", "--kind", "note")
        # dangling in a store the scan holds: its own, or another scanned one
        for dangling in ("aa-9", "bb-9", "not-an-id"):
            self.plant_parent(a, dangling)
            self.assertFails(a, "parents", f"parent {dangling} resolves in no scanned store")

    def test_a_parent_in_a_store_outside_the_scan_is_unchecked_not_red(self):
        """td-15: a report arriving from another repo carries a parent in that repo's
        store. A check whose scan does not reach that store cannot judge it: a WARN
        saying so, never a FAIL. The same parent, once its store is scanned and holds
        no such item, is red again (the counterfactual)."""
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "arrived", "--kind", "note")
        self.plant_parent(a, "zz-9")
        out = self.check(a).stdout
        warn = [ln for ln in out.splitlines() if ln.split()[:2] == ["WARN", "parents"]]
        self.assertTrue(warn and "unchecked" in warn[0] and "zz" in warn[0], out)
        self.assertNotIn("ok    parents", out)
        z = self.repo("z", "zz")
        self.assertFails(a, "parents", "parent zz-9 resolves in no scanned store")
        self.todo("-C", z, "add", "one", "--kind", "note")
        for n in range(2, 10):
            self.todo("-C", z, "add", f"n{n}", "--kind", "note")
        self.assertIn("ok    parents", self.check(a).stdout)

    def test_an_arrived_report_checks_green_under_a_scan_of_its_own_repo_only(self):
        """The real td-15 path: `todo report` writes the counterpart, then the owner's
        check runs with TODO_ROOT naming only its own repo (dev.sh self's mutant)."""
        a, b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", a, "add", "seen", "--kind", "bug")
        self.todo("-C", a, "report", "aa-1", "--to", "b")
        self.assertEqual(self.store(b)["items"][0]["parent"], "aa-1")
        out = self.todo("-C", b, "check", env={"TODO_ROOT": str(b)}).stdout
        self.assertIn("unchecked", out)
        self.assertNotIn("FAIL", out)

    def test_a_parent_loop_is_red(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", "note")
        self.todo("-C", a, "add", "two", "--kind", "note", "--parent", "aa-1")
        data = self.store(a)
        data["items"][0]["parent"] = "aa-2"
        self.write_json(a / "todo.json", data)
        self.todo("-C", a, "render", "--force")
        self.assertFails(a, "parents", "loops back")


class Workspace(Case):
    def test_a_shared_prefix_is_red(self):
        a = self.repo("a", "aa")
        self.repo("b", "aa")
        self.assertFails(a, "workspace", "prefix aa is also used")

    def test_todo_root_sets_the_scan_root_and_root_beats_it(self):
        a = self.repo("a", "aa")
        self.repo("b", "aa")
        self.assertFails(a, "workspace", "prefix aa is also used")
        alone = {"TODO_ROOT": str(a)}
        out = self.todo("-C", a, "repos", env=alone).stdout
        self.assertIn(f"scan root: {a.resolve()}", out)
        self.assertEqual(len(out.strip().splitlines()), 2, f"a alone, b out of the scan:\n{out}")
        self.assertIn("ok    workspace", self.todo("-C", a, "check", env=alone).stdout)
        out = self.todo("-C", a, "--root", self.ws, "repos", env=alone).stdout
        self.assertIn(f"scan root: {self.ws.resolve()}", out)
        self.assertEqual(len(out.strip().splitlines()), 3, f"a and b:\n{out}")

    def test_the_scan_never_enters_hidden_folders(self):
        a = self.repo("a", "aa")
        d = git_repo(self.ws / ".hidden")
        self.todo("-C", d, "init", "--prefix", "hh", "--repo", "inhidden")  # a hidden name itself is refused
        out = self.todo("-C", a, "repos").stdout
        self.assertNotIn(".hidden", out)
        self.assertNotIn("inhidden", out)


class OneWayIn(Case):
    """Only store.py writes a file; everything else goes through Store.save or write_atomic."""

    WRITERS = re.compile(r"\b(write_text|write_bytes|os\.replace|os\.rename|shutil\.)")

    def test_only_store_py_writes_files(self):
        hits = []
        for f in sorted((ROOT / "todolib").glob("*.py")):
            if f.name == "store.py":
                continue
            src = f.read_text()
            for n, line in enumerate(src.splitlines(), 1):
                if self.WRITERS.search(line):
                    hits.append(f"{f.name}:{n}: {line.strip()}")
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open":
                    hits.append(f"{f.name}:{node.lineno}: open()")
        self.assertEqual(hits, [], "write through Store.save / write_atomic only")
