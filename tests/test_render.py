"""Rendered == store: TODO.md is the render of todo.json, written read-only;
a hand edit is red, refused by every mutation, and recoverable."""
import os
import stat

from tests.helpers import Case


class Render(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "one", "--kind", "bug", "--evidence", "ran x\n\nsaw y")
        self.md = self.a / "TODO.md"

    def edit_md(self, text):
        os.chmod(self.md, 0o644)
        self.md.write_text(text)

    def test_render_is_written_read_only_and_clean(self):
        mode = stat.S_IMODE(os.stat(self.md).st_mode)
        self.assertEqual(mode & 0o222, 0, "TODO.md must be read-only")
        self.assertIn("ok    render", self.check(self.a).stdout)

    def test_a_hand_edit_is_red(self):
        self.edit_md(self.md.read_text() + "\n- a bullet typed by hand\n")
        out = self.check(self.a, ok=False).stdout
        self.assertIn("FAIL  render", out)
        self.assertIn("edited by hand", out)

    def test_a_hand_edit_is_a_warning_during_the_import_grace(self):
        b = self.ws / "b"
        b.mkdir()
        (b / "TODO.md").write_text("# b\n\n## Own bugs\n\n- **x** broke\n")
        self.todo("-C", b, "init", "--prefix", "bb")
        self.todo("-C", b, "import", "TODO.md")
        os.chmod(b / "TODO.md", 0o644)
        (b / "TODO.md").write_text((b / "TODO.md").read_text() + "\n- typed\n")
        self.assertIn("WARN  render", self.check(b).stdout)
        self.assertIn("FAIL  render", self.check(b, ok=False, today="2026-10-11").stdout)

    def test_mutations_refuse_to_overwrite_a_hand_edit(self):
        self.edit_md(self.md.read_text() + "\n- typed\n")
        r = self.todo("-C", self.a, "add", "two", "--kind", "bug", ok=False)
        self.assertIn("edited by hand", r.stderr)
        self.assertIn("- typed", self.md.read_text())

    def test_import_recovers_a_hand_added_bullet(self):
        self.edit_md(self.md.read_text().replace("## Open decisions\n", "## Open decisions\n\n- **typed by hand** why\n"))
        out = self.todo("-C", self.a, "import", "TODO.md").stdout
        self.assertIn("1 new open", out)
        self.check(self.a)
        items = {it["title"]: it for it in self.store(self.a)["items"]}
        self.assertEqual(items["typed by hand"]["kind"], "decision")
        self.assertEqual(len(self.store(self.a)["hand_edits"]), 1)

    def test_import_refuses_a_hand_changed_rendered_item(self):
        self.edit_md(self.md.read_text().replace("saw y", "saw z"))
        r = self.todo("-C", self.a, "import", "TODO.md", ok=False)
        self.assertIn("aa-1", r.stderr)
        self.assertEqual(len(self.store(self.a)["items"]), 1)

    def test_render_force_keeps_the_diff(self):
        self.edit_md(self.md.read_text() + "\n- typed\n")
        self.todo("-C", self.a, "render", ok=False)
        self.todo("-C", self.a, "render", "--force")
        self.assertIn("+- typed", self.store(self.a)["hand_edits"][0]["diff"])
        self.check(self.a)

    def test_render_is_a_function_of_the_store(self):
        before = self.md.read_text()
        self.todo("-C", self.a, "render")
        self.assertEqual(self.md.read_text(), before)
        self.todo("-C", self.a, "edit", "aa-1", "--status", "blocked")
        self.assertIn("· status: blocked", self.md.read_text())

    def test_history_render_is_written_and_never_checked(self):
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "fixed")
        self.todo("-C", self.a, "render", "--history")
        hist = (self.a / "TODO-HISTORY.md").read_text()
        self.assertIn("aa-1 · one", hist)
        self.assertIn("· resolution: fixed", hist)
        os.chmod(self.a / "TODO-HISTORY.md", 0o644)
        (self.a / "TODO-HISTORY.md").write_text("anything\n")
        self.check(self.a)
