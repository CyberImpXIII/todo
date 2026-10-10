"""Documented == implemented, both directions: README's command table against
the parser (commands and every flag), the plan's §3 list against the parser,
and dev.sh's usage against its case arms."""
import re
import unittest

from tests.helpers import ROOT, workspace_file
from todolib import cli

PLAN = workspace_file("PLAN-todo-tool.md")  # walks up, so a mutant copy runs it too
# Commands the plan's §3 does not list, each with why; the plan fix is reported to its owner (TODO.md).
BEYOND_PLAN = {"init": "a store has to be started; §3 assumes one exists",
               # The three verbs every service answers (PLAN-services.md §3; this plan's §9 step 4),
               # which §3's command list does not name yet.
               "get": "PLAN-services.md §3: one record by id", "find": "PLAN-services.md §3: records by tag",
               "refs": "PLAN-services.md §3: records whose ref: names an id",
               # The gap his question found (this plan's §9): a hand edit that broke a seal is
               # accepted only by a recorded verb; `help` is what tools/checks reads for cli.json.
               "reseal": "§9: accept a broken seal, recorded in hand_edits",
               "split": "PLAN-small-tasks.md §2.1: an L item into children, each one checkpoint",
               # Jacob, 2026-10-09: "Please dispatch any available tasks, if we do not have a script
               # for this, that should be added to the todo service" (the workspace TODO.md item
               # 'No command answers "what can be dispatched now"').
               "approve": "TODO.md 2026-10-09: record Jacob's approval", "dispatch": "the same: the dispatched mark",
               "dispatchable": "the same: what can be dispatched now",
               "help": "cli.json: tools/checks reads the verbs from `todo help`"}


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
        text = PLAN.read_text()
        sec = text.split("## 3. Commands", 1)[1].split("\n## ", 1)[0]
        block = sec.split("```", 2)[1]
        planned = set(re.findall(r"(?:^|\s)todo ([a-z]+)", block))
        self.assertEqual(planned - set(cli.COMMANDS), set(), "planned, not implemented")
        self.assertEqual(set(cli.COMMANDS) - planned, set(BEYOND_PLAN), "implemented, not planned (and not declared above)")

    def test_dev_sh_usage_equals_its_case_arms(self):
        text = (ROOT / "dev.sh").read_text()
        usage = text.split("cat <<'EOF'", 1)[1].split("\nEOF", 1)[0]
        documented = set(re.findall(r"^  ([a-z]+)\s", usage, re.M))
        case = text.rsplit('case "${1:-}" in', 1)[1]
        arms = set(re.findall(r"^  ([a-z]+)\)", case, re.M))
        self.assertEqual(documented, arms)
        gates = set(re.search(r"^GATES=\(([^)]*)\)", text, re.M).group(1).split())
        self.assertLessEqual(gates, arms)
