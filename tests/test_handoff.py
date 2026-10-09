"""Handoffs that survive a usage limit (PLAN-small-tasks.md §4.1, §4.3) and the
stop rule every brief carries (§2.3): `todo edit ID --handoff` records the note
with the date and the work repo's commit at that moment (the checkpoint), and
`todo brief` prints both, so a later or cloud dispatch resumes there."""
import re
import unittest

from tests.helpers import ROOT, TODAY, Case, git, git_commit, workspace_file
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
READY = ["--work", next(iter(VOCAB.works)), "--done-when", "dw", "--size", VOCAB.ready_sizes[0]]
SMALL_TASKS_PLAN = workspace_file("PLAN-small-tasks.md")
TEXT = "done: the parser; next: its tests; verify: ./dev.sh check"


def head(d):
    return git(d, "rev-parse", "--short", "HEAD").strip()


class Handoff(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "job", "--kind", NOTE, *READY)
        (self.a / "work.txt").write_text("step one\n")
        git_commit(self.a, "checkpoint one")

    def test_edit_records_the_note_its_date_and_the_checkpoint_commit(self):
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", TEXT)
        self.assertEqual(self.store(self.a)["items"][0]["handoff"],
                         {"date": TODAY, "text": TEXT, "commit": head(self.a)})

    def test_brief_carries_the_handoff_and_the_commit_it_was_made_at(self):
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", TEXT)
        sha = head(self.a)
        (self.a / "work.txt").write_text("step two, after the handoff\n")
        git_commit(self.a, "later work")
        out = self.todo("-C", self.a, "brief", "aa-1").stdout
        self.assertIn(f"Handoff ({TODAY}, at {sha} checkpoint one): {TEXT}", out)
        self.assertIn(f"HEAD is now {head(self.a)} later work: commits after the handoff are not in its note", out)

    def test_a_brief_at_the_handoffs_own_commit_warns_of_nothing(self):
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", TEXT)
        out = self.todo("-C", self.a, "brief", "aa-1").stdout
        self.assertIn(f"Handoff ({TODAY}, at {head(self.a)} checkpoint one): {TEXT}", out)
        self.assertNotIn("HEAD is now", out)

    def test_the_render_and_show_carry_it(self):
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", TEXT)
        line = f"handoff: {TEXT} ({TODAY}, at {head(self.a)})"
        self.assertIn("· " + line, (self.a / "TODO.md").read_text())
        self.assertIn(line, self.todo("-C", self.a, "show", "aa-1").stdout)

    def test_a_new_handoff_replaces_the_last_and_an_empty_one_clears_it(self):
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", "first")
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", "second")
        self.assertEqual(self.store(self.a)["items"][0]["handoff"]["text"], "second")
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", "")
        self.assertIsNone(self.store(self.a)["items"][0]["handoff"])
        self.assertIn("Handoff: none yet", self.todo("-C", self.a, "brief", "aa-1").stdout)
        self.todo("-C", self.a, "edit", "aa-1", "--handoff", "two\nlines", ok=False)

    def test_the_commit_is_the_work_repos_and_null_when_it_cannot_be_found(self):
        b = self.repo("b", "bb")
        (b / "theirs.txt").write_text("x\n")
        git_commit(b, "their checkpoint")
        self.todo("-C", self.a, "add", "theirs", "--kind", NOTE, "--repo", "b", *READY)
        self.todo("-C", self.a, "edit", "aa-2", "--handoff", TEXT)
        self.assertEqual(self.store(self.a)["items"][1]["handoff"]["commit"], head(b))
        self.todo("-C", self.a, "add", "nowhere", "--kind", NOTE, "--repo", "unscanned", *READY)
        self.todo("-C", self.a, "edit", "aa-3", "--handoff", TEXT)
        self.assertIsNone(self.store(self.a)["items"][2]["handoff"]["commit"])
        self.assertIn("no checkpoint commit recorded", self.todo("-C", self.a, "brief", "aa-3").stdout)

    def test_check_fails_a_malformed_handoff(self):
        data = self.store(self.a)
        for bad in ("just text", {"date": "today", "text": "n", "commit": None},
                    {"date": TODAY, "text": "", "commit": None}, {"date": TODAY, "text": "n", "commit": "not a sha"}):
            with self.subTest(handoff=bad):
                data["items"][0]["handoff"] = bad
                self.write_json(self.a / "todo.json", data)
                self.assertFails(self.a, "schema", "handoff must be")
                self.assertIn("Handoff", self.todo("-C", self.a, "brief", "aa-1").stdout)


class StopRule(Case):
    def test_every_brief_carries_the_stop_rule_and_how_to_hand_off(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "ready", "--kind", NOTE, *READY)
        self.todo("-C", a, "add", "not ready", "--kind", NOTE)
        for iid, ok in (("aa-1", True), ("aa-2", False)):
            with self.subTest(id=iid):
                out = self.todo("-C", a, "brief", iid, ok=ok).stdout
                self.assertIn(f"Stop rule: {VOCAB.brief['stop_rule']}", out)
                self.assertIn("Do not start the suite a third time.", out)
                self.assertIn(f"edit {iid} --handoff", out)

    def test_the_readme_quotes_the_rule_vocab_json_carries(self):
        readme = " ".join((ROOT / "README.md").read_text().split())
        self.assertIn(f'"{VOCAB.brief["stop_rule"]}"', readme)

    @unittest.skipUnless(SMALL_TASKS_PLAN, "the plan lives in the workspace, not in a fresh clone")
    def test_the_stop_rule_is_the_plans_words(self):
        """PLAN-small-tasks.md §2.3 quotes the rule; vocab.json carries it verbatim."""
        section = SMALL_TASKS_PLAN.read_text().split("**The brief carries a stop rule.**", 1)[1].split("\n4.", 1)[0]
        quoted = " ".join(re.search(r'"(.*?)"', section, re.S).group(1).split())
        self.assertEqual(VOCAB.brief["stop_rule"], quoted)
