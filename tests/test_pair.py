"""`todo pair [--apply]` (external audit ra-21.1): the owner of a store the scan never
enters pulls the reports addressed to its key, from its own folder, and pairs them
on both sides; todo still never enters the folder on its own."""
import unittest

from tests.helpers import Case, git_repo

NOTE = "note"
REPORT = "report"


class Pair(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.h = git_repo(self.ws / ".layer")
        self.todo("-C", self.h, "init", "--prefix", "hh", "--repo", "layer")
        self.todo("-C", self.a, "add", "the layer drops a row", "--kind", REPORT, "--reported-to", "layer", "--evidence", "seen twice")
        r = self.todo("-C", self.a, "report", "aa-1", "--to", "layer")
        self.assertIn("no store for layer in the scan", r.stdout)
        self.todo("-C", self.a, "add", "for someone else", "--kind", REPORT, "--reported-to", "other")

    def test_the_reporter_sees_it_unpaired_and_the_scan_never_enters_the_folder(self):
        out = self.check(self.a).stdout
        self.assertIn("unpaired: no store for repo 'layer'", out)
        self.assertNotIn(".layer", self.todo("-C", self.a, "repos").stdout)

    def test_without_apply_it_lists_what_would_pair_and_writes_nothing(self):
        r = self.todo("-C", self.h, "pair")
        self.assertIn("a:aa-1", r.stdout)
        self.assertIn("would pair 1 report(s) into layer", r.stdout)
        self.assertEqual(self.store(self.h)["items"], [])
        self.assertIsNone(self.store(self.a)["items"][0]["reported_to"]["their_id"])

    def test_apply_writes_the_counterpart_here_and_pairs_both_sides(self):
        r = self.todo("-C", self.h, "pair", "--apply")
        self.assertIn("paired a:aa-1 -> hh-1", r.stdout)
        mine = self.store(self.h)["items"]
        self.assertEqual([(it["id"], it["parent"], it["kind"], it["title"], it["evidence"]) for it in mine],
                         [("hh-1", "aa-1", NOTE, "the layer drops a row", "seen twice")])
        theirs = self.store(self.a)["items"]
        self.assertEqual(theirs[0]["reported_to"]["their_id"], "hh-1")
        self.assertIsNone(theirs[1]["reported_to"]["their_id"], "a report to another key is not touched")
        self.assertNotIn("unpaired: no store for repo 'layer'", self.check(self.a).stdout)
        self.check(self.h)
        self.assertIn("as hh-1", (self.a / "TODO.md").read_text())

    def test_a_second_pull_finds_nothing_and_an_existing_counterpart_is_reused(self):
        self.todo("-C", self.h, "pair", "--apply")
        r = self.todo("-C", self.h, "pair", "--apply")
        self.assertIn("no open report addressed to layer waits for a counterpart", r.stdout)
        # a counterpart already here (parent set by hand through the CLI) is paired with, not duplicated
        self.todo("-C", self.a, "add", "another one", "--kind", REPORT, "--reported-to", "layer")
        self.todo("-C", self.a, "report", "aa-3", "--to", "layer")
        self.todo("-C", self.h, "add", "already filed here", "--kind", NOTE, "--parent", "aa-3")
        r = self.todo("-C", self.h, "pair", "--apply")
        self.assertIn("paired a:aa-3 -> hh-2", r.stdout)
        self.assertEqual(len(self.store(self.h)["items"]), 2)
        self.assertEqual(self.store(self.a)["items"][2]["reported_to"]["their_id"], "hh-2")

    def test_each_written_store_logs_the_verb(self):
        self.todo("-C", self.h, "pair", "--apply")
        import json
        for d in (self.a, self.h):
            rows = [json.loads(ln) for ln in (d / "todo-writes.jsonl").read_text().splitlines() if ln.strip()]
            self.assertEqual(rows[-1]["verb"], "pair", d)


if __name__ == "__main__":
    unittest.main()
