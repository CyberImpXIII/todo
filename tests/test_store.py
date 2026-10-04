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

    def test_an_unresolved_parent_is_refused_and_red(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "orphan", "--kind", "note", "--parent", "zz-9", ok=False)
        self.todo("-C", a, "add", "orphan", "--kind", "note")
        data = self.store(a)
        data["items"][0]["parent"] = "zz-9"
        self.write_json(a / "todo.json", data)
        self.todo("-C", a, "render", "--force")
        self.assertFails(a, "parents", "parent zz-9 resolves in no scanned store")

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
