"""Approval by rule (TD-B1, PLAN-todo-tool.md §10.1; Jacob, 2026-10-12): an open item
counts as approved, with no `todo approve`, when every condition of vocab.json
`approval.rule` holds. The conditions are data; this module is their one reader, so
`dispatchable`, `dispatch`, `blockers`, `show` and `check` cannot disagree.

A rule approval is judged afresh at every read and stored only by `todo dispatch`,
for the time the item is dispatched (`dispatch --clear` removes it), so an item
edited out of the rule's reach loses it. Its `source` is the rule's own, so it is
never taken for Jacob's yes on that item: `is_rule()` tells them apart, and
`dispatchable` lists rule approvals under their own heading (`by_rule`).

What the rule cannot see: whether the work pushes to a new remote, or is
irreversible or outward-facing, except through the item's `work` (an excluded work)
and `files` (an excluded path). An item that names neither is judged by its kind,
size and repo alone.
"""
import fnmatch

from .vocab import VOCAB


def rule_misses(it, store_repo, vocab=VOCAB):
    """Why the rule does not approve this item, as short phrases; [] when it does."""
    r = vocab.approval_rule
    why = []
    if it.get("kind") not in r["kinds"]:
        why.append(f"kind {it.get('kind')} is not {'/'.join(r['kinds'])}")
    if it.get("repo") != store_repo:
        why.append(f"repo {it.get('repo')} is not its store's own ({store_repo})")
    if it.get("size") not in r["sizes"]:
        why.append(f"size {it.get('size')} is not {'/'.join(r['sizes'])}")
    missing = [f for f in r["needs"] if not it.get(f)]
    if missing:
        why.append(f"no {', '.join(missing)}")
    if it.get("status") != vocab.role("default_status"):
        why.append(f"status {it.get('status')}")
    if it.get("work") in r["exclude_works"]:
        why.append(f"work {it['work']} is never approved by rule")
    hit = [f for f in (it.get("files") or []) if isinstance(f, str)
           and any(fnmatch.fnmatchcase(f, g) for g in r["exclude_files"])]
    if hit:
        why.append(f"touches {', '.join(hit)}")
    return why


def rule_approval(vocab=VOCAB):
    """The approval the rule gives: the shape `todo approve` writes, with the rule's
    day and source, so `checks.approved_ok` accepts it and `is_rule` names it."""
    r = vocab.approval_rule
    return {"by": vocab.approval_by, "date": r["approved"], "source": r["source"]}


def is_rule(a, vocab=VOCAB):
    return isinstance(a, dict) and a.get("source") == vocab.approval_rule["source"]


def effective(it, store_repo, vocab=VOCAB):
    """(approval, by_rule) for an open item. Jacob's own stored approval wins; a stored
    rule approval counts while the item is dispatched; otherwise the rule is judged
    afresh (a stored rule approval on an undispatched item is ignored: `todo check`
    fails it). (None, False) when nothing approves it."""
    a = it.get("approved")
    if a is not None and not is_rule(a, vocab):
        return a, False
    if a is not None and it.get("dispatched"):
        return a, True
    if not rule_misses(it, store_repo, vocab):
        return rule_approval(vocab), True
    return None, False
