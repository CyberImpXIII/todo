"""./dev.sh check: the JSON contract ({"ok": bool, "gates": {name: bool}}) and the
gate list. Only the cheap gates run here: `test` would run this file again and
`mutants` copies the repo and runs the tests in each copy (the nesting guard in
cmd_check refuses both inside another check)."""
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
    r = subprocess.run([str(Path(root) / "dev.sh"), "check", *args], capture_output=True, text=True,
                       env=dict(os.environ, **(env or {})))
    return r.returncode, r.stdout, r.stderr


class CheckJson(unittest.TestCase):
    def test_named_gates_run_alone_in_order_and_report_green(self):
        for gates in (CHEAP, list(reversed(CHEAP))):
            code, out, err = dev(ROOT, "--json", *gates)
            self.assertEqual(code, 0, out + err)
            got = json.loads(out)
            self.assertEqual(got, {"ok": True, "gates": {g: True for g in gates}})
            self.assertEqual(list(got["gates"]), gates)  # the gate list changes the output

    def test_a_red_gate_is_false_and_makes_ok_false_and_the_exit_1(self):
        tmp = Path(tempfile.mkdtemp(prefix="todo-dev-"))
        try:
            copy = tmp / "todo"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", ".mutants", "__pycache__", "*.pyc"))
            (copy / "vocab.json").write_text("{,\n")
            code, out, err = dev(copy, "--json", *CHEAP)
            self.assertEqual(code, 1, out + err)
            self.assertEqual(json.loads(out), {"ok": False, "gates": {"files": False, "audit": True}})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_unknown_gate_is_refused_with_no_json(self):
        code, out, err = dev(ROOT, "--json", "files", "nosuch")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("unknown gate 'nosuch'", err)

    def test_a_check_inside_a_check_refuses_the_tests_and_the_mutants(self):
        for gate in ("test", "mutants"):
            code, out, err = dev(ROOT, "--json", "files", gate, env={"TODO_DEV_CHECK": "1"})
            self.assertEqual((code, out), (2, ""), gate)
            self.assertIn("refusing test/mutants inside another", err)


if __name__ == "__main__":
    unittest.main()
