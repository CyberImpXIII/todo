"""./dev.sh checks (td-12): tools/checks' `checks run .` with the roster-name copy
in devtools/audit.json, judged by devtools/checks_gate.py.

The judge is tested on reports written here; the gate itself runs the real
checks CLI in a throwaway workspace (ws/tools/checks, ws/tools/todo), where
no-roster applies, so a planted roster name must turn it red. That workspace
has no top CLAUDE.md rules or plans, so other checks are red there too: the
live tests read the no-roster lines, not the exit code alone."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT
from devtools.checks_gate import judge

IGNORE = shutil.ignore_patterns(".git", ".mutants", "__pycache__", "*.pyc")


def report(*results):
    return json.dumps({"results": [{"check": c, "status": s, "lines": lines} for c, s, lines in results]})


def checks_cli():
    """The real CLI: the one an outer ./dev.sh exported (a copy under .mutants/
    has no sibling), else the sibling repo. Absent is a failure, never a skip."""
    cli = Path(os.environ.get("CHECKS_CLI") or ROOT.parent / "checks" / "checks")
    if not os.access(cli, os.X_OK):
        raise AssertionError(f"no checks CLI at {cli}: the checks gate cannot be tested (td-12)")
    return cli


def env_without_cli(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ("CHECKS_CLI", "TODO_ROOT")}
    return dict(env, **extra)


def gate(repo, env):
    r = subprocess.run([str(repo / "dev.sh"), "checks"], cwd=repo, capture_output=True, text=True,
                       env=env, timeout=300)
    return r.returncode, r.stdout + r.stderr


class Judge(unittest.TestCase):
    OK = [("accessor", "ok", []), ("no-roster", "ok", []), ("stores-exported", "unchecked", ["no cli.json"])]

    def test_all_ok_with_no_roster_ok_is_green(self):
        ok, lines = judge(report(*self.OK), 0)
        self.assertTrue(ok, lines)
        self.assertIn("1 unchecked (stores-exported)", lines[0])

    def test_a_failing_check_is_red_with_its_findings(self):
        ok, lines = judge(report(*self.OK, ("no-secrets", "fail", ["a.txt:1 key"])), 1)
        self.assertFalse(ok)
        self.assertEqual(lines, ["  FAIL  checks: no-secrets fail", "          a.txt:1 key"])

    def test_no_roster_unchecked_is_red_though_checks_calls_it_green(self):
        ok, lines = judge(report(("accessor", "ok", []), ("no-roster", "unchecked", ["no names given"])), 0)
        self.assertFalse(ok)
        self.assertEqual(len(lines), 1)
        self.assertIn("no-roster unchecked (no names given)", lines[0])

    def test_no_roster_absent_is_red(self):
        ok, lines = judge(report(("accessor", "ok", [])), 0)
        self.assertFalse(ok)
        self.assertIn("no-roster did not run here", lines[0])

    def test_an_exit_code_that_disagrees_with_the_report_is_red(self):
        for results, code in ((self.OK, 1), (self.OK + [("x", "error", [])], 0)):
            ok, lines = judge(report(*results), code)
            self.assertFalse(ok)
            self.assertIn("disagrees with the report", lines[-1])

    def test_no_report_is_red(self):
        for text in ("", "Traceback: boom", "[]", '{"results": [{"status": "ok"}]}'):
            ok, lines = judge(text, 0)
            self.assertFalse(ok, text)
            self.assertIn("no report from `checks run`", lines[0])


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="todo-checks-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def workspace(self):
        ws = self.tmp / "ws"
        shutil.copytree(checks_cli().parent, ws / "tools" / "checks", ignore=IGNORE)
        shutil.copytree(ROOT, ws / "tools" / "todo", ignore=IGNORE)
        (ws / "CLAUDE.md").write_text("workspace\n")
        return ws / "tools" / "todo"

    def no_roster_lines(self, out):
        return [ln for ln in out.splitlines() if "no-roster" in ln]

    def test_no_roster_runs_with_the_names_through_the_default_sibling_path(self):
        repo = self.workspace()
        code, out = gate(repo, env_without_cli())
        self.assertNotIn("no checks CLI", out)
        self.assertEqual(self.no_roster_lines(out), [], out)  # ran, with names, and ok

    def test_a_planted_roster_name_turns_the_gate_red(self):
        repo = self.workspace()
        name = json.loads((ROOT / "devtools" / "audit.json").read_text())["roster_names"][0]
        (repo / "planted.json").write_text(json.dumps({"agent": name}) + "\n")
        code, out = gate(repo, env_without_cli())
        self.assertEqual(code, 1, out)
        self.assertIn("  FAIL  checks: no-roster fail", out)
        self.assertTrue(any("planted.json" in ln for ln in out.splitlines()), out)

    def test_no_checks_cli_is_red_never_skipped(self):
        repo = self.tmp / "todo"
        shutil.copytree(ROOT, repo, ignore=IGNORE)
        for env in (env_without_cli(), env_without_cli(CHECKS_CLI=str(self.tmp / "nosuch"))):
            code, out = gate(repo, env)
            self.assertEqual(code, 1, out)
            self.assertIn("FAIL  checks: no checks CLI", out)


if __name__ == "__main__":
    unittest.main()
