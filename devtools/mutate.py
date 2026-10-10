#!/usr/bin/env python3
"""Prove each gate can fail: break it once in a throwaway copy, see red.

  devtools/mutate.py [mutants.json] [--only ID] [--work DIR]

--work puts the copies under DIR instead of .mutants/ (the tests use it, so a
run of their own is told apart from any other run). Any other argument is
refused: an unknown flag used to fall through to a full run.

A run removes its copies however it ends: normally, on an exception, on ^C,
and on SIGTERM, which stops the commands still running (their whole process
group) and lets the cleanup run. Only SIGKILL leaves a run-*/ folder behind.

Each mutant names one or more edits (a file, an exact string that must occur
exactly once -- otherwise the mutant is STALE and fails the run: the code moved
and the proof with it -- and its replacement) and the command that must go red.
A gate guarded twice over (a refusal in the CLI and again in the store) needs
both guards broken to show the gate itself can fail, hence several edits.
Every command is first run on an unmutated copy and must be green, so the red
is the mutant's doing (the counterfactual), not a broken baseline.

Copies are separate folders run as separate processes, in parallel; every
mutant's outcome is reported, never just the first failure. Each copy is a
fresh `git init` under .mutants/ inside this repo, gitignored and removed
afterwards: the shared hooks' own tests find their sibling repos by walking up,
so a copy in the system temp folder would fail for its location, not for the
mutant. Nothing else in the working tree is touched.

Adapted from tools/setup/devtools/mutate.py (the `edits` list is the addition);
TODO.md records the duplicate as a shared-component candidate.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORE = shutil.ignore_patterns(".git", ".mutants", "__pycache__", "*.pyc")
WORK = ROOT / ".mutants"
USAGE = "usage: devtools/mutate.py [mutants.json] [--only ID] [--work DIR]"
# The commands running now, so SIGTERM can stop them; STOP refuses new ones after it.
PROCS, LOCK, STOP = set(), threading.Lock(), threading.Event()


def halt(*_):
    """Refuse new commands and stop the running ones (each its own process group)."""
    with LOCK:
        STOP.set()
        procs = list(PROCS)
    for p in procs:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except OSError:
            pass


def stop(signum, _frame):
    halt()
    raise SystemExit(128 + signum)  # unwinds into main's finally, which removes the copies


def copy_tree(dest: Path) -> Path:
    shutil.copytree(ROOT, dest, ignore=IGNORE, symlinks=True)
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    return dest


def run(cmd, cwd):
    with LOCK:
        if STOP.is_set():
            return 143, ["stopped before it started"]
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)  # its own group: SIGTERM reaches its children too
        PROCS.add(p)
    out, err = p.communicate()
    with LOCK:
        PROCS.discard(p)
    return p.returncode, (out + err).strip().splitlines()[-3:]


def baseline(cmd, tmp: Path, i: int):
    d = copy_tree(tmp / f"base{i}")
    code, tail = run(cmd, d)
    return cmd, code, tail


def edits_of(m):
    return m.get("edits") or [{"file": m["file"], "old": m["old"], "new": m["new"]}]


def mutant(m, tmp: Path):
    d = copy_tree(tmp / m["id"])
    for e in edits_of(m):
        f = d / e["file"]
        text = f.read_text()
        n = text.count(e["old"])
        if n != 1:
            return m["id"], "STALE", f"{e['file']}: the string to replace occurs {n} times, not once"
        mode = f.stat().st_mode
        f.chmod(mode | 0o200)  # TODO.md is rendered read-only
        f.write_text(text.replace(e["old"], e["new"]))
        f.chmod(mode)
    code, tail = run(m["run"], d)
    if code == 0:
        return m["id"], "SURVIVED", f"{' '.join(m['run'])} stayed green with the gate broken"
    return m["id"], "red", f"{' '.join(m['run'])} -> exit {code}"


def parse(argv):
    """(mutants.json, --only, --work) or None for an argument it does not know."""
    path, opts, rest = None, {"--only": None, "--work": None}, list(argv)
    while rest:
        a = rest.pop(0)
        if a in opts and rest and opts[a] is None and not rest[0].startswith("-"):
            opts[a] = rest.pop(0)
        elif not a.startswith("-") and path is None:
            path = Path(a)
        else:
            return None
    return path or ROOT / "devtools" / "mutants.json", opts["--only"], opts["--work"]


def main(argv):
    parsed = parse(argv)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    path, want, work = parsed
    work = Path(work).resolve() if work else WORK
    mutants = json.loads(path.read_text())["mutants"]
    if want is not None:
        mutants = [m for m in mutants if m["id"] == want]
    if not mutants:
        print("mutants: none loaded; nothing proven")
        return 1
    ids = [m["id"] for m in mutants]
    if len(ids) != len(set(ids)):
        print("mutants: duplicate ids")
        return 1
    work.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="run-", dir=work))
    signal.signal(signal.SIGTERM, stop)
    pool = ThreadPoolExecutor(max_workers=6)
    try:
        cmds = list({tuple(m["run"]): None for m in mutants})
        bases = list(pool.map(lambda a: baseline(list(a[1]), tmp, a[0]), enumerate(cmds)))
        bad_base = [(c, code, tail) for c, code, tail in bases if code != 0]
        for c, code, tail in bad_base:
            print(f"  BASELINE-RED  {' '.join(c)} exits {code} unmutated: {' | '.join(tail)}")
        results = list(pool.map(lambda m: mutant(m, tmp), mutants))
    finally:
        signal.signal(signal.SIGTERM, halt)  # a second SIGTERM must not cut the cleanup short
        # Queued copies are cancelled; a copy mid-way finishes, and its command is refused once STOP is set.
        pool.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            work.rmdir()  # only when no other run is using it
        except OSError:
            pass
    for mid, verdict, detail in results:
        if verdict != "red":
            print(f"  {verdict:<9} {mid}: {detail}")
    red = sum(v == "red" for _, v, _ in results)
    failed = len(results) - red + len(bad_base)
    print(f"mutants: {red} of {len(results)} red" + (f", {failed} problem(s)" if failed else ", every gate shown able to fail"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
