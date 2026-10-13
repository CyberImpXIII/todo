"""`todo blockers` (PLAN-todo-tool.md §10.2 step 1): every open item that is not
dispatchable, across every scanned store, grouped by its root blocker and ranked by
how many items wait behind each root.

One root per item, found in this order, because each later one cannot free an item
an earlier one holds: a report waits on its owner; an item blocked by another waits
on the end of that chain; a waiting-jacob item waits on Jacob (its waits_on); an
item lacking what `todo brief` needs waits on its store's owner to triage it; an
item ready but for approval waits on Jacob's yes. The kinds of root, their
tie-break order and the output bounds are vocab.json `blockers`.

`todo dispatchable` judges the same items (cli.dispatch_view): tests/test_blockers.py
holds every open item to exactly one of the two.
"""
import os

from . import checks, deps
from .store import never_scanned
from .vocab import VOCAB

# What `todo brief` needs set before an item is dispatched (besides a size it can be
# dispatched at, an open status and every blocked_by id closed). cli reads it too.
BRIEF_NEEDS = ("repo", "work", "done_when")


def size_refusal(it):
    """Why an item's size keeps it from being dispatched, or None (PLAN-small-tasks.md
    §2): unsized, it cannot be judged one checkpoint; too big, it is split first."""
    if it.get("size") is None:
        return f"no size (todo edit {it['id']} --size {'|'.join(VOCAB.sizes)})"
    if it["size"] not in VOCAB.ready_sizes:
        return f"size {it['size']}: split it first (todo split {it['id']} TITLE ... --size {'|'.join(VOCAB.ready_sizes)})"
    return None


def is_split(ws, it):
    """True when the item is the split size and has children (open or closed, any
    store): the children carry the work, so ready, dispatchable and blockers leave
    it out, and check passes it. The one test for "already split"."""
    return it.get("size") == VOCAB.split_size and bool(checks.children_of(ws, it["id"]))


def chain_ends(ws, item):
    """(ends, cycle): the open items (or unresolved ids) at the end of every open
    blocked_by chain from item, and a cycle met on the way (a list of ids) or None.
    Each id is visited once, so a cycle is reported, never looped on."""
    ends, seen, cycle = [], set(), None
    stack = [[item["id"], b] for b in reversed(deps.open_blockers(ws, item))]
    while stack:
        path = stack.pop()
        cur = path[-1]
        if cur in path[:-1]:
            cycle = cycle or path[path.index(cur):]
            continue
        if cur in seen:
            continue
        seen.add(cur)
        found = ws.find(cur)[0]
        nxt = deps.open_blockers(ws, found) if found else []
        if not nxt:
            if cur not in ends:
                ends.append(cur)
            continue
        stack.extend(path + [b] for b in reversed(nxt))
    return ends, cycle


def owner_root(ws, store, it):
    rt = it.get("reported_to") if isinstance(it.get("reported_to"), dict) else {}
    repo = rt.get("repo")
    if never_scanned(repo):
        clears = "relayed by hand (a hidden folder never pairs): close each by its done_when"
    else:
        clears = f"{repo} closes the counterpart; one not yet written: todo report ID --to {repo}"
    return (repo,), f"reported to {repo}", clears, rt.get("their_id")


def item_root(ws, store, it):
    ends, cycle = chain_ends(ws, it)
    if cycle:
        loop = " -> ".join(cycle)
        return ("cycle", *sorted(set(cycle))), f"a blocked_by cycle {loop}", \
            f"todo edit {cycle[0]} --blocked-by ... (drop one link)", None
    unresolved = [e for e in ends if ws.find(e)[0] is None]
    if unresolved:
        return ("dangling", *unresolved), f"blocked_by {', '.join(unresolved)}, in no scanned store", \
            f"todo edit {it['id']} --blocked-by ... (drop it, or scan its store)", None
    return tuple(ends), f"open item{'s' if len(ends) > 1 else ''} {', '.join(ends)}", \
        f"close {' and '.join(ends)} (todo brief {ends[0]})", None


def jacob_root(ws, store, it):
    w = it.get("waits_on") if it.get("status") == VOCAB.jacob_status else VOCAB.role("approval_waits_on")
    if w is None:
        return ("unnamed",), f"{VOCAB.jacob_status}, naming no waits_on", \
            f"todo edit ID --waits-on ({VOCAB.waits_on_forms()})", None
    name, _, arg = w.partition(":")
    spec = VOCAB.waits_on.get(name)
    clears = spec["clears"].format(arg=arg) if spec else f"(waits_on {w!r} is not declared: todo check names it)"
    return (w,), f"waits on {w}", clears, None


def field_root(ws, store, it):
    where = os.path.relpath(store.dir, ws.root)
    return (store.repo,), f"{store.repo} triage", \
        f"todo -C {where} edit ID --size/--work/--done-when, todo split, or todo done ID --resolution (stale)", None


# The code side of vocab.json blockers.roots: each kind's root for an item.
ROOTS = {"jacob": jacob_root, "item": item_root, "owner": owner_root, "field": field_root}


def field_reasons(ws, it):
    """What `todo brief` needs and this item lacks, as short words; [] when none."""
    why = [f for f in BRIEF_NEEDS if not it.get(f)]
    if size_refusal(it):
        why.append("size" if it.get("size") is None else f"size {it['size']} (split)")
    if it.get("status") not in (VOCAB.role("default_status"), VOCAB.jacob_status):
        why.append(f"status {it.get('status')} without blocked_by")
    return why


def root_kind(ws, it):
    """Which kind of root holds this open item, or None when nothing does (it is
    dispatchable, dispatched, or a split item whose children carry the work)."""
    if it.get("dispatched"):
        return None
    if is_split(ws, it):
        return None
    if it.get("kind") == VOCAB.role("report_kind"):
        return "owner"
    if deps.open_blockers(ws, it):
        return "item"
    if it.get("status") == VOCAB.jacob_status:
        return "jacob"
    if field_reasons(ws, it):
        return "field"
    if not checks.approved_ok(it.get("approved")):
        return "jacob"
    return None


def view(ws, repo=None):
    """{items, roots: [{kind, what, clears, count, ids, detail}], unreadable}: every
    root, ranked by count, then by vocab.json's order of kinds, then by what it is."""
    groups = {}
    for s in ws.stores:
        for it in s.items:
            if repo and it.get("repo") != repo:
                continue
            kind = root_kind(ws, it)
            if kind is None:
                continue
            key, what, clears, their = ROOTS[kind](ws, s, it)
            g = groups.setdefault((kind, *key), {"kind": kind, "what": what, "clears": clears, "ids": [], "detail": []})
            g["ids"].append(it["id"])
            if kind == "owner":
                if their:
                    g["detail"].append(f"{it['id']}->{their}")
            elif kind == "field":
                g["detail"].append(f"{it['id']}: {', '.join(field_reasons(ws, it))}")
    order = {k: i for i, k in enumerate(VOCAB.blocker_roots)}
    roots = sorted(groups.values(), key=lambda g: (-len(g["ids"]), order[g["kind"]], g["what"]))
    for g in roots:
        g["count"] = len(g["ids"])
        if g["kind"] == "field":
            tally = {}
            for d in g["detail"]:
                for w in d.split(": ", 1)[1].split(", "):
                    tally[w] = tally.get(w, 0) + 1
            g["what"] += ": lacks " + ", ".join(f"{w} ({n})" for w, n in tally.items())
        elif g["kind"] == "owner" and g["detail"]:
            g["clears"] += " (counterparts " + ", ".join(g["detail"]) + ")"
    return {"items": sum(g["count"] for g in roots), "roots": roots, "unreadable": list(ws.errors)}


def lines(v, max_roots=None, max_ids=None):
    """The text output: one line per root, bounded (vocab.json blockers)."""
    max_roots = max_roots or VOCAB.blocker_bounds["max_roots"]
    max_ids = max_ids or VOCAB.blocker_bounds["max_ids"]
    out = []
    for g in v["roots"][:max_roots]:
        ids = ", ".join(g["ids"][:max_ids]) + (f" (+{g['count'] - max_ids})" if g["count"] > max_ids else "")
        out.append(f"{g['count']:>4} {g['kind']:<6} {g['what']} -- clears: {g['clears']} -- {ids}")
    rest = v["roots"][max_roots:]
    if rest:
        out.append(f"     (+{len(rest)} more root(s), holding {sum(g['count'] for g in rest)} item(s): todo blockers --json)")
    return out
