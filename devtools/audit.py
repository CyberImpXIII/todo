#!/usr/bin/env python3
"""The direction audit: no file in this repo reads the delegation layer or names a
roster agent (PLAN-todo-tool.md §8 decision 4). Terms live in devtools/audit.json.

  devtools/audit.py [ROOT]      exit 1 and one line per hit; `ok` line when clean

`accepted` in audit.json lists single lines that hit and cannot be changed: a line of
the history store is append-only (todo check fails an edited entry against every git
version), so a term written there by mistake stays. Each entry names its file and the
line's exact text (stripped) and why; it exempts that line alone. An entry whose file
is present and holds no such line is itself a FAIL, and so is an accepted line that hits
no term, so an exemption never outlives its line (tests/test_audit.py Accepted).
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def audit(root):
    cfg = json.loads((HERE / "audit.json").read_text())
    pats = [(re.compile(p["re"]), p["why"]) for p in cfg["patterns"]]
    pats += [(re.compile(r"(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])" % re.escape(n), re.I), "names a roster agent")
             for n in cfg["roster_names"]]
    accepted = {(a["file"], a["line"]) for a in cfg.get("accepted", [])}
    used = set()
    hits, scanned = [], 0
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root).as_posix()
        if not f.is_file() or any(rel.startswith(s) or rel == s.rstrip("/") for s in cfg["skip"]) or "__pycache__" in rel:
            continue
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue
        scanned += 1
        for n, line in enumerate(text.splitlines(), 1):
            if (rel, line.strip()) in accepted:
                used.add((rel, line.strip()))
                if not any(rx.search(line) for rx, _ in pats):
                    hits.append(f"  FAIL  audit  {rel}:{n}: an accepted line hits no term (a needless exemption)")
                continue
            for rx, why in pats:
                m = rx.search(line)
                if m:
                    hits.append(f"  FAIL  audit  {rel}:{n}: {m.group(0)!r} ({why})")
    for rel, line in sorted(a for a in accepted - used if (root / a[0]).is_file()):
        hits.append(f"  FAIL  audit  {rel}: an accepted line matches no line there (stale exemption): {line[:80]!r}")
    return hits, scanned


def main(argv):
    root = Path(argv[0]).resolve() if argv else HERE.parent
    hits, scanned = audit(root)
    for h in hits:
        print(h)
    if not hits:
        print(f"  ok    audit: {scanned} files, none reads the delegation layer or names a roster agent")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
