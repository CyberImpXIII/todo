"""`./dev.sh check` runs check.parts.json through the shared runner
(devtools/parts.py, setup's rendered copy of tools/checks' runner;
PLAN-small-tasks.md §3, §5, §7). Held here:

  the parts file   valid by the runner's own `validate`; one part per
                   tests/test_*.py module (and none for a module that is gone),
                   then exactly the gates dev.sh's GATES names after `test`, in
                   that order, each run as `./dev.sh <gate>`, the hooks gate
                   as one part per hook in .claude/hooks (td-82);
  the wiring       a copy of dev.sh and the runner with canned parts: the text
                   run ends "N of M passed; failed: <name>", --json is one
                   document naming each part, `test <part>` runs that part
                   alone, --resume re-runs only what did not pass, and a part
                   that exits 3 (UNCHECKED) makes the check exit 3, never 0,
                   in text and in --json, while a part --only did not run does not;
  the contract     in the workspace, tools/checks' own validators: check-json on
                   the canned copy's document, check-partial on this repo
                   (it hands dev.sh a suite of its own through CHECK_PARTS and
                   touches nothing here).

The runner's internals are tools/checks' (tests/test_parts.py there); this
file holds only this repo's use of it."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests.helpers import ROOT, Case

PARTS = ROOT / "check.parts.json"
RUNNER = ROOT / "devtools" / "parts.py"
# The validators set these while they run a repo's suite, and answer UNCHECKED to a
# run nested inside them: their guard, their decision; a nested test skips, saying so.
GUARDS = ("CHECKS_CHECK_JSON_ACTIVE", "CHECKS_CHECK_PARTIAL_ACTIVE")


def _checks_cli():
    """tools/checks/checks in the workspace around this tool, or None (a lone clone)."""
    for top in ROOT.parents:
        cli = top / "tools" / "checks" / "checks"
        if os.access(cli, os.X_OK):
            return cli
    return None


CHECKS_CLI = _checks_cli()
LONE = "no shared checks CLI in a workspace around this tool (a lone clone)"


def parts():
    return json.loads(PARTS.read_text())["parts"]


HOOKS = ROOT / ".claude" / "hooks"


def hook_parts():
    """(name, run) of the part each hook in .claude/hooks should have: hooks.NAME runs
    `./dev.sh hooks NAME.sh`, that hook and its test alone (td-82)."""
    return sorted((f"hooks.{h.stem}", f"./dev.sh hooks {h.name}")
                  for h in HOOKS.glob("*.sh") if not h.name.startswith("test-"))


def gates():
    """dev.sh's GATES, the one list of its gates (tests/test_docs.py holds it to the case arms)."""
    text = (ROOT / "dev.sh").read_text()
    return re.search(r"^GATES=\(([^)]*)\)", text, re.M).group(1).split()


class PartsFile(unittest.TestCase):
    def test_the_runner_validates_it(self):
        p = subprocess.run(["python3", str(RUNNER), "validate", str(PARTS)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(p.stdout.startswith("ok: "), p.stdout)

    def test_one_part_per_test_module_and_none_for_a_gone_one(self):
        modules = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))
        want = [(f"test.{m[len('test_'):]}", f"python3 -m unittest tests.{m}", [f"tests/{m}.py"])
                for m in modules]
        got = [(p["name"], p["run"], p["files"]) for p in parts() if p["name"].startswith("test.")]
        self.assertEqual(sorted(got), want)

    def test_the_gates_follow_the_tests_in_dev_sh_order(self):
        ps = parts()
        names = [p["name"] for p in ps]
        tests = [n for n in names if n.startswith("test.")]
        self.assertEqual(names[:len(tests)], tests, "the test modules come first")
        self.assertEqual(gates()[0], "test", "GATES opens with the unit tests, which the test.* parts are")
        want = []
        for g in gates()[1:]:
            want += hook_parts() if g == "hooks" else [(g, f"./dev.sh {g}")]
        self.assertEqual([(p["name"], p["run"]) for p in ps[len(tests):]], want)

    def test_one_hooks_part_per_hook_and_every_hook_test_has_its_hook(self):
        # td-82: the hooks gate ran every hook test in one part, which overran its
        # timeout under load; each hook now has a part, and together they cover what
        # the bare `./dev.sh hooks` does: every hook, and every test-*.sh beside one.
        got = sorted((p["name"], p["run"]) for p in parts() if p["name"].startswith("hooks"))
        self.assertEqual(got, hook_parts())
        self.assertGreater(len(got), 1, "one part per hook, not one part for all")
        self.assertNotIn("hooks", [p["name"] for p in parts()], "no part runs every hook test")
        names = {h.name for h in HOOKS.glob("*.sh")}
        orphans = sorted(t for t in names if t.startswith("test-") and t[len("test-"):] not in names)
        self.assertEqual(orphans, [], "a hook test with no hook is run by no part")

    def test_progress_is_ignored_by_git(self):
        p = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", ".progress/check.json"])
        self.assertEqual(p.returncode, 0, ".progress/ must be in .gitignore")


CANNED = {"parts": [
    {"name": "p_ok", "run": "echo fine", "files": ["a.txt"], "timeout_s": 30},
    {"name": "p_bad", "run": "echo 'FAIL b.txt:3 broken on purpose'; exit 1", "files": ["b.txt"], "timeout_s": 30},
]}
UNCHECKED = {"parts": [
    {"name": "p_ok", "run": "echo fine", "files": ["a.txt"], "timeout_s": 30},
    {"name": "p_lone", "run": "echo 'UNCHECKED: no sibling repo here'; exit 3", "files": ["b.txt"], "timeout_s": 30},
]}


def wired_copy(d, suite=CANNED):
    """dev.sh and the runner, as shipped, with canned parts as its own check.parts.json."""
    (d / "devtools").mkdir(parents=True)
    shutil.copy(ROOT / "dev.sh", d / "dev.sh")
    shutil.copy(RUNNER, d / "devtools" / "parts.py")
    (d / "check.parts.json").write_text(json.dumps(suite))
    (d / "a.txt").write_text("a\n")
    (d / "b.txt").write_text("1\n2\n3\n")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    return d


def dev(d, *args):
    """The copy's dev.sh, as a user runs it: no suite, progress file or check of the caller's."""
    env = {k: v for k, v in os.environ.items() if k not in ("CHECK_PARTS", "PROGRESS_FILE", "TODO_DEV_CHECK")}
    return subprocess.run(["./dev.sh", *args], cwd=d, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env=env, timeout=120)


class Wiring(Case):
    def setUp(self):
        super().setUp()
        self.d = wired_copy(self.tmp / "copy")

    def test_text_run_says_n_of_m_and_names_the_failure(self):
        r = dev(self.d, "check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        last = r.stdout.strip().splitlines()[-1]
        self.assertIn("1 of 2 passed", last)
        self.assertIn("failed: p_bad", last)

    def test_json_is_one_document_one_check_per_part(self):
        r = dev(self.d, "check", "--json")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1, r.stdout)
        doc = json.loads(r.stdout)
        self.assertIs(doc["ok"], False)
        self.assertEqual([(c["name"], c["status"]) for c in doc["checks"]], [("p_ok", "ok"), ("p_bad", "fail")])

    def test_test_part_runs_that_part_alone(self):
        r = dev(self.d, "test", "p_ok")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("only: running 1 of 2: p_ok", r.stdout)
        self.assertNotIn("p_bad (", r.stdout)

    def test_resume_reruns_only_what_did_not_pass(self):
        dev(self.d, "check")
        r = dev(self.d, "check", "--resume")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("resume: re-running 1 of 2: p_bad"), r.stdout)
        (self.d / "b.txt").write_text("fixed\n")
        (self.d / "check.parts.json").write_text(json.dumps(CANNED).replace("exit 1", "exit 0"))
        r = dev(self.d, "check", "--resume")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 of 2 passed", r.stdout.strip().splitlines()[-1])


class Unchecked(Case):
    """The runner exits 0 when a part only said UNCHECKED (exit 3); this repo's check
    exits 3 then, so a part that could not run here is never green by exit code."""

    def setUp(self):
        super().setUp()
        self.d = wired_copy(self.tmp / "copy", UNCHECKED)

    def test_text_run_exits_3_and_names_it(self):
        r = dev(self.d, "check")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        last = r.stdout.strip().splitlines()[-1]
        self.assertIn("unchecked: p_lone", last)
        self.assertNotIn("failed:", last)

    def test_json_run_exits_3_and_the_part_is_unchecked(self):
        r = dev(self.d, "check", "--json")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        doc = json.loads(r.stdout)
        self.assertEqual([(c["name"], c["status"]) for c in doc["checks"]], [("p_ok", "ok"), ("p_lone", "unchecked")])

    def test_a_part_only_left_out_is_not_unchecked_by_exit_code(self):
        for args in (("check", "--only", "p_ok"), ("check", "--json", "--only", "p_ok")):
            with self.subTest(args):
                r = dev(self.d, *args)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_fail_beside_an_unchecked_is_a_fail(self):
        suite = {"parts": UNCHECKED["parts"] + [CANNED["parts"][1]]}
        (self.d / "check.parts.json").write_text(json.dumps(suite))
        for args in (("check",), ("check", "--json")):
            with self.subTest(args):
                self.assertEqual(dev(self.d, *args).returncode, 1)


class Contract(Case):
    def one(self, check, repo, env=None):
        r = subprocess.run([str(CHECKS_CLI), "one", check, str(repo), "--json"], env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600)
        results = json.loads(r.stdout)["results"]
        self.assertEqual([x["check"] for x in results], [check], r.stdout)
        if results[0]["status"] == "unchecked" and any(os.environ.get(g) for g in GUARDS):
            self.skipTest(f"nested inside a {check} run, which answers UNCHECKED here by design")
        return results[0]["status"], results[0]["lines"]

    @unittest.skipIf(CHECKS_CLI is None, LONE)
    def test_the_json_passes_the_shared_validator(self):
        # The copy's parts are canned stubs, not this repo's tests, so its check cannot
        # recurse: inside ./dev.sh check, TODO_DEV_CHECK would make dev.sh refuse the
        # bare run (exit 2, nothing on stdout) and this would test the guard instead.
        env = {k: v for k, v in os.environ.items() if k != "TODO_DEV_CHECK"}
        self.assertEqual(self.one("check-json", wired_copy(self.tmp / "copy"), env), ("ok", []))

    @unittest.skipIf(CHECKS_CLI is None, LONE)
    def test_this_repo_fails_in_parts(self):
        status, lines = self.one("check-partial", ROOT)
        self.assertEqual(status, "ok", lines)


if __name__ == "__main__":
    unittest.main()
