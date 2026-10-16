"""`todo repos --status` (PLAN-architecture.md step 5): every git repo the scan finds,
with a store or not, and where each one stands, as todo can see it:

- has_store, and its open_items (null with no store, or one that does not load);
- the last commit: short sha, subject, committer date (null with no commit);
- the uncommitted paths `git status --porcelain` lists: a count, and the first
  DIRTY_LISTED of them;
- whose: always null. Who left a file uncommitted is the git-stamp ledger's to
  say, and todo reads no file of the delegation layer (its own rule).

Read-only, and sorted by path, so the same tree prints the same lines."""
import os
import subprocess
from pathlib import Path

from .store import Store, TodoError, scan_stores

DIRTY_LISTED = 10
SEP = "\x1f"  # between the fields of `git log --format`: never in a sha, a subject or a date


def git(path, *args):
    """(exit, stdout) of git in path; (None, why) when git cannot start."""
    try:
        r = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)
    except OSError as e:
        return None, str(e)
    return r.returncode, r.stdout


def last_commit(path):
    code, out = git(path, "log", "-1", f"--format=%h{SEP}%s{SEP}%cs")
    parts = out.strip().split(SEP) if code == 0 else []
    if len(parts) != 3:
        return None  # no commit yet, or git could not say
    return {"sha": parts[0], "subject": parts[1], "date": parts[2]}


def dirty(path):
    """{count, files} of uncommitted paths, or None when git could not list them."""
    code, out = git(path, "status", "--porcelain", "--untracked-files=all")
    if code != 0:
        return None
    files = [ln[3:] for ln in out.splitlines() if len(ln) > 3]
    return {"count": len(files), "files": files[:DIRTY_LISTED]}


def status(root):
    """One row per repo under root (scan_stores, storeless), sorted by path."""
    root = Path(root).resolve()
    rows = []
    for d in scan_stores(root, storeless=True):
        store, n_open, why = Store(d), None, None
        name = d.name
        if store.exists():
            try:
                store.load()
                name, n_open = store.repo, len(store.items)
            except TodoError as e:
                why = str(e)
        rows.append({"name": name, "path": os.path.relpath(d, root), "has_store": store.exists(), "open_items": n_open,
                     "unreadable": why, "last_commit": last_commit(d), "dirty": dirty(d), "whose": None})
    return sorted(rows, key=lambda r: r["path"])


def lines(rows):
    out = []
    for r in rows:
        held = f"{r['open_items']} items" if r["open_items"] is not None else ("UNREADABLE" if r["unreadable"] else "no store")
        c = r["last_commit"]
        last = f"{c['sha']} {c['date']} {c['subject'][:50]}" if c else "no commit"
        d = r["dirty"]
        dirt = "dirty: unknown" if d is None else (f"{d['count']} uncommitted" if d["count"] else "clean")
        out.append(f"  {r['name']:<20} {held:<10} {dirt:<16} {last}  {r['path']}")
    return out
