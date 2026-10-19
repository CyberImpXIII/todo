"""The practices a brief carries (PLAN-services.md §3 A3, §4 step 7.4; README
"Practices in the brief"): the prose rows of the practice registry that apply to
the item's repo, by id, one line each, and the `practices:` line the agent's
report ends with (vocab.json brief.practices).

The rows are read through the checks tool's `checks practices --json`, never from
its gates.json: that tool's checkslib/practices.py is the registry's one reader.
That verb measures cells; asked for rows alone, it is handed (`--from`, on stdin)
a report of one location with no results, so it runs no check, and only its
`rows` are read. The cells and ratchet of such a report mean nothing and are
never read. Interim until the checks tool serves the rows by a verb of their own
(this repo's TODO.md says which item waits on it).

Every answer is (rows, None) or (None, why). An answer that cannot be read is
never read as "no practice applies": the brief says UNCHECKED instead."""
import json
import subprocess
from pathlib import Path

from . import plans

CHECKS_CLI_NAME = ("checks", "checks")   # <dir>/checks/checks: the checks tool, a sibling of this one
ARGS = ("practices", "--json", "--from", "/dev/stdin")
TIMEOUT = 60
PROSE = "prose"
LIVE = "live"
ALL = "all"
ROW_NEEDS = ("id", "status")             # every row the verb prints
LIVE_NEEDS = ("held", "applies")         # and a live row besides


def resolve_cli(given):
    """(path, None) for the checks CLI, or (None, why): --checks-cli, else
    checks/checks in the first folder above this tool holding one."""
    return plans.resolve_cli(given, CHECKS_CLI_NAME, "checks CLI", "--checks-cli")


def location(root, work_dir, repo):
    """The item's repo as a location the checks tool names: its folder relative to
    the scan root, `.` the root itself. `work_dir` is the folder of the store that
    holds the repo (None when none does); else a repo named by its path under the
    root. (None, why) when neither places it."""
    if not repo:
        return None, "the item names no repo"
    root = Path(root).resolve()
    d = Path(work_dir) if work_dir else root / repo
    if not d.is_dir():
        return None, f"repo {repo} is no store's and no folder under {root}"
    try:
        rel = d.resolve().relative_to(root)
    except ValueError:
        return None, f"repo {repo} ({d}) is outside the scan root {root}"
    return str(rel), None


def rows(cli, loc):
    """(the registry's rows as `checks practices --json` prints them, None) or
    (None, why)."""
    report = json.dumps({"repos": [{"rel": loc, "results": []}]})
    try:
        r = subprocess.run([str(cli), *ARGS], input=report, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"{cli} {' '.join(ARGS[:2])} could not run: {e}"
    try:
        got = json.loads(r.stdout)["rows"]
    except (ValueError, KeyError, TypeError):
        first = (r.stderr.strip().splitlines() or ["(no stderr)"])[0][:200]
        return None, f"`checks {' '.join(ARGS[:2])}` gave no rows (exit {r.returncode}): {first}"
    if not isinstance(got, list) or not got:
        return None, f"`checks {' '.join(ARGS[:2])}` printed no rows (exit {r.returncode})"
    for i, row in enumerate(got):
        if not isinstance(row, dict):
            return None, f"`checks {' '.join(ARGS[:2])}` row #{i} is not an object"
        need = ROW_NEEDS + (LIVE_NEEDS if row.get("status") == LIVE else ())
        missing = [k for k in need if k not in row]
        if missing:
            return None, f"`checks {' '.join(ARGS[:2])}` row #{i} lacks {', '.join(missing)}"
        if "held" in row and not isinstance(row["held"], dict):
            return None, f"`checks {' '.join(ARGS[:2])}` row #{i}: held is not an object"
    return got, None


def applies(row, loc):
    a = row.get("applies")
    return a == ALL or (isinstance(a, list) and loc in a)


def prose_for(all_rows, loc):
    """The live prose rows that apply at loc, in registry order."""
    return [r for r in all_rows if r.get("status") == LIVE and (r.get("held") or {}).get("kind") == PROSE
            and applies(r, loc)]


def one_line(row):
    """`id: must show: <what a justified explanation shows>`, or the words the row
    was handed over with when it says no more."""
    h = row.get("held") or {}
    if h.get("shows"):
        return f"{row['id']}: must show: {h['shows']}"
    return f"{row['id']}: {h.get('text') or '(the row says nothing more)'}"


def brief_lines(given_cli, root, work_dir, repo, words):
    """The brief's practices block, as lines. `words` is vocab.json brief.practices."""
    head = words["heading"]
    loc, why = location(root, work_dir, repo)
    cli = None
    if loc is not None:
        cli, why = resolve_cli(given_cli)
    got = None
    if cli is not None:
        got, why = rows(cli, loc)
    if got is None:
        return [f"{head}: UNCHECKED: {why}. {words['unchecked']}"]
    mine = prose_for(got, loc)
    if not mine:
        return [f"{head}: no prose row of the practice registry applies to {loc}. {words['none_line']}"]
    out = [f"{head} ({len(mine)} prose row(s) of the practice registry that apply to {loc}; "
           f"no check holds them, so your report says how you held each):"]
    out += [f"  {one_line(r)}" for r in mine]
    out.append(f"Report line: {words['report_line']}")
    return out
