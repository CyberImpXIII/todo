"""Jacob's steps (PLAN-architecture.md §11 S7): a jacob-step carries a done_check;
`todo steps --run` closes the step whose check exits 0, leaves the rest open, and
reports a check it could not judge as UNCHECKED (exit 3), never as done. A step is
never ready or dispatchable; blockers groups every step under one jacob root."""
import json
import os
from unittest import mock

from tests.helpers import ROOT, Case
from todolib import steps
from todolib.vocab import VOCAB, Vocab

STEP = VOCAB.role("step_kind")
NOTE = VOCAB.role("default_kind")
RESOLUTION = VOCAB.role("step_resolution")


class Steps(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")

    def step(self, title, check):
        self.todo("-C", self.a, "add", title, "--kind", STEP, "--done-check", check)

    def ids(self, data):
        return [it["id"] for it in data["items"]]

    def test_a_step_needs_its_check_and_one_line(self):
        r = self.todo("-C", self.a, "add", "s", "--kind", STEP, ok=False)
        self.assertIn("--done-check", r.stderr)
        r = self.todo("-C", self.a, "add", "s", "--kind", STEP, "--done-check", "true\nfalse", ok=False)
        self.assertIn("one line", r.stderr)

    def test_steps_numbers_them_without_running_anything(self):
        marker = self.a / "ran"
        self.step("first", f"touch {marker}")
        self.todo("-C", self.a, "add", "not a step", "--kind", NOTE)
        self.step("second", "true")
        out = self.todo("-C", self.a, "steps").stdout
        self.assertIn(" 1. aa-1", out)
        self.assertIn(" 2. aa-3", out)
        self.assertNotIn("aa-2", out)
        self.assertFalse(marker.exists(), "listing must not run a check")

    def test_run_closes_exactly_the_steps_whose_check_passes(self):
        (self.a / "taken").write_text("")
        self.step("taken", "test -f taken")  # run in the store's folder
        self.step("not taken", "test -f missing")
        r = self.todo("-C", self.a, "steps", "--run", "--json")
        report = json.loads(r.stdout)
        self.assertEqual(report["closed"], ["aa-1"])
        verdicts = {s["id"]: s["verdict"] for s in report["steps"]}
        self.assertEqual(verdicts, {"aa-1": steps.DONE, "aa-2": steps.NOT_DONE})
        self.assertEqual(self.ids(self.store(self.a)), ["aa-2"])
        closed = self.history(self.a)["items"][0]
        self.assertEqual((closed["id"], closed["status"], closed["resolution"]), ("aa-1", VOCAB.closed, RESOLUTION))
        self.check(self.a)

    def test_a_check_that_cannot_be_judged_is_unchecked_never_done(self):
        self.step("killed", "kill -9 $$")
        self.step("taken", "true")
        r = self.todo("-C", self.a, "steps", "--run", ok=None)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("UNCHECKED", r.stderr)
        self.assertIn("aa-1 killed by signal 9", r.stderr)
        self.assertEqual(self.ids(self.store(self.a)), ["aa-1"], "the passing step still closes; the unjudged stays")

    def test_run_check_reads_the_exit_alone(self):
        self.assertEqual(steps.run_check("true", self.a), (steps.DONE, "exit 0"))
        self.assertEqual(steps.run_check("echo nope >&2; exit 4", self.a), (steps.NOT_DONE, "exit 4: nope"))
        self.assertIsNone(steps.run_check("", self.a)[0])
        self.assertIsNone(steps.run_check("kill -9 $$", self.a)[0])
        with mock.patch.object(VOCAB, "step_timeout", 0.5):
            self.assertEqual(steps.run_check("sleep 5", self.a), (None, "timed out after 0.5s"))
        with mock.patch.object(VOCAB, "step_shell", str(self.a / "no-such-shell")):
            verdict, detail = steps.run_check("true", self.a)
        self.assertIsNone(verdict)
        self.assertIn("could not start", detail)

    def test_the_check_runs_in_the_store_folder_with_stdin_closed(self):
        self.assertEqual(steps.run_check(f"test \"$(pwd -P)\" = \"{self.a.resolve()}\"", self.a)[0], steps.DONE)
        # Our own stdin holds a line: a check that inherited it would read it and pass.
        r, w = os.pipe()
        os.write(w, b"a line\n")
        os.close(w)
        saved = os.dup(0)
        try:
            os.dup2(r, 0)
            verdict = steps.run_check("read x", self.a)[0]
        finally:
            os.dup2(saved, 0)
            os.close(saved)
            os.close(r)
        self.assertEqual(verdict, steps.NOT_DONE)  # EOF at once: never reads ours, never hangs on a terminal

    def test_done_refuses_the_reserved_resolution_and_check_fails_it_elsewhere(self):
        self.todo("-C", self.a, "add", "n", "--kind", NOTE)
        r = self.todo("-C", self.a, "done", "aa-1", "--resolution", RESOLUTION, ok=False)
        self.assertIn("todo steps --run only", r.stderr)
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "fixed")
        data = self.history(self.a)
        data["items"][0]["resolution"] = RESOLUTION
        self.write_json(self.a / "todo-history.json", data)
        self.assertFails(self.a, "vocab", "set by todo steps --run only")

    def test_a_step_is_never_ready_or_dispatchable_and_blockers_names_it(self):
        self.todo("-C", self.a, "add", "s", "--kind", STEP, "--done-check", "false", "--work", VOCAB.works and list(VOCAB.works)[0],
                  "--done-when", "dw", "--size", VOCAB.ready_sizes[0])
        self.todo("-C", self.a, "approve", "aa-1", "--source", "s")
        self.assertNotIn("aa-1", self.todo("-C", self.a, "ready").stdout)
        view = json.loads(self.todo("-C", self.a, "dispatchable", "--json").stdout)
        self.assertNotIn("todo:aa-1", [d["id"] for d in view["dispatchable"]])
        roots = json.loads(self.todo("-C", self.a, "blockers", "--json").stdout)["roots"]
        mine = [g for g in roots if "aa-1" in g["ids"]]
        self.assertEqual([(g["kind"], g["what"]) for g in mine], [("jacob", f"his own steps ({STEP})")])
        r = self.todo("-C", self.a, "dispatch", "aa-1", ok=False)
        self.assertIn(STEP, r.stdout + r.stderr)


class Declared(Case):
    def test_vocab_refuses_a_relative_shell_or_a_bad_timeout(self):
        raw = json.loads((ROOT / "vocab.json").read_text())
        for steps_block in ({"shell": "sh", "timeout_s": 30}, {"shell": "/bin/sh", "timeout_s": 0},
                            {"shell": "/bin/sh", "timeout_s": True}):
            with self.subTest(steps_block):
                path = self.tmp / "vocab.json"
                path.write_text(json.dumps(dict(raw, steps=steps_block)))
                with self.assertRaises(ValueError):
                    Vocab(path)
