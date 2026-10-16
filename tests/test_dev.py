"""./dev.sh check on this repo's own parts (check.parts.json through the shared runner):
named parts run alone (--only), a red part is `fail` in the check-json document and
exit 1, an unknown part is refused, and the nesting guard. Only the cheap gates run
here: a test.* part would run a test module again (this one, maybe) and `mutants`
copies the repo and runs the tests in each copy, so the guard in cmd_check refuses
both inside another check. The runner's own wiring (N of M, --resume, exit 3) is
tests/test_parts_file.py's."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

CHEAP = ["files", "audit"]


def dev(root, *args, env=None):
    """dev.sh check with a progress file of its own: never the repo's .progress/check.json,
    which a check this test runs inside is writing."""
    base = {k: v for k, v in os.environ.items() if k != "CHECK_PARTS"}
    progress = Path(tempfile.mkdtemp(prefix="todo-dev-progress-"))
    try:
        r = subprocess.run([str(Path(root) / "dev.sh"), "check", *args], capture_output=True, text=True,
                           env=dict(base, PROGRESS_FILE=str(progress / "check.json"), **(env or {})),
                           stdin=subprocess.DEVNULL, timeout=300)
    finally:
        shutil.rmtree(progress, ignore_errors=True)
    return r.returncode, r.stdout, r.stderr


def only(*names):
    return [a for n in names for a in ("--only", n)]


def statuses(out):
    return {c["name"]: c["status"] for c in json.loads(out)["checks"]}


def copy_of_repo():
    tmp = Path(tempfile.mkdtemp(prefix="todo-dev-"))
    copy = tmp / "todo"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", ".mutants", ".progress", "__pycache__", "*.pyc"))
    return tmp, copy


class CheckJson(unittest.TestCase):
    def test_named_parts_run_alone_and_report_green(self):
        code, out, err = dev(ROOT, "--json", *only(*CHEAP), env={"TODO_DEV_CHECK": "1"})
        self.assertEqual(code, 0, out + err)
        got = statuses(out)
        self.assertEqual({n: got[n] for n in CHEAP}, {n: "ok" for n in CHEAP})
        # every other part is in the document, not run (the --only selection changes the output)
        self.assertEqual({s for n, s in got.items() if n not in CHEAP}, {"unchecked"})

    def test_a_red_part_is_fail_and_the_exit_1(self):
        tmp, copy = copy_of_repo()
        try:
            (copy / "vocab.json").write_text("{,\n")
            code, out, err = dev(copy, "--json", *only(*CHEAP))
            self.assertEqual(code, 1, out + err)
            got = statuses(out)
            self.assertEqual((got["files"], got["audit"]), ("fail", "ok"))
            self.assertIs(json.loads(out)["ok"], False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_unknown_part_is_refused(self):
        code, out, err = dev(ROOT, "--json", *only("files", "nosuch"), env={"TODO_DEV_CHECK": "1"})
        self.assertEqual(code, 2, out + err)
        self.assertIn("nosuch", out + err)
        self.assertFalse([c for c in json.loads(out)["checks"] if c["status"] == "ok"], out)

    def test_a_check_inside_a_check_refuses_the_tests_and_the_mutants(self):
        """Run in a copy whose parts are one trivial test module, the files gate and a
        mutants run of one mutant of it, so with the guard broken the parts run, finish and print
        JSON instead of running this test again without end (td-11). The copy runs
        them all when the guard is not set: the refusal is the guard's doing."""
        tmp, copy = copy_of_repo()
        try:
            shutil.rmtree(copy / "tests")
            (copy / "tests").mkdir()
            (copy / "tests" / "__init__.py").write_text("")
            (copy / "tests" / "test_stub.py").write_text(
                "import unittest\n\n\nclass Stub(unittest.TestCase):\n    def test_ok(self):\n        pass\n")
            (copy / "devtools" / "mutants.json").write_text(json.dumps({"mutants": [
                {"id": "stub", "gate": "the stub test", "file": "tests/test_stub.py", "old": "        pass",
                 "new": "        self.fail()", "run": ["python3", "-m", "unittest", "tests.test_stub"]}]}))
            (copy / "check.parts.json").write_text(json.dumps({"parts": [
                {"name": "test.stub", "run": "python3 -m unittest tests.test_stub", "files": ["tests"], "timeout_s": 120},
                {"name": "files", "run": "./dev.sh files", "files": ["."], "timeout_s": 120},
                {"name": "mutants", "run": "./dev.sh mutants", "files": ["."], "timeout_s": 120}]}))
            code, out, err = dev(copy, "--json", env={"TODO_DEV_CHECK": ""})
            self.assertEqual(statuses(out), {"test.stub": "ok", "files": "ok", "mutants": "ok"}, out + err)
            inside = {"TODO_DEV_CHECK": "1"}
            for args in (["--json"], ["--json", "--resume"], ["--json", *only("files", "test.stub")],
                         ["--json", *only("mutants")]):
                with self.subTest(args):
                    code, out, err = dev(copy, *args, env=inside)
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn("refusing test/mutants inside another", err)
            code, out, err = dev(copy, "--json", *only("files"), env=inside)
            self.assertEqual((code, statuses(out)["files"]), (0, "ok"), out + err)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
