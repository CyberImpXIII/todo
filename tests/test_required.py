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


class ImportResolution(Case):
    """td-1: an imported closed bullet gets done-deprecated; a closed item without a
    resolution is red wherever it came from; the value is the import's alone."""

    def setUp(self):
        super().setUp()
        self.deprecated = VOCAB.role("import_resolution")
        self.b = self.ws / "b"
        self.b.mkdir()  # no git: the append-only audit is skipped, so a rewrite below is seen by its own gate only
        (self.b / "TODO.md").write_text("# b\n\n## Own bugs\n\n- DONE 2026-10-01: fixed the thing\n\n## Resolved\n\n- an undated one\n")
        self.todo("-C", self.b, "init", "--prefix", "bb")
        self.todo("-C", self.b, "import", "TODO.md")

    def set_resolution(self, d, value, index=0):
        h = self.history(d)
        h["items"][index]["resolution"] = value
        self.write_json(d / "todo-history.json", h)

    def test_imported_closed_items_are_green_with_it(self):
        self.assertEqual([it["resolution"] for it in self.history(self.b)["items"]], [self.deprecated] * 2)
        out = self.check(self.b).stdout
        self.assertIn("ok    required", out)
        self.assertIn("ok    vocab", out)

    def test_an_imported_closed_item_without_a_resolution_is_red(self):
        self.set_resolution(self.b, None, index=1)  # the undated one: its date stays exempt, its resolution does not
        self.assertFails(self.b, "required", "requires resolution")

    def test_the_value_on_an_item_not_imported_is_red(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "x", "--kind", "bug")
        self.todo("-C", a, "done", "aa-1", "--resolution", "fixed")
        self.check(a)
        self.set_resolution(a, self.deprecated)
        self.assertFails(a, "vocab", f"resolution {self.deprecated!r} is set by todo import only")

    def test_done_refuses_the_value(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "x", "--kind", "bug")
        for value in (self.deprecated, f" {self.deprecated} "):
            with self.subTest(value=value):
                r = self.todo("-C", a, "done", "aa-1", "--resolution", value, ok=False)
                self.assertIn("set by todo import only", r.stderr)
        self.assertEqual(self.history(a)["items"], [])
        self.todo("-C", a, "done", "aa-1", "--resolution", "fixed")
        self.assertEqual(self.history(a)["items"][0]["resolution"], "fixed")
