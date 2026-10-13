"""Handoffs that survive a usage limit (PLAN-small-tasks.md §4.1, §4.3) and the
stop rule and iterate rule every brief carries (§2.3, §3.5): `todo edit ID --handoff` records the note
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
# The shared suite runner (PLAN-small-tasks.md §7) and the one dev.sh that hands
# its parts to it today; None in a fresh clone.
RUNNER = workspace_file("tools/checks/checkslib/parts.py")
RUNNER_DEV = workspace_file("tools/checks/dev.sh")
# The runner's `run` usage line the iterate rule was worded against (parts.py
# 1.0.0). IterateRule holds it equal to the runner's own when the runner is here.
RUNNER_RUN_USAGE = "parts.py run <parts.json> [--resume] [--json]"
COMMAND_HEADS = ("./dev.sh", "dev.sh", "check")


def run_flags(text):
    """The flags of the `parts.py run <parts.json> [...]` usage line in text, or None."""
    m = re.search(r"^\s*parts\.py run <parts\.json>((?: \[--[a-z-]+\])*)\s*$", text, re.M)
    return None if m is None else re.findall(r"--[a-z-]+", m.group(1))


def command_faults(command, flags):
    """Why a dev.sh command is not one the runner runs, or []. dev.sh reaches the
    runner only as `./dev.sh check`, whose arguments go to `parts.py run`."""
    words = command.split()
    if words[:1] == ["check"]:
        words = ["./dev.sh"] + words
    if words[:1] == ["dev.sh"]:
        words[0] = "./dev.sh"
    if words[:2] != ["./dev.sh", "check"]:
        return [f"`{command}` is not `./dev.sh check`, the runner's one way in from dev.sh"]
    return [f"`{command}`: {w} is not a flag of `parts.py run`" for w in words[2:] if w not in flags]


def rule_faults(rule, flags):
    """Every backticked dev.sh command in the rule, held to the runner's flags."""
    if flags is None:
        return ["no `parts.py run <parts.json> [...]` usage line to hold the rule to"]
    cmds = [c for c in re.findall(r"`([^`]+)`", rule) if c.split()[:1] and c.split()[0] in COMMAND_HEADS]
    if not cmds:
        return ["the rule names no dev.sh command"]
    return [f for c in cmds for f in command_faults(c, flags)]


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


class IterateRule(Case):
    """PLAN-small-tasks.md §3.5, worded to the runner's real commands (vocab.json
    brief.iterate_rule): a renamed command on either side turns this red."""
    RULE = VOCAB.brief["iterate_rule"]

    def test_every_brief_carries_the_iterate_rule(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "ready", "--kind", NOTE, *READY)
        self.todo("-C", a, "add", "not ready", "--kind", NOTE)
        for iid, ok in (("aa-1", True), ("aa-2", False)):
            with self.subTest(id=iid):
                out = self.todo("-C", a, "brief", iid, ok=ok).stdout
                self.assertIn(f"Iterate rule: {self.RULE}", out)
                self.assertIn("`./dev.sh check --resume`", out)
                self.assertIn("Run the full suite once, before the commit", out)

    def test_the_rules_commands_are_the_pinned_runners(self):
        flags = run_flags(RUNNER_RUN_USAGE)
        self.assertEqual(flags, ["--resume", "--json"])
        self.assertEqual(rule_faults(self.RULE, flags), [])

    def test_a_renamed_command_on_either_side_fails(self):
        flags = run_flags(RUNNER_RUN_USAGE)
        for old, new in (("--resume`", "--quick`"), ("`./dev.sh check --resume`", "`./dev.sh test <part>`"),
                         ("`./dev.sh check`", "`./dev.sh verify`")):
            with self.subTest(rule=new):
                self.assertIn(old, self.RULE)
                self.assertTrue(rule_faults(self.RULE.replace(old, new), flags))
        with self.subTest(runner="--resume renamed --since"):
            self.assertTrue(rule_faults(self.RULE, run_flags(RUNNER_RUN_USAGE.replace("--resume", "--since"))))
        with self.subTest(runner="no run usage line"):
            self.assertIsNone(run_flags("parts.py check <parts.json> [--resume]"))
            self.assertTrue(rule_faults(self.RULE, None))
        with self.subTest(rule="no command at all"):
            self.assertTrue(rule_faults("Iterate small.", flags))

    def test_the_readme_quotes_the_rule_vocab_json_carries(self):
        readme = " ".join((ROOT / "README.md").read_text().split())
        self.assertIn(f'"{self.RULE}"', readme)

    @unittest.skipUnless(RUNNER and RUNNER_DEV, "the runner lives in tools/checks, not in a fresh clone")
    def test_the_pin_is_the_runners_usage_and_dev_sh_hands_it_its_arguments(self):
        """parts.py's own usage carries the pinned line, its argument check accepts
        exactly those flags, and the reference dev.sh passes `check`'s arguments on."""
        runner = RUNNER.read_text()
        self.assertEqual(run_flags(runner), run_flags(RUNNER_RUN_USAGE), f"{RUNNER}: reword the iterate rule")
        accepted = re.search(r'bad = \[a for a in flags if a not in \(([^)]*)\)\]', runner)
        self.assertIsNotNone(accepted, f"{RUNNER}: cmd_run's flag check moved; re-read it")
        self.assertEqual(sorted(re.findall(r'"(--[a-z-]+)"', accepted.group(1))), sorted(run_flags(RUNNER_RUN_USAGE)))
        self.assertRegex(RUNNER_DEV.read_text(), r'cmd_check\(\) \{ exec python3 [^\n]*parts\.py" run [^\n]*"\$@"; \}')

    @unittest.skipUnless(SMALL_TASKS_PLAN, "the plan lives in the workspace, not in a fresh clone")
    def test_the_rule_is_the_plans_and_names_its_sketch_as_absent(self):
        """§3.5's lead and its 'full suite once, before the commit' are the rule's;
        each command §3.5 sketches is named in the rule and is not one the runner has."""
        lead = "Iterate small, then run whole once."
        section = SMALL_TASKS_PLAN.read_text().split(f"**{lead}**", 1)[1].split("\n6.", 1)[0]
        section = " ".join(section.split())
        self.assertTrue(self.RULE.startswith(lead))
        self.assertIn("runs the full suite once, before the commit", section)
        self.assertIn("Run the full suite once, before the commit", self.RULE)
        sketch = re.findall(r"`([^`]+)`", section)
        self.assertTrue(sketch, "§3.5 names no command any more: reword the rule")
        for cmd in sketch:
            with self.subTest(sketch=cmd):
                self.assertIn(cmd, self.RULE)
                self.assertNotIn(f"`{cmd}`", self.RULE)
                self.assertTrue(command_faults(cmd, run_flags(RUNNER_RUN_USAGE)),
                                f"the runner now has {cmd}: the rule should use it, not call it absent")
