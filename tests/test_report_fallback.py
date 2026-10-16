"""A report to a repo with no store (PLAN-architecture.md §11 S4): when the scan
finds a git repo of that name without a todo.json, `todo report` files one bullet
in its hand-written TODO.md, marked todo:<id>, once; the item's evidence says so,
and their_id stays null until the repo has a store."""
import json

from tests.helpers import ROOT, Case, git_repo
from todolib import store as storelib
from todolib.vocab import VOCAB, Vocab

HEADING = "## " + VOCAB.fallback_heading


class Fallback(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "their bug", "--kind", VOCAB.role("default_kind"),
                  "--evidence", "ran x\nsaw y", "--done-when", "x passes")
        self.c = git_repo(self.ws / "c")

    def report(self, **kw):
        return self.todo("-C", self.a, "report", "aa-1", "--to", "c", **kw)

    def test_the_bullet_is_filed_once_and_the_evidence_says_so(self):
        (self.c / "TODO.md").write_text("# c\n\n## Own bugs\n\n- one\n")
        out = self.report().stdout
        self.assertIn("a bullet marked todo:aa-1 was added", out)
        self.assertIn("Commit it there", out)
        text = (self.c / "TODO.md").read_text()
        self.assertTrue(text.startswith("# c\n\n## Own bugs\n\n- one\n\n" + HEADING + "\n\n- todo:aa-1 from a "), text)
        self.assertIn("  evidence: ran x\n  saw y\n  done when: x passes\n", text)
        item = self.store(self.a)["items"][0]
        self.assertEqual(item["reported_to"]["their_id"], None)
        self.assertIn("as a bullet marked todo:aa-1", item["evidence"])
        out = self.report().stdout
        self.assertIn("names todo:aa-1 already: nothing added", out)
        self.assertEqual((self.c / "TODO.md").read_text(), text)
        self.assertEqual(self.store(self.a)["items"][0]["evidence"], item["evidence"])

    def test_a_second_report_joins_the_section_before_the_next_heading(self):
        (self.c / "TODO.md").write_text(f"# c\n\n{HEADING}\n\n- todo:zz-9 earlier\n\n## Notes\n\n- n\n")
        self.report()
        text = (self.c / "TODO.md").read_text()
        head, rest = text.split("## Notes", 1)
        self.assertIn("- todo:zz-9 earlier\n- todo:aa-1 from a", head)
        self.assertTrue(head.endswith(")\n\n"), head)
        self.assertEqual(rest, "\n\n- n\n")

    def test_no_file_yet_is_made(self):
        self.report()
        self.assertTrue((self.c / "TODO.md").read_text().startswith(HEADING + "\n\n- todo:aa-1 "))

    def test_a_longer_id_is_not_this_one(self):
        (self.c / "TODO.md").write_text("- todo:aa-10 another\n")
        self.assertIn("was added", self.report().stdout)
        self.assertFalse(storelib.marker_in("- todo:aa-10 x", "todo:aa-1"))
        self.assertTrue(storelib.marker_in("- todo:aa-1 x", "todo:aa-1"))

    def test_nothing_is_written_without_a_git_repo_or_when_the_name_is_ambiguous(self):
        self.todo("-C", self.a, "add", "second", "--kind", VOCAB.role("default_kind"))
        out = self.todo("-C", self.a, "report", "aa-2", "--to", "d").stdout  # no folder d at all
        self.assertIn("no counterpart yet", out)
        (self.ws / "e").mkdir()  # a folder, not a git repo
        self.todo("-C", self.a, "add", "third", "--kind", VOCAB.role("default_kind"))
        self.assertIn("no counterpart yet", self.todo("-C", self.a, "report", "aa-3", "--to", "e").stdout)
        self.assertFalse((self.ws / "e" / "TODO.md").exists())
        git_repo(self.ws / "x" / "c")
        out = self.report().stdout
        self.assertIn("2 repos are named c", out)
        self.assertFalse((self.c / "TODO.md").exists())
        self.assertFalse((self.ws / "x" / "c" / "TODO.md").exists())

    def test_vocab_refuses_a_nested_file_or_a_broken_heading(self):
        raw = json.loads((ROOT / "vocab.json").read_text())
        for block in ({"file": "docs/TODO.md", "heading": "h"}, {"file": "TODO.md", "heading": ""},
                      {"file": "TODO.md", "heading": "a\nb"}):
            with self.subTest(block):
                path = self.tmp / "vocab.json"
                path.write_text(json.dumps(dict(raw, report_fallback=block)))
                with self.assertRaises(ValueError):
                    Vocab(path)
