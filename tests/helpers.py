"""Shared test plumbing: throwaway workspaces and the CLI run as a subprocess,
exactly as a user runs it, with the date pinned (TODO_TODAY)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from todolib.store import HISTORY_FILE, STORE_FILE, sealed

ROOT = Path(__file__).resolve().parent.parent
TODO = ROOT / "todo"
FIXTURES = ROOT / "tests" / "fixtures"
TODAY = "2026-10-04"


def workspace_file(name):
    """A workspace file (a plan) above this repo, or None in a fresh clone. Walks up
    rather than fixing `../..`, so a copy of the repo deeper down (devtools/mutate.py
    runs the tests in one) still finds it, and a mutant of a plan-backed gate is
    not a skipped test that passes."""
    for d in ROOT.parents:
        if (d / name).is_file():
            return d / name
    return None


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "user.name", "todo tests")
    return path


def git_commit(path, message="test"):
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", message)


class Case(unittest.TestCase):
    """A workspace folder (not a repo, holding a CLAUDE.md, like the real one)
    with repos made on demand."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="todo-test-"))
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        (self.ws / "CLAUDE.md").write_text("workspace\n")

    def tearDown(self):
        for p in self.tmp.rglob("*"):
            if p.is_file():
                os.chmod(p, 0o644)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def todo(self, *args, cwd=None, today=TODAY, ok=True, env=None):
        base = {k: v for k, v in os.environ.items() if k != "TODO_ROOT"}  # never the caller's
        env = dict(base, TODO_TODAY=today, **(env or {}))
        r = subprocess.run([str(TODO), *map(str, args)], cwd=cwd or self.tmp, env=env,
                           capture_output=True, text=True)
        if ok is True and r.returncode != 0:
            self.fail(f"todo {' '.join(map(str, args))} exited {r.returncode}:\n{r.stdout}{r.stderr}")
        if ok is False and r.returncode == 0:
            self.fail(f"todo {' '.join(map(str, args))} should have failed:\n{r.stdout}")
        return r

    def repo(self, name, prefix, git_init=True):
        d = self.ws / name
        if git_init:
            git_repo(d)
        else:
            d.mkdir(parents=True)
        self.todo("-C", d, "init", "--prefix", prefix)
        return d

    def store(self, d):
        return json.loads((Path(d) / "todo.json").read_text())

    def history(self, d):
        return json.loads((Path(d) / "todo-history.json").read_text())

    def check(self, d, ok=True, today=TODAY):
        return self.todo("-C", d, "check", ok=ok, today=today)

    def assertFails(self, d, gate, text, today=TODAY):
        """check exits 1 AND that gate itself prints a FAIL line holding text: a red
        exit caused by another gate (the render's counts, say) does not count."""
        out = self.check(d, ok=False, today=today).stdout
        hits = [ln for ln in out.splitlines() if ln.split()[:2] == ["FAIL", gate] and text in ln]
        self.assertTrue(hits, f"no 'FAIL {gate}' line holding {text!r} in:\n{out}")
        return out

    def write_json(self, path, data, seal=True):
        """Plant a fixture. A store file is written sealed and read-only, as the CLI
        writes it, so the test exercises its own gate and not the seal gate;
        seal=False writes it as a hand edit would leave it (tests/test_seal.py)."""
        path = Path(path)
        if path.exists():
            os.chmod(path, 0o644)
        is_store = path.name in (STORE_FILE, HISTORY_FILE) and isinstance(data, dict)
        if is_store and seal:
            data = sealed(data)
        path.write_text(json.dumps(data, indent=2) + "\n")
        if is_store and seal:
            os.chmod(path, 0o444)
