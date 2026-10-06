"""todo edit --append-evidence (td-19): adds to the evidence inside the store's
lock, so a caller never reads, changes and rewrites it itself."""
from tests.helpers import Case


class AppendEvidence(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("alpha", "aa")
        self.todo("-C", self.a, "add", "x", "--kind", "note", "--evidence", "ran X, saw Y")

    def evidence(self):
        return self.store(self.a)["items"][0]["evidence"]

    def test_append_keeps_the_old_text_and_adds_a_line(self):
        self.todo("-C", self.a, "edit", "aa-1", "--append-evidence", "2026-10-06: ran Z, saw W")
        self.assertEqual(self.evidence(), "ran X, saw Y\n2026-10-06: ran Z, saw W")
        self.todo("-C", self.a, "edit", "aa-1", "--append-evidence", "third")
        self.assertEqual(self.evidence(), "ran X, saw Y\n2026-10-06: ran Z, saw W\nthird")
        md = (self.a / "TODO.md").read_text()
        self.assertIn("  ran X, saw Y\n  2026-10-06: ran Z, saw W\n  third\n", md)
        self.check(self.a)

    def test_append_to_an_item_without_evidence_sets_it(self):
        self.todo("-C", self.a, "add", "y", "--kind", "note")
        self.todo("-C", self.a, "edit", "aa-2", "--append-evidence", "first words")
        self.assertEqual(self.store(self.a)["items"][1]["evidence"], "first words")

    def test_append_with_evidence_or_with_nothing_is_refused_and_changes_nothing(self):
        r = self.todo("-C", self.a, "edit", "aa-1", "--evidence", "new", "--append-evidence", "more", ok=False)
        self.assertIn("give one", r.stderr)
        r = self.todo("-C", self.a, "edit", "aa-1", "--append-evidence", "  ", ok=False)
        self.assertIn("nothing to add", r.stderr)
        self.assertEqual(self.evidence(), "ran X, saw Y")
