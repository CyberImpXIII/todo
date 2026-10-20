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

    def test_a_named_hook_runs_that_hook_alone(self):
        # td-82: `./dev.sh hooks NAME.sh` is one check part per hook. The name must
        # change what runs: h0's test fails, h1's passes, so each answers for itself.
        copy = self.copy_with(1, 0)
        code, out = self.run_dev(copy, "hooks", "h1.sh")
        self.assertEqual(code, 0, out)
        self.assertIn("ok    hooks: 1 hooks (h1.sh), each executable", out)
        self.assertNotIn("test-h0.sh", out)
        code, out = self.run_dev(copy, "hooks", "h0.sh")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL  test-h0.sh: exit 1", out)
        code, out = self.run_dev(copy, "hooks")
        self.assertEqual(code, 1, out)

    def test_a_name_that_is_no_hook_is_a_fail_never_an_empty_pass(self):
        copy = self.copy_with(0)
        for name, says in (("nosuch.sh", "no hook nosuch.sh in .claude/hooks"),
                           ("h0", "no hook h0 in .claude/hooks"),
                           ("test-h0.sh", "'test-h0.sh' is not a hook's file name"),
                           ("../hooks/h0.sh", "'../hooks/h0.sh' is not a hook's file name")):
            with self.subTest(name):
                code, out = self.run_dev(copy, "hooks", name)
                self.assertEqual(code, 1, out)
                self.assertIn(f"FAIL  hooks: {says}", out)
                self.assertNotIn("ok    hooks", out)

    def test_a_named_hook_without_its_test_is_a_fail(self):
        copy = self.copy_with(0)
        (copy / ".claude" / "hooks" / "test-h0.sh").unlink()
        code, out = self.run_dev(copy, "hooks", "h0.sh")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL  h0.sh has no test-h0.sh", out)

    def test_check_counts_unchecked_apart_from_failed_and_never_green(self):
        """The hooks gate as a part of `./dev.sh check` (the shared runner, one part):
        exit 0, 1 and 3 give a pass, a fail and an UNCHECKED that exits 3, never 0."""
        results = {}
        for code in (0, 1, 3):
            copy = self.copy_with(code)
            (copy / "devtools").mkdir()
            shutil.copy2(ROOT / "devtools" / "parts.py", copy / "devtools" / "parts.py")
            (copy / "check.parts.json").write_text(json.dumps({"parts": [
                {"name": "hooks", "run": "./dev.sh hooks", "files": ["."], "timeout_s": 120}]}))
            exit_code, out = self.run_dev(copy, "check")
            jexit, jout = self.run_dev(copy, "check", "--json")
            statuses = [(c["name"], c["status"]) for c in json.loads(jout)["checks"]]
            results[code] = (exit_code, out.strip().splitlines()[-1].split(";")[0], jexit, statuses)
        self.assertEqual(results[0], (0, "check: 1 of 1 passed", 0, [("hooks", "ok")]))
        self.assertEqual(results[1], (1, "check: 0 of 1 passed", 1, [("hooks", "fail")]))
        self.assertEqual(results[3], (3, "check: 0 of 1 passed", 3, [("hooks", "unchecked")]))


if __name__ == "__main__":
    unittest.main()
