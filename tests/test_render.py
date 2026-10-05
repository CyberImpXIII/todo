"""Rendered == store: TODO.md is the render of todo.json, written read-only;
a hand edit is red, refused by every mutation, and recoverable."""
import os
import stat

from tests.helpers import Case
from todolib.render import SEAL_RE, seal


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
        self.assertFails(self.a, "render", "edited by hand")

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

    # -- td-10: a render that is merely out of date is stale, never a hand edit ----

    def seal_as_another_format(self):
        """TODO.md as a sealed render of a different render format: what a
        format change leaves in every store that has not re-rendered since."""
        other = self.md.read_text().replace("  · added: ", "  · added on: ")
        self.assertNotEqual(other, self.md.read_text())
        self.edit_md(seal(other))

    def assertStale(self, d):
        out = self.assertFails(d, "render", "stale render")
        self.assertNotIn("by hand", out)

    def test_a_render_of_another_format_is_stale_not_hand_edited(self):
        self.seal_as_another_format()
        self.assertStale(self.a)
        self.assertEqual(self.store(self.a)["hand_edits"], [])

    def test_a_stale_render_is_rewritten_by_render_and_no_hand_edit_is_recorded(self):
        self.seal_as_another_format()
        out = self.todo("-C", self.a, "render").stdout
        self.assertIn("stale", out)
        self.assertEqual(self.store(self.a)["hand_edits"], [])
        self.assertIn("ok    render", self.check(self.a).stdout)
        self.seal_as_another_format()
        self.todo("-C", self.a, "render", "--force")
        self.assertEqual(self.store(self.a)["hand_edits"], [], "--force over a stale render records nothing")

    def test_a_mutation_rewrites_a_stale_render(self):
        self.seal_as_another_format()
        self.todo("-C", self.a, "add", "two", "--kind", "bug")
        self.assertIn("aa-2 · two", self.md.read_text())
        self.assertEqual(self.store(self.a)["hand_edits"], [])
        self.assertIn("ok    render", self.check(self.a).stdout)

    def test_a_render_of_an_older_store_is_stale(self):
        data = self.store(self.a)
        data["items"][0]["title"] = "one, renamed outside the CLI"
        self.write_json(self.a / "todo.json", data)
        self.assertStale(self.a)

    def test_a_stale_render_fails_even_during_the_import_grace(self):
        data = self.store(self.a)
        data["render_gate_from"] = "2099-01-01"
        self.write_json(self.a / "todo.json", data)
        self.seal_as_another_format()
        self.assertStale(self.a)

    def test_the_seal_covers_every_line(self):
        """A hand edit anywhere, the header and the seal included, is a hand edit."""
        clean = self.md.read_text()
        header, rest = clean.split("\n", 1)
        sealed = SEAL_RE.search(header).group(1)
        for edited in (clean + "\n- typed\n",
                       clean.replace("saw y", "saw z"),
                       header.replace("1 open", "2 open") + "\n" + rest,
                       header.replace(sealed, "0" * len(sealed)) + "\n" + rest):
            self.edit_md(edited)
            self.assertFails(self.a, "render", "edited by hand")

    def test_an_unsealed_render_of_the_format_before_seals_is_stale(self):
        clean = self.md.read_text()
        header, rest = clean.split("\n", 1)
        legacy = SEAL_RE.sub("", header) + "\n" + rest
        self.assertNotIn("seal", legacy.split("\n", 1)[0])
        self.edit_md(legacy)
        self.assertStale(self.a)
        self.edit_md(legacy.replace("saw y", "saw z"))
        self.assertFails(self.a, "render", "edited by hand")

    def test_history_render_is_written_and_never_checked(self):
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "fixed")
        self.todo("-C", self.a, "render", "--history")
        hist = (self.a / "TODO-HISTORY.md").read_text()
        self.assertIn("aa-1 · one", hist)
        self.assertIn("· resolution: fixed", hist)
        os.chmod(self.a / "TODO-HISTORY.md", 0o644)
        (self.a / "TODO-HISTORY.md").write_text("anything\n")
        self.check(self.a)
