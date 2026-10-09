"""./dev.sh hooks: a hook's own test answers 0 (pass), 3 (UNCHECKED: it could not run
here, e.g. no site-scrapers above a lone clone) or anything else (FAIL). Exit 3 must be
named UNCHECKED with its reason and make the gate exit 3: never `ok`, never a FAIL.

Each case runs dev.sh in a throwaway copy holding one stub hook whose test exits a
chosen code, so exits 0, 1 and 3 must give three different results."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

REASON = "site-scrapers not found above /nowhere: the recipe cases did not run"


def stub_test(code):
    """A hook test as the shared ones end: its lines, then its verdict and exit code."""
    if code == 3:
        tail = f'echo "  UNCHECKED  {REASON}"\necho "UNCHECKED: {REASON}"\nexit 3\n'
    elif code == 0:
        tail = 'echo "  ok  stub case"\nexit 0\n'
    else:
        tail = f'echo "  FAIL  stub case broke"\nexit {code}\n'
    return "#!/usr/bin/env bash\n" + tail


class HooksGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="todo-hooks-gate-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def copy_with(self, *codes):
        """A copy of dev.sh beside .claude/hooks holding one stub hook per code, and no
        settings.json (registration is td-2's, not this test's)."""
        copy = self.tmp / f"todo-{'-'.join(map(str, codes))}"
        hooks = copy / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        shutil.copy2(ROOT / "dev.sh", copy / "dev.sh")
        for i, code in enumerate(codes):
            for name, body in ((f"h{i}.sh", "#!/usr/bin/env bash\nexit 0\n"), (f"test-h{i}.sh", stub_test(code))):
                (hooks / name).write_text(body)
                (hooks / name).chmod((hooks / name).stat().st_mode | stat.S_IXUSR)
        return copy

    def run_dev(self, copy, *args):
        env = {k: v for k, v in os.environ.items() if k != "TODO_DEV_CHECK"}
        r = subprocess.run([str(copy / "dev.sh"), *args], capture_output=True, text=True, env=env, timeout=120)
        return r.returncode, r.stdout + r.stderr

    def test_exit_0_1_and_3_give_three_different_results(self):
        got = {}
        for code in (0, 1, 3):
            exit_code, out = self.run_dev(self.copy_with(code), "hooks")
            got[code] = exit_code
            lines = [l.strip() for l in out.splitlines() if l.strip() and not l.strip().startswith("NOTE")]
            if code == 0:
                self.assertEqual(lines, ["ok    hooks: 1 hooks, each executable and passing its own test"], out)
            elif code == 1:
                self.assertEqual(lines[0], "FAIL  test-h0.sh: exit 1", out)
                self.assertIn("stub case broke", out)
                self.assertNotIn("UNCHECKED", out)
            else:
                self.assertEqual(lines[0], f"UNCHECKED  test-h0.sh: {REASON}", out)
                self.assertNotIn("FAIL", out)
                self.assertNotIn("ok    hooks", out)
        self.assertEqual(got, {0: 0, 1: 1, 3: 3})

    def test_unchecked_without_a_reason_says_so(self):
        copy = self.copy_with(3)
        (copy / ".claude" / "hooks" / "test-h0.sh").write_text("#!/usr/bin/env bash\nexit 3\n")
        code, out = self.run_dev(copy, "hooks")
        self.assertEqual(code, 3, out)
        self.assertIn("UNCHECKED  test-h0.sh: exit 3 without saying why", out)

    def test_a_fail_beside_an_unchecked_is_a_fail(self):
        code, out = self.run_dev(self.copy_with(3, 1, 0), "hooks")
        self.assertEqual(code, 1, out)
        self.assertIn("UNCHECKED  test-h0.sh", out)
        self.assertIn("FAIL  test-h1.sh: exit 1", out)

    def test_check_counts_unchecked_apart_from_failed_and_never_green(self):
        results = {}
        for code in (0, 1, 3):
            copy = self.copy_with(code)
            exit_code, out = self.run_dev(copy, "check", "hooks")
            jexit, jout = self.run_dev(copy, "check", "--json", "hooks")
            results[code] = (exit_code, out.strip().splitlines()[-1], jexit, json.loads(jout))
        self.assertEqual(results[0], (0, "check: all 1 gates green", 0, {"ok": True, "gates": {"hooks": True}}))
        self.assertEqual(results[1], (1, "check: 1 of 1 gates FAILED", 1, {"ok": False, "gates": {"hooks": False}}))
        self.assertEqual(results[3], (3, "check: 0 of 1 gates FAILED, 1 UNCHECKED (did not run here, not a pass)",
                                      3, {"ok": False, "gates": {"hooks": False}}))


if __name__ == "__main__":
    unittest.main()
