"""`todo rename-repo OLD NEW [--apply]` (PLAN-architecture.md §13.1 step 3): one
store's key and every record naming it, everywhere the scan reaches and in the
current store, with no old spelling left; refused whole when it cannot be right."""
import json
import os
import unittest

from tests.helpers import Case, git_repo

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
        self.assertIn("0 store(s) have the key 'nobody'", r.stderr + r.stdout)
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


if __name__ == "__main__":
    unittest.main()
