"""blocked_by: what an item waits on (PLAN-todo-tool.md §9 step 3).

One place answers "is this item blocked" and "would this list make a cycle", so
`ready`, `list --ready/--blocked`, `brief`, `add`/`edit` and `check` cannot
disagree about it.
"""


def open_blockers(ws, item):
    """The ids in item's blocked_by that are not closed. An id that resolves in no
    scanned store blocks, never frees: a wrong "ready" is worse than a held item."""
    return [b for b in item.get("blocked_by") or [] if ws.find(b)[1] != "history"]


def cycle(ws, item_id, blockers):
    """A path item_id -> ... -> item_id through blocked_by, or None. `blockers` is
    item_id's own list as it is about to be written; every other item's is read
    from the workspace."""
    stack = [[item_id, b] for b in blockers or []]
    seen = set()
    while stack:
        path = stack.pop()
        cur = path[-1]
        if cur == item_id:
            return path
        if cur in seen:
            continue
        seen.add(cur)
        found = ws.find(cur)[0]
        for b in (found or {}).get("blocked_by") or []:
            stack.append(path + [b])
    return None
