#!/usr/bin/env python3
"""The direction audit: no file in this repo reads the delegation layer or names a
roster agent (PLAN-todo-tool.md §8 decision 4). Terms live in devtools/audit.json.

  devtools/audit.py [ROOT]      exit 1 and one line per hit; `ok` line when clean
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
            for rx, why in pats:
                m = rx.search(line)
                if m:
                    hits.append(f"  FAIL  audit  {rel}:{n}: {m.group(0)!r} ({why})")
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
