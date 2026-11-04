"""`todo rename-repo OLD NEW`: one store's key, and every record that names it, in
every scanned store and history, in one pass (PLAN-architecture.md §13.1 step 3).
No old spelling is kept anywhere: a rename rewrites the records, it does not add
an alias (Jacob, 2026-10-31: "frontloading the work so that it is correct should
always be prioritized over building exceptions to facilitate a change").

What a key names: the store's own `repo` (todo.json, todo-history.json,
todo-records.json), each item's `repo`, and each report's `reported_to.repo`,
open or closed, and each project row's `repos` (todolib/tables.py). `plan` refuses before anything is written; the CLI then takes
each store under its lock and saves it, so every write is in its write log."""
import json
import re

from . import names as naming
from .store import TodoError

KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
FIELDS = ("key", "items", "history", "projects")


def services_name(store_dir):
    """The repo's own name, `services.json` `name`, or None where it has none."""
    p = store_dir / "services.json"
    if not p.is_file():
        return None
    try:
        name = json.loads(p.read_text()).get("name")
    except ValueError as e:
        raise TodoError(f"{p} does not parse: {e}")
    return name if isinstance(name, str) and name else None


def _hits(items, old):
    n = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("repo") == old:
            n += 1
        rt = it.get("reported_to")
        if isinstance(rt, dict) and rt.get("repo") == old:
            n += 1
    return n


def count(store, old):
    """{key, items, history}: how many fields of this store name `old`."""
    return {"key": int(store.repo == old), "items": _hits(store.items, old), "history": _hits(store.closed, old),
            "projects": sum(old in (p.get("repos") or []) for p in store.projects if isinstance(p, dict))}


def plan(ws, old, new):
    """[(store, counts)] for every store that would change, or a TodoError naming
    why nothing may: an unreadable store, more than one store keyed OLD, a store
    already keyed NEW, or a `services.json` whose name is not NEW (one name per
    location: the key is the repo's own name). With no store keyed OLD the rename is
    of fields alone (an item's `repo` or `reported_to.repo` that names a location by
    a path or an old key, PLAN-architecture.md §13.1 G3): then NEW must be a
    location's name in the names file handed, and something must name OLD."""
    if old == new:
        raise TodoError("OLD and NEW are the same name")
    if not KEY.match(new):
        raise TodoError(f"{new!r} is not a repo key: letters, digits, _ . and -, not starting with a dot")
    if ws.errors:
        raise TodoError("a store could not be read, so nothing is renamed: " + "; ".join(ws.errors))
    owners = [s for s in ws.stores if s.data and s.repo == old]
    if len(owners) > 1:
        raise TodoError(f"{len(owners)} stores have the key {old!r}; rename-repo renames one store's key "
                        "(todo repos lists the stores and their keys)")
    if owners:
        if any(s.data and s.repo == new for s in ws.stores):
            raise TodoError(f"a store already has the key {new!r}")
        own = services_name(owners[0].dir)
        if own is not None and own != new:
            raise TodoError(f"{owners[0].dir / 'services.json'} names this repo {own!r}, so its key is {own!r} "
                            f"(one name per location, PLAN-architecture.md §13.1), not {new!r}")
    else:
        nm = naming.CURRENT
        if nm is None:
            raise TodoError(f"no store is keyed {old!r}: a rename of fields alone needs the names file "
                            "(--names FILE or TODO_NAMES), so that NEW is a location's name")
        why = nm.target_problem(new)
        if why:
            raise TodoError(f"NEW {new!r}: {why}")
    out = []
    for s in ws.stores:
        c = count(s, old)
        if any(c.values()):
            out.append((s, c))
    if not owners and not out:
        raise TodoError(f"nothing names {old!r}: no store is keyed so, and no item field holds it")
    return out


def _rewrite(items, old, new):
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("repo") == old:
            it["repo"] = new
        rt = it.get("reported_to")
        if isinstance(rt, dict) and rt.get("repo") == old:
            rt["repo"] = new


def apply(store, old, new):
    """Rewrite this loaded store's fields in memory; the caller saves it."""
    for doc in (store.data, store.history, store.records):
        if isinstance(doc, dict) and doc.get("repo") == old:
            doc["repo"] = new
    _rewrite(store.items, old, new)
    _rewrite(store.closed, old, new)
    if isinstance(store.records, dict):
        _rewrite(store.records.get("runs", {}).values() if isinstance(store.records.get("runs"), dict) else [], old, new)
    for p in store.projects:
        if isinstance(p, dict) and isinstance(p.get("repos"), list):
            p["repos"] = [new if r == old else r for r in p["repos"]]


def renamed(item, renames):
    """`item` with every logged key rename applied, oldest first: what a committed
    history entry must now read as, and nothing else (checks.check_history)."""
    it = json.loads(json.dumps(item))
    for r in renames:
        if it.get("repo") == r["old"]:
            it["repo"] = r["new"]
        rt = it.get("reported_to")
        if isinstance(rt, dict) and rt.get("repo") == r["old"]:
            rt["repo"] = r["new"]
    return it


def describe(store, c):
    parts = (["key"] if c["key"] else []) + [f"{c['items']} item field(s)"] * bool(c["items"]) \
        + [f"{c['history']} history field(s)"] * bool(c["history"]) \
        + [f"{c['projects']} project row(s)"] * bool(c["projects"])
    return f"  {store.repo} ({store.dir}): " + ", ".join(parts)
