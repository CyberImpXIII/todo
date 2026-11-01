"""`todo rename-repo OLD NEW [--apply]` (PLAN-architecture.md §13.1 step 3): one
store's key and every record naming it, everywhere the scan reaches and in the
current store, with no old spelling left; refused whole when it cannot be right."""
import json
import os
import unittest

from tests.helpers import Case, git_commit, git_repo

NOTE = "note"
REPORT = "report"
# where the fixture names the old key: both renders head with the key, b's report names its owner
FIXTURE_HITS = ["b/TODO.md", "b/todo.json", "oldname/TODO.md", "oldname/todo-history.json", "oldname/todo.json"]


def grep(root, word):
    """Files under root (todo*.json, TODO.md) whose text holds the whole word."""
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for f in filenames:
            if f.startswith("todo") and f.endswith(".json") or f == "TODO.md":
                p = os.path.join(dirpath, f)
                if f'"{word}"' in open(p).read() or f" {word}\n" in open(p).read() or f" {word} " in open(p).read():
                    hits.append(os.path.relpath(p, root))
    return sorted(hits)


class Rename(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("oldname", "on")
        (self.a / "services.json").write_text(json.dumps({"name": "newname"}) + "\n")
        self.b = self.repo("b", "bb")
        self.todo("-C", self.a, "add", "one of its own", "--kind", NOTE)
        self.todo("-C", self.a, "add", "closed one", "--kind", NOTE)
        self.todo("-C", self.a, "done", "on-2", "--resolution", "done")
        self.todo("-C", self.b, "add", "about oldname", "--kind", REPORT, "--reported-to", "oldname")
        self.todo("-C", self.b, "report", "bb-1", "--to", "oldname")

    def test_the_fixture_names_the_old_key_in_both_stores(self):
        self.assertEqual(grep(self.ws, "oldname"), FIXTURE_HITS)

    def test_without_apply_it_says_what_would_change_and_writes_nothing(self):
        before = {p: open(self.ws / p).read() for p in grep(self.ws, "oldname")}
        r = self.todo("-C", self.a, "rename-repo", "oldname", "newname")
        self.assertIn("would rename oldname -> newname in 2 store(s)", r.stdout)
        self.assertIn("oldname (", r.stdout)
        self.assertIn("key, 2 item field(s), 1 history field(s)", r.stdout)
        self.assertIn("b (", r.stdout)
        for p, text in before.items():
            self.assertEqual(open(self.ws / p).read(), text, p)

    def test_apply_rewrites_every_record_and_no_old_spelling_remains(self):
        r = self.todo("-C", self.a, "rename-repo", "oldname", "newname", "--apply")
        self.assertIn("renamed oldname -> newname in 2 store(s)", r.stdout)
        self.assertEqual(grep(self.ws, "oldname"), [])
        self.assertEqual(self.store(self.a)["repo"], "newname")
        self.assertEqual(self.history(self.a)["repo"], "newname")
        self.assertEqual([it["repo"] for it in self.store(self.a)["items"]], ["newname", "newname"])
        self.assertEqual(self.history(self.a)["items"][0]["repo"], "newname")
        self.assertEqual(self.store(self.b)["items"][0]["reported_to"]["repo"], "newname")
        self.assertIn("newname", (self.b / "TODO.md").read_text())
        self.check(self.a)
        self.check(self.b)

    def test_each_written_store_logs_the_verb(self):
        self.todo("-C", self.a, "rename-repo", "oldname", "newname", "--apply")
        for d in (self.a, self.b):
            rows = [json.loads(ln) for ln in (d / "todo-writes.jsonl").read_text().splitlines() if ln.strip()]
            self.assertEqual(rows[-1]["verb"], "rename-repo", d)

    def test_refused_when_the_repos_own_name_is_another(self):
        (self.a / "services.json").write_text(json.dumps({"name": "other"}) + "\n")
        r = self.todo("-C", self.a, "rename-repo", "oldname", "newname", "--apply", ok=False)
        self.assertIn("names this repo 'other'", r.stderr + r.stdout)
        self.assertEqual(self.store(self.a)["repo"], "oldname")

    def test_refused_for_an_unknown_old_or_a_taken_new(self):
        r = self.todo("-C", self.a, "rename-repo", "nobody", "newname", "--apply", ok=False)
        self.assertIn("no store is keyed 'nobody'", r.stderr + r.stdout)
        r = self.todo("-C", self.a, "rename-repo", "oldname", "b", "--apply", ok=False)
        self.assertIn("already has the key 'b'", r.stderr + r.stdout)
        r = self.todo("-C", self.a, "rename-repo", "oldname", ".hidden", "--apply", ok=False)
        self.assertIn("not a repo key", r.stderr + r.stdout)
        self.assertEqual(grep(self.ws, "oldname"), FIXTURE_HITS)

    def test_the_current_store_is_renamed_through_even_when_the_scan_skips_its_folder(self):
        """A store in a hidden folder is outside the scan; run from it (-C), it is the
        current store, so its records naming OLD are rewritten with the rest."""
        h = git_repo(self.ws / ".layer")
        self.todo("-C", h, "init", "--prefix", "hh", "--repo", "layer")
        self.todo("-C", h, "add", "names it", "--kind", NOTE, "--repo", "oldname")
        self.assertIn(".layer/todo.json", grep(self.ws, "oldname"))
        r = self.todo("-C", h, "rename-repo", "oldname", "newname", "--apply")
        self.assertIn("in 3 store(s)", r.stdout)
        self.assertEqual(grep(self.ws, "oldname"), [])
        self.assertEqual(self.store(h)["items"][0]["repo"], "newname")

    def test_a_committed_history_passes_check_after_the_rename_and_a_hand_edit_still_fails(self):
        """The history gate admits exactly one change since a commit: a key rename the
        write log recorded. Anything else in a history entry still fails it."""
        git_commit(self.a, "before the rename")
        self.todo("-C", self.a, "rename-repo", "oldname", "newname", "--apply")
        out = self.check(self.a).stdout
        self.assertIn("1 history entr(ies) differ from a committed version only by a key rename the write log recorded (oldname -> newname)", out)
        hist = self.history(self.a)
        hist["items"][0]["title"] = "closed one, reworded by hand"
        self.write_json(self.a / "todo-history.json", hist)
        self.assertFails(self.a, "history", "never edited")

    def test_an_ordinary_write_logs_no_rename(self):
        rows = [json.loads(ln) for ln in (self.a / "todo-writes.jsonl").read_text().splitlines() if ln.strip()]
        self.assertTrue(rows and all("rename" in r and r["rename"] is None for r in rows))


class FieldsOnly(Case):
    """No store is keyed OLD: the rename is of fields alone (PLAN-architecture.md §13.1
    G3), and needs the names file so that NEW is a location's name."""

    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")
        self.names = self.ws / "names.json"
        self.names.write_text(json.dumps({"locations": [
            {"name": "a", "dir": "a", "store": "a", "remote": None, "agent": "a"},
            {"name": "b", "dir": "b", "store": "b", "remote": None, "agent": "b"},
            {"name": "zeta", "dir": "tools/zeta", "store": None, "remote": None, "agent": "zeta"}]}) + "\n")
        self.todo("-C", self.a, "add", "keyed by a path", "--kind", NOTE, "--repo", "tools/zeta")
        self.todo("-C", self.b, "add", "about it", "--kind", REPORT, "--reported-to", "tools/zeta")
        self.todo("-C", self.a, "add", "closed one", "--kind", NOTE, "--repo", "tools/zeta")
        self.todo("-C", self.a, "done", "aa-2", "--resolution", "done")

    def test_with_the_names_file_the_fields_are_renamed_across_stores_and_history(self):
        r = self.todo("-C", self.a, "--names", self.names, "rename-repo", "tools/zeta", "zeta", "--apply")
        self.assertIn("renamed tools/zeta -> zeta in 2 store(s)", r.stdout)
        self.assertEqual(self.store(self.a)["items"][0]["repo"], "zeta")
        self.assertEqual(self.history(self.a)["items"][0]["repo"], "zeta")
        self.assertEqual(self.store(self.b)["items"][0]["reported_to"]["repo"], "zeta")
        self.assertEqual(self.store(self.a)["repo"], "a", "no store was keyed tools/zeta, so no key changed")
        self.assertEqual(grep(self.ws, "tools/zeta"), [])
        rows = [json.loads(ln) for ln in (self.a / "todo-writes.jsonl").read_text().splitlines() if ln.strip()]
        self.assertEqual(rows[-1]["rename"], {"old": "tools/zeta", "new": "zeta"})

    def test_without_the_names_file_a_fields_only_rename_is_refused_saying_why(self):
        r = self.todo("-C", self.a, "rename-repo", "tools/zeta", "zeta", "--apply", ok=False)
        self.assertIn("no store is keyed 'tools/zeta': a rename of fields alone needs the names file", r.stderr)
        self.assertEqual(self.store(self.a)["items"][0]["repo"], "tools/zeta")

    def test_new_must_be_a_location_and_old_must_be_named_somewhere(self):
        r = self.todo("-C", self.a, "--names", self.names, "rename-repo", "tools/zeta", "nowhere", "--apply", ok=False)
        self.assertIn("NEW 'nowhere': 'nowhere' is no location", r.stderr)
        r = self.todo("-C", self.a, "--names", self.names, "rename-repo", "nobody", "zeta", "--apply", ok=False)
        self.assertIn("nothing names 'nobody'", r.stderr)
        self.assertEqual(self.store(self.a)["items"][0]["repo"], "tools/zeta")


if __name__ == "__main__":
    unittest.main()
