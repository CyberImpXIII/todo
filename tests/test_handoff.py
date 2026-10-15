"""Handoffs that survive a usage limit (PLAN-small-tasks.md §4.1, §4.3) and the
stop rule and iterate rule every brief carries (§2.3, §3.5): `todo edit ID --handoff` records the note
with the date and the work repo's commit at that moment (the checkpoint), and
`todo brief` prints both, so a later or cloud dispatch resumes there."""
import json
import re
import subprocess
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
# The runner's `run` options the iterate rule is worded against: `parts.py usage
# --json` run.options (parts.py 1.3.0), flag -> the value it takes, or None.
# IterateRule holds it equal to the runner's own when the runner is here.
RUNNER_RUN_OPTIONS = {"--resume": None, "--only": "<name>", "--json": None}
COMMAND_HEADS = ("./dev.sh", "dev.sh", "check")


def run_options(usage):
    """{flag: value or None} from `parts.py usage --json`'s run.options, or None
    when it has no such table (an older runner, or not this runner at all)."""
    try:
        return {o["flag"]: o.get("value") for o in usage["run"]["options"]}
    except (KeyError, TypeError):
        return None


def command_faults(command, options):
    """Why a dev.sh command is not one the runner runs, or []. dev.sh reaches the
    runner as `./dev.sh check OPTIONS`, whose arguments go to `parts.py run`, and
    as `./dev.sh test <part>...`, which the reference dev.sh turns into
    `check --only <part>...`."""
    words = command.split()
    if words[:1] == ["check"]:
        words = ["./dev.sh"] + words
    if words[:1] == ["dev.sh"]:
        words[0] = "./dev.sh"
    if words[:2] == ["./dev.sh", "test"] and len(words) > 2:
        words = ["./dev.sh", "check"] + [x for part in words[2:] for x in ("--only", part)]
    if words[:2] != ["./dev.sh", "check"]:
        return [f"`{command}` is not `./dev.sh check` or `./dev.sh test <part>`, dev.sh's ways into the runner"]
    faults, rest, i = [], words[2:], 0
    while i < len(rest):
        w = rest[i]
        if w not in options:
            faults.append(f"`{command}`: {w} is not an option of `parts.py run`")
        elif options[w] is not None:
            if i + 1 >= len(rest):
                faults.append(f"`{command}`: {w} takes {options[w]}")
            i += 1  # its value
        i += 1
    return faults


def rule_faults(rule, options):
    """Every backticked dev.sh command in the rule, held to the runner's options."""
    if options is None:
        return ["no `parts.py usage --json` run.options to hold the rule to"]
    cmds = [c for c in re.findall(r"`([^`]+)`", rule) if c.split()[:1] and c.split()[0] in COMMAND_HEADS]
    if not cmds:
        return ["the rule names no dev.sh command"]
    return [f for c in cmds for f in command_faults(c, options)]


def sketch_faults(rule, sketch, options):
    """The plan's sketched commands against the rule: one the runner runs is used in
    backticks; one it does not run is named, unbackticked, as absent."""
    faults = []
    for cmd in sketch:
        quoted = re.search(r"`(?:\./)?" + re.escape(cmd) + "`", rule)
        if not command_faults(cmd, options):
            if not quoted:
                faults.append(f"the runner runs {cmd}: the rule should use it")
        elif quoted:
            faults.append(f"the rule offers {cmd}, which the runner does not run")
        elif cmd not in rule:
            faults.append(f"the rule does not name the plan's {cmd} as absent")
    return faults


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
        self.todo("-C", a, "add", "not ready", "--kind", NOTE, "--done-when", "it is")  # no repo, work or size
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
    brief.iterate_rule): an option added, removed or renamed on either side turns
    this red."""
    RULE = VOCAB.brief["iterate_rule"]
    SKETCH = ["dev.sh test <part>", "check --quick"]  # §3.5's, when the plan is absent

    def test_every_brief_carries_the_iterate_rule(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "ready", "--kind", NOTE, *READY)
        self.todo("-C", a, "add", "not ready", "--kind", NOTE, "--done-when", "it is")  # no repo, work or size
        for iid, ok in (("aa-1", True), ("aa-2", False)):
            with self.subTest(id=iid):
                out = self.todo("-C", a, "brief", iid, ok=ok).stdout
                self.assertIn(f"Iterate rule: {self.RULE}", out)
                self.assertIn("`./dev.sh test <part>`", out)
                self.assertIn("`./dev.sh check --resume`", out)
                self.assertIn("Run the full suite once, before the commit", out)

    def test_the_rules_commands_are_the_pinned_runners(self):
        self.assertEqual(rule_faults(self.RULE, RUNNER_RUN_OPTIONS), [])
        self.assertEqual(sketch_faults(self.RULE, self.SKETCH, RUNNER_RUN_OPTIONS), [])

    def test_an_option_added_removed_or_renamed_changes_the_verdict(self):
        """Counterfactuals: the same rule is red against a runner one option away."""
        drop = lambda flag: {k: v for k, v in RUNNER_RUN_OPTIONS.items() if k != flag}
        with self.subTest(runner="--only removed"):
            self.assertTrue(rule_faults(self.RULE, drop("--only")))
            self.assertTrue(sketch_faults(self.RULE, self.SKETCH, drop("--only")))
        with self.subTest(runner="--only takes no value"):
            self.assertTrue(rule_faults(self.RULE, dict(RUNNER_RUN_OPTIONS, **{"--only": None})))
        with self.subTest(runner="--resume renamed --since"):
            self.assertTrue(rule_faults(self.RULE, dict(drop("--resume"), **{"--since": None})))
        with self.subTest(runner="--quick added"):
            self.assertEqual(rule_faults(self.RULE, dict(RUNNER_RUN_OPTIONS, **{"--quick": None})), [])
            self.assertTrue(sketch_faults(self.RULE, self.SKETCH, dict(RUNNER_RUN_OPTIONS, **{"--quick": None})))
        with self.subTest(runner="no run.options table"):
            self.assertIsNone(run_options({"run": {"usage": "parts.py run <parts.json> [--resume]"}}))
            self.assertTrue(rule_faults(self.RULE, None))
        for old, new in (("--resume`", "--quick`"), ("`./dev.sh test <part>`", "`./dev.sh test`"),
                         ("`./dev.sh check`", "`./dev.sh verify`")):
            with self.subTest(rule=new):
                self.assertIn(old, self.RULE)
                self.assertTrue(rule_faults(self.RULE.replace(old, new), RUNNER_RUN_OPTIONS))
        with self.subTest(rule="no command at all"):
            self.assertTrue(rule_faults("Iterate small.", RUNNER_RUN_OPTIONS))

    def test_the_readme_quotes_the_rule_vocab_json_carries(self):
        readme = " ".join((ROOT / "README.md").read_text().split())
        self.assertIn(f'"{self.RULE}"', readme)

    @unittest.skipUnless(RUNNER and RUNNER_DEV, "the runner lives in tools/checks, not in a fresh clone")
    def test_the_pin_is_the_runners_usage_and_dev_sh_hands_it_its_arguments(self):
        """parts.py's own `usage --json` gives the pinned options, and the reference
        dev.sh passes `check`'s arguments on and turns `test <part>` into --only."""
        r = subprocess.run(["python3", str(RUNNER), "usage", "--json"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run_options(json.loads(r.stdout)), RUNNER_RUN_OPTIONS, f"{RUNNER}: reword the iterate rule")
        dev = RUNNER_DEV.read_text()
        self.assertRegex(dev, r'cmd_check\(\) \{ exec python3 [^\n]*parts\.py" run [^\n]*"\$@"; \}')
        self.assertRegex(dev, r'only\+=\(--only "\$p"\)')

    @unittest.skipUnless(SMALL_TASKS_PLAN, "the plan lives in the workspace, not in a fresh clone")
    def test_the_rule_is_the_plans_and_uses_or_names_each_sketched_command(self):
        """§3.5's lead and its 'full suite once, before the commit' are the rule's;
        each command §3.5 sketches is the pinned SKETCH, used when the runner runs it
        and named as absent when it does not."""
        lead = "Iterate small, then run whole once."
        section = SMALL_TASKS_PLAN.read_text().split(f"**{lead}**", 1)[1].split("\n6.", 1)[0]
        section = " ".join(section.split())
        self.assertTrue(self.RULE.startswith(lead))
        self.assertIn("runs the full suite once, before the commit", section)
        self.assertIn("Run the full suite once, before the commit", self.RULE)
        self.assertEqual(re.findall(r"`([^`]+)`", section), self.SKETCH, "§3.5's commands changed: reword the rule")
