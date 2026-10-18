"""The readers that stop the switch to todo.db (PLAN-todo-tool.md §10.6, "Before
the switch: every direct reader"): every line, in any file under the scan root
outside this tool, that names one of the store's JSON files by name. Code that
opens the file, a test that plants one, a guard's list of store names and a
config that excludes them all break or go stale when the files go, so each is
listed; the switch waits until none is left.

What is not read, and why:
- this tool's own folder: it is the CLI, and moves with the switch;
- Markdown (`*.md`): prose, plans and rendered TODO.md files, which name the
  files without reading them;
- the store files themselves (item prose naming them);
- hidden folders: todo never reads the delegation layer (PLAN-todo-tool.md §8
  decision 4), so readers there are listed by that layer's owner, and the scan
  says so rather than reporting them clean;
- dependency and cache folders, and files that are not text.
A file over MAX_BYTES is not read either, and is listed as skipped, never passed.
"""
import os
import re
from pathlib import Path

from .store import HISTORY_FILE, RECORDS_FILE, STORE_FILE, never_scanned

NAMES = [STORE_FILE, HISTORY_FILE, RECORDS_FILE]
NAME_RE = re.compile(r"(?<![\w.-])(" + "|".join(re.escape(n) for n in NAMES) + r")(?![\w-])")
PRUNE = {"node_modules", "__pycache__", "venv"}
NOT_READ_SUFFIXES = {".md"}
MAX_BYTES = 2_000_000
TOOL_DIR = Path(__file__).resolve().parent.parent
LINE_WIDTH = 160


def scan(root, own=TOOL_DIR):
    """{hits: [{path, line, text}], skipped: [{path, why}], files} under root,
    sorted by path then line. own: the folder not read (this tool's)."""
    root, own = Path(root).resolve(), Path(own).resolve()
    hits, skipped, files = [], [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        dirnames[:] = sorted(n for n in dirnames
                             if not never_scanned(n) and n not in PRUNE and (d / n).resolve() != own)
        for name in sorted(filenames):
            p = d / name
            if never_scanned(name) or name in NAMES or p.suffix in NOT_READ_SUFFIXES or not p.is_file():
                continue
            rel = os.path.relpath(p, root)
            if p.stat().st_size > MAX_BYTES:
                skipped.append({"path": rel, "why": f"over {MAX_BYTES} bytes"})
                continue
            try:
                raw = p.read_bytes()
            except OSError as e:
                skipped.append({"path": rel, "why": str(e)})
                continue
            if b"\0" in raw[:8192]:
                continue  # not text
            files += 1
            for n, text in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
                if NAME_RE.search(text):
                    hits.append({"path": rel, "line": n, "text": text.strip()[:LINE_WIDTH]})
    return {"hits": hits, "skipped": skipped, "files": files}


def summary(found):
    paths = {h["path"] for h in found["hits"]}
    return (f"{len(found['hits'])} lines in {len(paths)} files outside this tool name "
            f"{', '.join(NAMES)} (hidden folders not read: their owner lists those)")
