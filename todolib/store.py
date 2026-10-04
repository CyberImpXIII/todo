"""One repo's store: todo.json (open items) and todo-history.json (closed items).

Every write goes through `Store.save()` (atomic: a temp file, then rename) under
`Store.lock()` (an flock on the repo folder), so two sessions writing the same
store serialise instead of losing an update. Nothing else in todolib writes a
store file; tests/test_store.py audits that.
"""
import contextlib
import datetime
import fcntl
import json
import os
import re
import subprocess
from pathlib import Path

from .vocab import VOCAB

STORE_FILE = "todo.json"
HISTORY_FILE = "todo-history.json"
RENDER_FILE = "TODO.md"
HISTORY_RENDER_FILE = "TODO-HISTORY.md"
FORMAT = 1
STORE_KEYS = ["format", "repo", "prefix", "next", "render_gate_from", "hand_edits", "items"]
HISTORY_KEYS = ["format", "repo", "items"]
PREFIX_RE = re.compile(r"^[a-z][a-z0-9]{0,7}$")
ID_RE = re.compile(r"^([a-z][a-z0-9]{0,7})-([0-9]+)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# How deep below the scan root a repo's todo.json is looked for (claudeTest/x/y is depth 2).
SCAN_DEPTH = 3
SCAN_PRUNE = {"node_modules", "__pycache__", "fixtures", "venv"}


class TodoError(Exception):
    """A refusal: printed as is, exit 1. Never a traceback for a user error."""


def today():
    """Today, or TODO_TODAY (YYYY-MM-DD) for tests and reproducible runs."""
    forced = os.environ.get("TODO_TODAY")
    if forced:
        if not DATE_RE.match(forced):
            raise TodoError(f"TODO_TODAY={forced!r} is not YYYY-MM-DD")
        return forced
    return datetime.date.today().isoformat()


def add_days(date, days):
    return (datetime.date.fromisoformat(date) + datetime.timedelta(days=days)).isoformat()


def id_number(item_id):
    m = ID_RE.match(item_id or "")
    return int(m.group(2)) if m else -1


def new_item(**values):
    """An item with every declared field, in declared order; unset ones null."""
    unknown = set(values) - set(VOCAB.field_names())
    if unknown:
        raise ValueError(f"undeclared field(s): {sorted(unknown)}")
    return {name: values.get(name) for name in VOCAB.field_names()}


def never_scanned(name):
    """A folder or repo name the scan never enters: a hidden one. The delegation
    layer is one, and todo never reads it (PLAN-todo-tool.md §8 decision 4), so a
    report to such a name never pairs and no store may take one as its repo."""
    return str(name or "").startswith(".")


def git_toplevel(path):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path,
                           capture_output=True, text=True)
    except OSError:
        return None
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_atomic(path, text, readonly=False):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text)
    os.chmod(tmp, 0o444 if readonly else 0o644)
    os.replace(tmp, path)


class Store:
    def __init__(self, folder):
        self.dir = Path(folder).resolve()
        self.path = self.dir / STORE_FILE
        self.history_path = self.dir / HISTORY_FILE
        self.render_path = self.dir / RENDER_FILE
        self.data = None
        self.history = None

    # -- reading -----------------------------------------------------------
    def exists(self):
        return self.path.is_file()

    def load(self):
        if not self.exists():
            raise TodoError(f"no {STORE_FILE} in {self.dir}: run `todo init --prefix XX` there first")
        try:
            self.data = json.loads(self.path.read_text())
        except ValueError as e:
            raise TodoError(f"{self.path} does not parse: {e}")
        if self.history_path.is_file():
            try:
                self.history = json.loads(self.history_path.read_text())
            except ValueError as e:
                raise TodoError(f"{self.history_path} does not parse: {e}")
        else:
            self.history = None
        return self

    @property
    def repo(self):
        return self.data["repo"]

    @property
    def prefix(self):
        return self.data["prefix"]

    @property
    def items(self):
        return self.data["items"]

    @property
    def closed(self):
        return (self.history or {}).get("items", [])

    def find(self, item_id):
        """(item, "store"|"history") or (None, None)."""
        for it in self.items:
            if it.get("id") == item_id:
                return it, "store"
        for it in self.closed:
            if it.get("id") == item_id:
                return it, "history"
        return None, None

    def owns(self, item_id):
        m = ID_RE.match(item_id or "")
        return bool(m) and m.group(1) == self.prefix

    # -- writing -----------------------------------------------------------
    @contextlib.contextmanager
    def lock(self):
        fd = os.open(self.dir, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield self
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def init(self, prefix, repo):
        if self.exists():
            raise TodoError(f"{self.path} already exists")
        if not PREFIX_RE.match(prefix):
            raise TodoError(f"prefix {prefix!r}: 1-8 characters, a lowercase letter then letters or digits")
        if not repo or "/" in repo:
            raise TodoError(f"repo name {repo!r}: a folder-style name, no slash")
        if never_scanned(repo):
            raise TodoError(f"repo name {repo!r} is hidden: the scan never enters a hidden folder, "
                            "so no report could ever pair with this store; pass --repo NAME")
        if self.history_path.exists():
            raise TodoError(f"{self.history_path} exists without {STORE_FILE}; refusing to start over a history")
        self.data = {"format": FORMAT, "repo": repo, "prefix": prefix, "next": 1,
                     "render_gate_from": today(), "hand_edits": [], "items": []}
        self.history = {"format": FORMAT, "repo": repo, "items": []}
        self.save()

    def allocate(self):
        n = self.data["next"]
        taken = {it.get("id") for it in self.items} | {it.get("id") for it in self.closed}
        while f"{self.prefix}-{n}" in taken:
            n += 1
        self.data["next"] = n + 1
        return f"{self.prefix}-{n}"

    def save(self):
        """History first: an interrupted close leaves the id in both files,
        which `check` reports and `todo done ID` finishes; never in neither.
        A missing history is never written back empty."""
        if self.history is None:
            raise TodoError(f"{self.history_path} is missing; refusing to write a store without its history")
        self.data["items"].sort(key=lambda it: id_number(it.get("id")))
        write_atomic(self.history_path, dump(self.history))
        write_atomic(self.path, dump(self.data))


def store_dir_for(cwd, explicit=None):
    """The store a command acts on: -C DIR, else the git repo holding cwd,
    else the nearest folder above cwd that holds a todo.json, else cwd."""
    if explicit:
        return Path(explicit).resolve()
    cwd = Path(cwd).resolve()
    top = git_toplevel(cwd)
    if top:
        return top.resolve()
    for d in [cwd, *cwd.parents]:
        if (d / STORE_FILE).is_file():
            return d
    return cwd


def scan_root(store_dir, explicit=None):
    """Where `todo repos` looks: --root DIR; else a store outside any git repo is
    its own root (a workspace store); else the nearest folder above the repo that
    is in no git repo and holds a todo.json or a CLAUDE.md; else the repo's parent."""
    if explicit:
        return Path(explicit).resolve()
    store_dir = Path(store_dir).resolve()
    if not git_toplevel(store_dir):
        return store_dir
    for d in store_dir.parents:
        if git_toplevel(d):
            continue
        if (d / STORE_FILE).is_file() or (d / "CLAUDE.md").is_file():
            return d
    return store_dir.parent


def scan_stores(root, depth=SCAN_DEPTH):
    """Folders under root holding a todo.json: the root itself, and any git
    repo (a folder with .git) down to `depth`. Hidden folders, fixtures and
    dependency folders are never entered."""
    root = Path(root).resolve()
    found = []
    if (root / STORE_FILE).is_file():
        found.append(root)
    for dirpath, dirnames, _ in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        level = 0 if str(rel) == "." else len(rel.parts)
        dirnames[:] = sorted(d for d in dirnames
                             if not never_scanned(d) and d not in SCAN_PRUNE) if level < depth else []
        d = Path(dirpath)
        if d != root and (d / ".git").exists() and (d / STORE_FILE).is_file():
            found.append(d)
    return found


class Workspace:
    """The current store plus every store the scan finds, loaded once."""

    def __init__(self, current, root):
        self.current = current
        self.root = Path(root)
        self.stores = [current]
        self.errors = []
        seen = {current.dir}
        for d in scan_stores(root):
            if d.resolve() in seen:
                continue
            seen.add(d.resolve())
            try:
                self.stores.append(Store(d).load())
            except TodoError as e:
                self.errors.append(str(e))

    def by_repo(self, name):
        hits = [s for s in self.stores if s.data and s.repo == name]
        return hits[0] if len(hits) == 1 else None

    def find(self, item_id):
        """(item, where, store) across every store, open or closed."""
        for s in self.stores:
            if s.owns(item_id):
                it, where = s.find(item_id)
                if it:
                    return it, where, s
        return None, None, None

    def everything(self):
        """(item, where, store) for every item in every store and history."""
        for s in self.stores:
            for it in s.items:
                yield it, "store", s
            for it in s.closed:
                yield it, "history", s
