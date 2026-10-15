"""`todo brief` writes no brief for an item without done_when: exit 1, nothing on
stdout, and a message naming the item and the field. A dispatch is held to its
brief, so a brief without its done-when must never come out. Any other reason
it is not ready still prints the brief, marked NOT READY."""
from tests.helpers import Case
from todolib.blockers import BRIEF_REFUSES_WITHOUT
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
ALL_BUT_DONE_WHEN = ["--repo", "a", "--work", next(iter(VOCAB.works)), "--size", VOCAB.ready_sizes[0]]


class NoDoneWhen(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "no end named", "--kind", NOTE, *ALL_BUT_DONE_WHEN)

    def test_an_item_without_done_when_gets_no_brief(self):
        r = self.todo("-C", self.a, "brief", "aa-1", ok=False)
        self.assertEqual(r.returncode, 1, "a refusal, README Exit codes")
        self.assertEqual(r.stdout, "", "not a word of the brief")
        self.assertIn("todo:aa-1 has no done_when", r.stderr)
        self.assertIn("todo edit aa-1 --done-when", r.stderr)

    def test_counterfactual_with_done_when_the_same_item_renders(self):
        self.todo("-C", self.a, "edit", "aa-1", "--done-when", "the end is named")
        r = self.todo("-C", self.a, "brief", "aa-1")
        self.assertIn("What: no end named", r.stdout)
        self.assertIn("Done when: the end is named", r.stdout)
        self.assertNotIn("NOT READY", r.stdout)

    def test_another_missing_field_still_prints_the_brief_not_ready(self):
        self.todo("-C", self.a, "add", "no work named", "--kind", NOTE, "--done-when", "it is")
        r = self.todo("-C", self.a, "brief", "aa-2", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("What: no work named", r.stdout)
        self.assertIn("NOT READY:", r.stdout)

    def test_the_field_refused_on_is_one_brief_needs(self):
        from todolib.blockers import BRIEF_NEEDS
        self.assertEqual(BRIEF_REFUSES_WITHOUT, "done_when")
        self.assertIn(BRIEF_REFUSES_WITHOUT, BRIEF_NEEDS)
        self.assertIn(BRIEF_REFUSES_WITHOUT, VOCAB.fields)
