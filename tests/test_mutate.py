"""devtools/mutate.py removes its copies however a run ends, and refuses an
argument it does not know (an unknown `--help` once ran every mutant, and a
SIGTERM to that run left ~124 copies under .mutants/)."""
import json
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.helpers import ROOT

MUTATE = ROOT / "devtools" / "mutate.py"


class Mutate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="todo-mutate-"))
        self.work = self.tmp / "work"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mutants(self, run):
        path = self.tmp / "mutants.json"
        path.write_text(json.dumps({"mutants": [
            {"id": "one", "gate": "test", "file": "README.md", "old": "# todo", "new": "# x", "run": run}]}))
        return path

    def leftovers(self):
        return sorted(p.name for p in self.work.glob("run-*")) if self.work.exists() else []

    def test_sigterm_mid_run_stops_the_commands_and_removes_the_copies(self):
        # The baseline copy runs this first: it marks that it started, then outlasts the test.
        path = self.mutants(["sh", "-c", "touch started; exec sleep 120"])
        p = subprocess.Popen([sys.executable, MUTATE, path, "--work", self.work],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 60
            while not list(self.work.glob("run-*/base0/started")):
                self.assertIsNone(p.poll(), "mutate.py ended before its command started")
                self.assertLess(time.time(), deadline, "the baseline command never started")
                time.sleep(0.2)
            self.assertEqual(len(self.leftovers()), 1)
            p.send_signal(signal.SIGTERM)
            out, err = p.communicate(timeout=30)  # far less than the sleep: the command was stopped, not waited for
        finally:
            if p.poll() is None:
                p.kill()
            p.communicate()
        self.assertEqual(p.returncode, 128 + signal.SIGTERM, out + err)
        self.assertEqual(self.leftovers(), [])

    def test_an_unknown_argument_is_refused_and_runs_nothing(self):
        path = self.mutants(["true"])
        for args in (["--help"], [path, "--help"], [path, "--only"], [path, "extra.json"]):
            with self.subTest(args=args):
                r = subprocess.run([sys.executable, MUTATE, *args, "--work", self.work],
                                   capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("usage: devtools/mutate.py", r.stderr)
                self.assertFalse(self.work.exists(), "a refused run made a work folder")

    def test_a_known_run_still_runs_and_cleans_up(self):
        # The control for the two above: the same file, run properly, does run (and `true` survives).
        r = subprocess.run([sys.executable, MUTATE, self.mutants(["true"]), "--only", "one", "--work", self.work],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SURVIVED  one", r.stdout)
        self.assertEqual(self.leftovers(), [])
