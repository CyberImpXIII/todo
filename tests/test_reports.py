"""Reports in pairs: a reported_to has its counterpart in the owner's store or
history, the counterpart's parent points back, and check names every gap."""
from tests.helpers import Case
from todolib.vocab import VOCAB


class Reports(Case):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", self.a, "add", "their bug", "--kind", "bug", "--evidence", "ran x, saw y")

    def test_report_creates_the_counterpart_with_parent_pointing_back(self):
        out = self.todo("-C", self.a, "report", "aa-1", "--to", "b").stdout
        self.assertIn("as bb-1", out)
        mine = self.store(self.a)["items"][0]
        self.assertEqual(mine["kind"], VOCAB.role("report_kind"))
        self.assertEqual(mine["reported_to"], {"repo": "b", "date": "2026-10-04", "their_id": "bb-1"})
        theirs = self.store(self.b)["items"][0]
        self.assertEqual((theirs["parent"], theirs["kind"], theirs["evidence"]), ("aa-1", "bug", "ran x, saw y"))
        self.check(self.a)
        out = self.check(self.b).stdout
        self.assertIn("still open here: bb-1", out)

    def test_pairing_finds_a_counterpart_the_owner_already_closed(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "b")
        self.todo("-C", self.b, "done", "bb-1", "--resolution", "fixed in b")
        out = self.check(self.a).stdout
        self.assertIn("counterpart bb-1 closed 2026-10-04: fixed in b", out)
        self.assertNotIn("FAIL", out)

    def test_reporting_again_pairs_with_the_existing_counterpart_even_closed(self):
        self.todo("-C", self.b, "add", "already filed", "--kind", "bug", "--parent", "aa-1")
        self.todo("-C", self.b, "done", "bb-1", "--resolution", "fixed before we asked")
        out = self.todo("-C", self.a, "report", "aa-1", "--to", "b").stdout
        self.assertIn("already holds bb-1", out)
        self.assertEqual(self.store(self.b)["items"], [])
        self.assertEqual(self.store(self.a)["items"][0]["reported_to"]["their_id"], "bb-1")

    def test_report_to_a_repo_without_a_store_is_a_warning_until_it_has_one(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "c")
        out = self.check(self.a).stdout
        self.assertIn("WARN  reports", out)
        self.assertIn("unpaired", out)
        self.repo("c", "cc")
        self.assertFails(self.a, "reports", "has a store now")
        self.assertIn("as cc-1", self.todo("-C", self.a, "report", "aa-1", "--to", "c").stdout)
        self.check(self.a)

    def test_a_missing_counterpart_is_red(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "b")
        data = self.store(self.b)
        data["items"] = []
        self.write_json(self.b / "todo.json", data)
        self.assertFails(self.a, "reports", "counterpart bb-1 is in neither")

    def test_a_counterpart_whose_parent_does_not_point_back_is_red(self):
        self.todo("-C", self.a, "add", "other", "--kind", "note")
        self.todo("-C", self.a, "report", "aa-1", "--to", "b")
        data = self.store(self.b)
        data["items"][0]["parent"] = "aa-2"
        self.write_json(self.b / "todo.json", data)
        self.assertFails(self.a, "reports", "has parent aa-2, not aa-1")

    def test_report_to_its_own_repo_is_refused(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "a", ok=False)
