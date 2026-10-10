"""Documented == implemented, both directions: README's command table against
the parser (commands and every flag), the plan's §3 list against the parser,
and dev.sh's usage against its case arms."""
import re
import unittest

from tests.helpers import ROOT, workspace_file
from todolib import cli

PLAN = workspace_file("PLAN-todo-tool.md")  # walks up, so a mutant copy runs it too
# Commands the plan's §3 does not list, each with why. An entry the plan later lists is a
# stale exemption and fails the check: drop it here (td-27 dropped get, find, refs, approve,
# dispatch, dispatchable and stale-plans when §3 named them, 2026-10-09).
BEYOND_PLAN = {"init": "a store has to be started; §3 assumes one exists",
               # The gap his question found (this plan's §9): a hand edit that broke a seal is
               # accepted only by a recorded verb; `help` is what tools/checks reads for cli.json.
               "reseal": "§9: accept a broken seal, recorded in hand_edits",
               "split": "PLAN-small-tasks.md §2.1: an L item into children, each one checkpoint",
               "help": "cli.json: tools/checks reads the verbs from `todo help`"}
# A command name may hold a hyphen (stale-plans); `[a-z]+` read it as "stale".
PLAN_COMMAND = re.compile(r"(?:^|\s)todo ([a-z][a-z-]*)")


def plan_commands(text):
    """The command names in the fenced block of the plan's §3."""
    sec = text.split("## 3. Commands", 1)[1].split("\n## ", 1)[0]
    return set(PLAN_COMMAND.findall(sec.split("```", 2)[1]))


def plan_drift(planned, implemented, declared):
    """Plan == CLI, both directions, net of the declared exemptions: {} when they agree."""
    beyond = implemented - planned
    drift = {"planned, not implemented": sorted(planned - implemented),
             "implemented, not planned, not declared in BEYOND_PLAN": sorted(beyond - declared),
             "declared in BEYOND_PLAN, but planned or not a command (stale)": sorted(declared - beyond)}
    return {k: v for k, v in drift.items() if v}


def parser_flags():
    ap = cli.build_parser()
    sub = next(a for a in ap._actions if a.dest == "command").choices
    out = {}
    for name, p in sub.items():
        out[name] = sorted(o for a in p._actions for o in a.option_strings if o.startswith("--") and o != "--help")
    return out, sorted(o for a in ap._actions for o in a.option_strings if o not in ("-h", "--help"))


def readme_commands():
    text = (ROOT / "README.md").read_text()
    m = re.search(r"<!-- commands -->\n(.*?)\n\n", text, re.S)
    assert m, "README.md has no <!-- commands --> table"
    rows = [ln for ln in m.group(1).splitlines() if ln.startswith("| `todo ")]
    out = {}
    for r in rows:
        usage = r.split("|")[1].strip().strip("`")
        name = usage.split()[1]
        out.setdefault(name, set()).update(re.findall(r"--[a-z][a-z-]*", usage))
    return {k: sorted(v) for k, v in out.items()}


class Docs(unittest.TestCase):
    def test_readme_command_table_equals_the_parser(self):
        flags, _ = parser_flags()
        self.assertEqual(readme_commands(), flags)

    def test_readme_names_the_global_options(self):
        _, glob = parser_flags()
        text = (ROOT / "README.md").read_text()
        for o in glob:
            self.assertIn(f"`{o} ", text, f"global option {o} undocumented")

    @unittest.skipUnless(PLAN, "the plan lives in the workspace, not in a fresh clone")
    def test_plan_section_3_lists_exactly_the_commands(self):
        planned = plan_commands(PLAN.read_text())
        self.assertEqual(plan_drift(planned, set(cli.COMMANDS), set(BEYOND_PLAN)), {})

    def test_dev_sh_usage_equals_its_case_arms(self):
        text = (ROOT / "dev.sh").read_text()
        usage = text.split("cat <<'EOF'", 1)[1].split("\nEOF", 1)[0]
        documented = set(re.findall(r"^  ([a-z]+)\s", usage, re.M))
        case = text.rsplit('case "${1:-}" in', 1)[1]
        arms = set(re.findall(r"^  ([a-z]+)\)", case, re.M))
        self.assertEqual(documented, arms)
        gates = set(re.search(r"^GATES=\(([^)]*)\)", text, re.M).group(1).split())
        self.assertLessEqual(gates, arms)


class PlanDrift(unittest.TestCase):
    """The plan check goes red in each direction, on a fixture plan (runs in a fresh clone too)."""

    @staticmethod
    def fixture(commands):
        lines = "\n".join(f"todo {c} ID" for c in sorted(commands))
        return f"# plan\n\n## 3. Commands\n\n```\n{lines}\n```\n\nprose: todo notacommand\n\n## 4. Next\n"

    def drift(self, commands):
        return plan_drift(plan_commands(self.fixture(commands)), set(cli.COMMANDS), set(BEYOND_PLAN))

    def planned_now(self):
        return set(cli.COMMANDS) - set(BEYOND_PLAN)

    def test_a_plan_naming_every_undeclared_command_agrees(self):
        # The control: also proves a hyphenated name (stale-plans) is read whole.
        self.assertIn("stale-plans", self.planned_now())
        self.assertEqual(self.drift(self.planned_now()), {})

    def test_a_command_missing_from_the_plan_fails(self):
        for name in ("stale-plans", "get", "dispatchable"):
            with self.subTest(name=name):
                self.assertEqual(self.drift(self.planned_now() - {name}),
                                 {"implemented, not planned, not declared in BEYOND_PLAN": [name]})

    def test_a_planned_command_not_implemented_fails(self):
        self.assertEqual(self.drift(self.planned_now() | {"nope"}), {"planned, not implemented": ["nope"]})

    def test_an_exemption_the_plan_now_lists_fails_as_stale(self):
        self.assertEqual(self.drift(self.planned_now() | {"init"}),
                         {"declared in BEYOND_PLAN, but planned or not a command (stale)": ["init"]})
