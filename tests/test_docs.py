"""Documented == implemented, both directions: README's command table against
the parser (commands and every flag), the plan's §3 list against the parser,
and dev.sh's usage against its case arms."""
import re
import unittest

from tests.helpers import ROOT
from todolib import cli

PLAN = ROOT.parent.parent / "PLAN-todo-tool.md"
# Commands the plan's §3 does not list, each with why; the plan fix is reported to its owner (TODO.md).
BEYOND_PLAN = {"init": "a store has to be started; §3 assumes one exists"}


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

    @unittest.skipUnless(PLAN.is_file(), "the plan lives in the workspace, not in a fresh clone")
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
