#!/usr/bin/env python3
"""Judge one `checks run . --json` (tools/checks) for ./dev.sh checks (td-12).

  checks run . --json --names ... | devtools/checks_gate.py EXIT_CODE

Green only when the run printed its report, nothing in it is fail or error,
no-roster ran here AND ran its names half (ok, never unchecked: without the
names it proves half of what it says), and the exit code agrees with the
report. Other checks may be unchecked (no node.json, no cli.json: the design
of that tool); they are named in the summary line. Exit 0 green, 1 red.
"""
import json
import sys

RED = ("fail", "error")
MUST_RUN = "no-roster"
SHOWN = 6  # finding lines shown per red check; the rest are counted


def judge(text, code):
    """(ok, lines): lines are what the gate prints, two-space indented."""
    try:
        report = json.loads(text)
        results = report["results"]
        statuses = {r["check"]: (r["status"], r.get("lines") or []) for r in results}
    except (ValueError, KeyError, TypeError):
        first = (text.strip().splitlines() or ["(nothing)"])[0][:200]
        return False, [f"  FAIL  checks: no report from `checks run` (exit {code}): {first}"]
    out = []
    for name, (status, lines) in statuses.items():
        if status in RED:
            out.append(f"  FAIL  checks: {name} {status}")
            out += [f"          {ln}" for ln in lines[:SHOWN]]
            if len(lines) > SHOWN:
                out.append(f"          ({len(lines) - SHOWN} more)")
    roster = statuses.get(MUST_RUN)
    if roster is None:
        out.append(f"  FAIL  checks: {MUST_RUN} did not run here (it applies to repos under tools/): "
                   "nothing proved this repo reads no roster")
    elif roster[0] == "unchecked":
        out.append(f"  FAIL  checks: {MUST_RUN} unchecked ({'; '.join(roster[1]) or 'no reason given'}): "
                   "the roster names were not passed")
    tool_red = any(s in RED for s, _ in statuses.values())  # what checks itself calls red
    if tool_red == (code == 0):
        out.append(f"  FAIL  checks: exit {code} disagrees with the report ({'red' if tool_red else 'green'})")
    red = bool(out)
    if red:
        return False, out
    ok = [n for n, (s, _) in statuses.items() if s == "ok"]
    unchecked = [n for n, (s, _) in statuses.items() if s == "unchecked"]
    tail = f", {len(unchecked)} unchecked ({', '.join(unchecked)})" if unchecked else ""
    return True, [f"  ok    checks: {len(ok)} ok{tail}; {MUST_RUN} ok with the roster names"]


def main(argv):
    if len(argv) != 1 or not argv[0].lstrip("-").isdigit():
        print("usage: checks run . --json --names ... | devtools/checks_gate.py EXIT_CODE", file=sys.stderr)
        return 2
    ok, lines = judge(sys.stdin.read(), int(argv[0]))
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
