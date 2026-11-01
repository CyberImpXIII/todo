"""`todo pair [--apply]`: the owner pulls. From its own store (`-C DIR`), todo finds
every open report in the scanned stores addressed to this store's key with no
counterpart yet, and the CLI writes the counterpart here and the pairing on both
sides, as `todo report` does from the reporter's side. A store the scan never
enters (the delegation layer, `.claude`) pairs its reports this way and only this
way: todo still opens it only when run from it (PLAN-todo-tool.md §8 decision 4
stands; external audit ra-21.1, Jacob 2026-10-31: "the owner pulls")."""


def candidates(ws, store):
    """[(their store, their item)] for every open item of another scanned store
    reported to this store's key and not yet paired (reported_to.their_id null)."""
    out = []
    for s in ws.stores:
        if s is store or not s.data:
            continue
        for it in s.items:
            rt = it.get("reported_to")
            if isinstance(rt, dict) and rt.get("repo") == store.repo and rt.get("their_id") is None:
                out.append((s, it))
    return out


def counterpart_of(store, item):
    """The item here whose parent is theirs, open or closed, or None."""
    prior = [c for c in store.items + store.closed if c.get("parent") == item.get("id")]
    return prior[0] if prior else None
