"""TODO.md (and TODO-HISTORY.md) from the store, and the parser for that format.

The render is a pure function of the store: no dates of its own, no wrapping,
so the same store always renders byte for byte the same file, and `check`
can compare. One item renders as

    - **td-3 · Title**
      evidence, verbatim, two spaces in
      · probe: ...
      · added: 2026-10-04

`parse_blocks()` reads that back (tests/test_import.py round-trips it).

TODO.md carries a seal in its header: a digest of the file with the seal left
out. A file whose seal matches is exactly what some render wrote, so when it
differs from today's render it is stale (the render format changed, or
todo.json changed without a re-render), never a hand edit; rewriting it loses
nothing (td-10). An edit anywhere, the header and the seal included, breaks the
seal. TODO-HISTORY.md is never checked and carries none.
"""
import hashlib
import re

from .store import never_scanned
from .vocab import VOCAB

HEADER_PREFIX = "<!-- rendered by todo"
HEADER = (HEADER_PREFIX + " from todo.json ({counts}): do not edit by hand, `todo check` fails on a "
          "hand edit. Change items with the todo CLI; a hand edit is recovered with `todo import`. -->")
# "; seal <digest>" just inside the header's closing parenthesis.
SEAL_RE = re.compile(r"; seal ([0-9a-f]{12})(?=\))")
SEAL_LEN = 12
HISTORY_HEADER =(HEADER_PREFIX + " from todo-history.json ({counts}): a read-only view for people, "
                  "never checked; the data file is the record. -->")
ITEM_RE = re.compile(r"^- \*\*([a-z][a-z0-9]*-[0-9]+) · (.*)\*\*$")
FIELD_MARK = "· "
FIELD_RE = re.compile(r"^· ([a-z ]+): (.*)$")
UNKNOWN_KIND_HEADING = "Items of an undeclared kind (todo check fails on these)"
# Fields that render in the header or the body, or not at all, rather than as "· label:" lines.
NOT_FIELD_LINES = {"id", "title", "evidence", "imported"}


def field_value(name, value):
    if name == "reported_to":
        their = value.get("their_id")
        if their:
            tail = f" as {their}"
        else:
            tail = " (relayed by hand; never pairs)" if never_scanned(value.get("repo")) else " (no counterpart yet)"
        return f"{value.get('repo')} on {value.get('date')}" + tail
    if name == "handoff" and isinstance(value, dict):
        return f"{value.get('text')} ({value.get('date')}, at {value.get('commit') or 'no recorded commit'})"
    if name == "approved" and isinstance(value, dict):
        return f"{value.get('by')} {value.get('date')}: {value.get('source')}"
    if name == "dispatched" and isinstance(value, dict):
        return f"{value.get('date')}" + (f": {value['text']}" if value.get("text") else "")
    if name == "plan_pins" and isinstance(value, list):
        return "; ".join(f"{p.get('plan')} as of {p.get('date')} (sha256 {str(p.get('digest'))[:12]})"
                         if isinstance(p, dict) else repr(p) for p in value)
    if isinstance(value, list):
        return ", ".join(value)
    return str(value)


def render_item(item, store_repo, show_kind=False):
    lines = [f"- **{item.get('id')} · {item.get('title')}**"]
    evidence = item.get("evidence") or ""
    if evidence:
        lines += [("  " + ln).rstrip() for ln in evidence.split("\n")]
    for name, spec in VOCAB.fields.items():
        if name in NOT_FIELD_LINES:
            continue
        value = item.get(name)
        if value in (None, "", []):
            continue
        if name == "kind" and not show_kind:
            continue
        if name == "status" and value == VOCAB.role("default_status"):
            continue
        if name == "repo" and value == store_repo:
            continue
        lines.append(f"  {FIELD_MARK}{spec['label']}: {field_value(name, value)}".rstrip())
    return "\n".join(lines)


def _counts(store):
    return f"{len(store.items)} open, {len(store.closed)} closed in todo-history.json"


def render_store(store):
    out = [HEADER.format(counts=_counts(store)), f"# {store.repo} TODO", ""]
    by_kind = {}
    for it in store.items:
        by_kind.setdefault(it.get("kind"), []).append(it)
    sections = [(spec["heading"], by_kind.pop(kind, []), spec["always"], False)
                for kind, spec in VOCAB.kinds.items()]
    leftovers = [it for k in sorted(by_kind, key=str) for it in by_kind[k]]
    sections.append((UNKNOWN_KIND_HEADING, leftovers, False, True))
    for heading, items, always, show_kind in sections:
        if not items and not always:
            continue
        out += [f"## {heading}", ""]
        for it in items:
            out += [render_item(it, store.repo, show_kind=show_kind), ""]
    return seal("\n".join(out).rstrip("\n") + "\n")


def unseal(text):
    """The text with its header's seal left out: what the seal is a digest of,
    and byte for byte the render format from before seals."""
    head, sep, rest = text.partition("\n")
    return SEAL_RE.sub("", head, count=1) + sep + rest


def _digest(unsealed):
    return hashlib.sha256(unsealed.encode()).hexdigest()[:SEAL_LEN]


def seal(text):
    """The text with its header sealed (an existing seal is replaced)."""
    plain = unseal(text)
    head, sep, rest = plain.partition("\n")
    close = head.index(")")  # the parenthesis closing the counts
    return head[:close] + f"; seal {_digest(plain)}" + head[close:] + sep + rest


def is_sealed(text):
    """True when the text is exactly what a render wrote, of whatever store or format."""
    m = SEAL_RE.search(text.partition("\n")[0])
    return bool(m) and m.group(1) == _digest(unseal(text))


def history_order(items):
    """Newest first: by done date (undated last), then latest appended first."""
    indexed = list(enumerate(items))
    indexed.sort(key=lambda p: (p[1].get("done") or "", p[0]), reverse=True)
    dated = [it for _, it in indexed if it.get("done")]
    undated = [it for _, it in indexed if not it.get("done")]
    return dated + undated


def render_history(store):
    out = [HISTORY_HEADER.format(counts=_counts(store)), f"# {store.repo} history", ""]
    for it in history_order(store.closed):
        out += [render_item(it, store.repo, show_kind=True), ""]
    return "\n".join(out).rstrip("\n") + "\n"


def parse_blocks(text):
    """Rendered items in a file: [{id, title, evidence, fields, text}], in order."""
    lines = text.split("\n")
    blocks, i = [], 0
    while i < len(lines):
        m = ITEM_RE.match(lines[i])
        if not m:
            i += 1
            continue
        body = [lines[i]]
        i += 1
        while i < len(lines) and (lines[i] == "" or lines[i].startswith("  ")):
            body.append(lines[i])
            i += 1
        while body and body[-1] == "":
            body.pop()
        evidence, fields = [], {}
        for ln in body[1:]:
            fm = FIELD_RE.match(ln[2:]) if ln.startswith("  " + FIELD_MARK) else None
            if fm:
                fields[fm.group(1)] = fm.group(2)
            else:
                evidence.append(ln[2:] if ln.startswith("  ") else ln)
        blocks.append({"id": m.group(1), "title": m.group(2), "evidence": "\n".join(evidence),
                       "fields": fields, "text": "\n".join(body)})
    return blocks
