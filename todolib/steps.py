"""Jacob's own steps (PLAN-architecture.md §11 S7): an open item of kind
roles.step_kind carries a `done_check`, a shell command that exits 0 once the step
is taken. `todo steps` numbers the open ones; `todo steps --run` runs each check and
closes the step whose check passed, so a step he has taken never sits in prose
looking undone.

A check is judged by its exit status alone, and only three ways: exit 0 is done,
another exit is not done, and a timeout, a kill by a signal or a command that cannot start is unjudged
(None), which `todo steps --run` reports as UNCHECKED (exit 3), never as either.
The shell and the timeout are vocab.json `steps`.
"""
import subprocess

from .vocab import VOCAB

DONE, NOT_DONE = "taken", "not-taken"
DETAIL_CHARS = 200  # how much of a failing check's output a verdict carries


def is_step(it):
    return it.get("kind") == VOCAB.role("step_kind")


def open_steps(store):
    """The store's open steps, in store order: the numbering `todo steps` shows."""
    return [it for it in store.items if is_step(it)]


def run_check(command, cwd):
    """(verdict, detail) for one done_check run in cwd: DONE on exit 0, NOT_DONE on
    another exit (detail: the exit and the start of its output), None when it could
    not be judged (detail: why)."""
    if not isinstance(command, str) or not command.strip():
        return None, "no done_check to run"
    try:
        r = subprocess.run([VOCAB.step_shell, "-c", command], cwd=str(cwd), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=VOCAB.step_timeout)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {VOCAB.step_timeout}s"
    except OSError as e:
        return None, f"could not start {VOCAB.step_shell}: {e.strerror or e}"
    if r.returncode < 0:
        return None, f"killed by signal {-r.returncode} before it finished"
    if r.returncode == 0:
        return DONE, "exit 0"
    said = " ".join((r.stderr or r.stdout or "").split())[:DETAIL_CHARS]
    return NOT_DONE, f"exit {r.returncode}" + (f": {said}" if said else "")
