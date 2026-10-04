"""Required fields by kind and status: refused at add/edit/done, red in check
for imported items (PLAN §5)."""
from tests.helpers import Case
from todolib.vocab import VOCAB


def needing(field):
    return [k for k, spec in VOCAB.kinds.items() if field in spec["requires"]]


class Required(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")

    def test_add_refuses_each_kind_without_its_required_field(self):
        for kind, spec in VOCAB.kinds.items():
            for field in spec["requires"]:
                if field == "reported_to":
                    continue  # set by `todo report`, never by a flag: covered below
                r = self.todo("-C", self.a, "add", "x", "--kind", kind, ok=False)
                self.assertIn("--" + field.replace("_", "-"), r.stderr, kind)
        self.assertEqual(self.store(self.a)["items"], [])

    def test_a_report_is_made_only_by_todo_report(self):
        for kind in needing("reported_to"):
            r = self.todo("-C", self.a, "add", "x", "--kind", kind, ok=False)
            self.assertIn("--reported-to", r.stderr)

    def test_edit_cannot_drop_a_required_field(self):
        self.todo("-C", self.a, "add", "x", "--kind", needing("probe")[0], "--probe", "run it")
        self.todo("-C", self.a, "edit", "aa-1", "--probe", "", ok=False)
        self.assertEqual(self.store(self.a)["items"][0]["probe"], "run it")

    def test_done_refuses_an_empty_resolution(self):
        self.todo("-C", self.a, "add", "x", "--kind", "bug")
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "", ok=False)
        self.assertEqual(self.history(self.a)["items"], [])

    def test_edit_cannot_close(self):
        self.todo("-C", self.a, "add", "x", "--kind", "bug")
        self.todo("-C", self.a, "edit", "aa-1", "--status", VOCAB.closed, ok=False)

    def test_imported_items_missing_a_required_field_are_red(self):
        b = self.ws / "b"
        b.mkdir()
        (b / "TODO.md").write_text("# b\n\n## Unconfirmed suspicions\n\n- **maybe x** no probe written\n")
        self.todo("-C", b, "init", "--prefix", "bb")
        out = self.todo("-C", b, "import", "TODO.md").stdout
        self.assertIn("1 lack a field", out)
        self.assertFails(b, "required", "requires probe")
        self.todo("-C", b, "edit", "bb-1", "--probe", "run y")
        self.check(b)
