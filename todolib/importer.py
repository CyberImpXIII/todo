"""`todo import FILE`: a hand-written (or hand-edited) TODO.md into items.

One top-level bullet, or one paragraph, is one item; nothing is dropped. A
block's kind and status come from its headings (vocab.json "import"); a block
whose own text starts with the done marker ("DONE 2026-10-03: ...") goes to
history with that date. A bold lead becomes the title and the rest the
evidence; otherwise the title is the first sentence and the evidence the whole
text. Each imported item records the sha of its block, so a second import of
the same file adds nothing.

A file that todo rendered is read back too: a rendered item that matches its
store entry is skipped, one that was edited by hand is reported (and the import
refused), and a bullet with no id is new. That is how a hand edit is recovered.
"""
import hashlib
import re

from .render import HEADER_PREFIX, ITEM_RE, render_item, FIELD_MARK
from .store import TodoError, new_item
from .vocab import VOCAB

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
BULLET_RE = re.compile(r"^([-*+]|\d+[.)])(\s+)")
RULE_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
TITLE_MAX = 100
BOLD_TITLE_MAX = 300


class Block:
    def __init__(self, kind, headings, first, marker_width=0):
        self.kind = kind            # "bullet" | "para"
        self.headings = list(headings)
        self.raw = [first]
        self.marker_width = marker_width
        self.pending = 0            # blank lines seen inside a bullet, not yet known to belong

    def add(self, line):
        self.raw += [""] * self.pending + [line]
        self.pending = 0

    def text(self):
        """The block's text without its list marker, continuation lines dedented."""
        if self.kind == "bullet":
            out = [self.raw[0][self.marker_width:]]
            for ln in self.raw[1:]:
                indent = len(ln) - len(ln.lstrip(" "))
                out.append(ln[min(indent, self.marker_width):])
        else:
            indents = [len(ln) - len(ln.lstrip(" ")) for ln in self.raw if ln.strip()]
            cut = min(indents) if indents else 0
            out = [ln[cut:] for ln in self.raw]
        return "\n".join(ln.rstrip() for ln in out).strip("\n")


def md_blocks(text):
    """(blocks, skipped): top-level bullets and paragraphs, each with its heading chain."""
    stack, blocks, skipped = [], [], {"rules": 0, "headings": 0, "render_header": 0}
    cur, prev_blank, fence = None, True, None

    def close():
        nonlocal cur
        if cur is not None:
            blocks.append(cur)
        cur = None

    for raw in text.expandtabs(4).split("\n"):
        if fence:
            cur.add(raw)
            if raw.strip().startswith(fence) and raw.strip().strip(fence[0]) == "":
                fence = None
            prev_blank = False
            continue
        if not raw.strip():
            if cur is not None and cur.kind == "para":
                close()
            elif cur is not None:
                cur.pending += 1
            prev_blank = True
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0 and raw.startswith(HEADER_PREFIX):
            skipped["render_header"] += 1
            continue
        h = HEADING_RE.match(raw) if indent == 0 else None
        if h:
            close()
            level = len(h.group(1))
            stack = [s for s in stack if s[0] < level] + [(level, h.group(2))]
            skipped["headings"] += 1
            prev_blank = True
            continue
        if indent == 0 and RULE_RE.match(raw):
            close()
            skipped["rules"] += 1
            prev_blank = True
            continue
        b = BULLET_RE.match(raw) if indent == 0 else None
        headings = [s[1] for s in stack]
        if b:
            close()
            cur = Block("bullet", headings, raw, marker_width=len(b.group(0)))
        elif indent > 0 and cur is not None:
            cur.add(raw)
        elif indent > 0:
            cur = Block("para", headings, raw)
        elif cur is not None and not prev_blank and not cur.pending:
            cur.add(raw)  # a lazy continuation line
        else:
            close()
            cur = Block("para", headings, raw)
        m = FENCE_RE.match(raw)
        if m:
            fence = m.group(1)
        prev_blank = False
    close()
    return blocks, skipped


COLON_MIN_WORDS = 4  # "DONE 2026-10-02:" or "Still open:" is a lead-in, not a title


def first_sentence(text):
    flat = " ".join(text.split()).replace("**", "")
    for m in re.finditer(r"[.!?:](?=\s|$)", flat[:TITLE_MAX + 1]):
        head = flat[:m.end()]
        if m.group(0) == ":" and len(head.split()) < COLON_MIN_WORDS:
            continue
        return head
    if len(flat) <= TITLE_MAX:
        return flat
    cut = flat[:TITLE_MAX].rsplit(" ", 1)[0]
    return cut + "…"


def split_title(text):
    """(title, evidence, title_from, sep) for a block's text: sep is the one
    space or newline between a bold lead and the rest, kept so the block can be
    rebuilt word for word."""
    if text.startswith("**"):
        end = text.find("**", 2)
        lead = text[2:end] if end > 2 else ""
        if lead.strip() and "\n\n" not in lead and len(lead) <= BOLD_TITLE_MAX and "*" not in lead[-1:]:
            rest = text[end + 2:]
            sep = rest[:1] if rest[:1] in (" ", "\n") else ""
            return " ".join(lead.split()), rest[len(sep):], "bold", sep
    return first_sentence(text), text, "text", ""


def reconstruct(item, title=None, evidence=None):
    """The block text an imported item came from, modulo whitespace. Title and
    evidence default to the item's; a test passes the ones it read back from a render."""
    meta = item.get("imported") or {}
    title = item["title"] if title is None else title
    evidence = (item.get("evidence") or "") if evidence is None else evidence
    if meta.get("title_from") == "bold":
        return "**" + title + "**" + meta.get("sep", "") + evidence
    return evidence


class Plan:
    def __init__(self):
        self.new = []          # (item, "store"|"history")
        self.unchanged = []    # ids
        self.changed = []      # ids
        self.closed_seen = []  # ids already in history
        self.already = 0       # blocks imported before (same sha)
        self.missing = []      # store ids the file no longer shows
        self.rendered = False  # the file carries the render header
        self.skipped = {}


def plan_import(text, store, today):
    plan = Plan()
    plan.rendered = text.startswith(HEADER_PREFIX)
    blocks, plan.skipped = md_blocks(text)
    known_shas = {(it.get("imported") or {}).get("sha") for it in list(store.items) + list(store.closed)}
    seen_ids, occurrences = set(), {}
    for blk in blocks:
        m = ITEM_RE.match(blk.raw[0])
        if m and store.owns(m.group(1)):
            item, where = store.find(m.group(1))
            if where == "store":
                seen_ids.add(item["id"])
                rendered = render_item(item, store.repo)
                mine = "\n".join(ln.rstrip() for ln in blk.raw[:len(blk.raw)]).rstrip("\n")
                (plan.unchanged if mine == rendered else plan.changed).append(item["id"])
                continue
            if where == "history":
                plan.closed_seen.append(item["id"])
                continue
        body = blk.text()
        if not body.strip():
            continue
        section = " > ".join(blk.headings)
        key = section + "\n" + " ".join(body.split())
        occurrences[key] = occurrences.get(key, 0) + 1
        sha = hashlib.sha256(f"{key}#{occurrences[key]}".encode()).hexdigest()[:16]
        if sha in known_shas:
            plan.already += 1
            continue
        title, evidence, title_from, sep = split_title(body)
        bad = [ln for ln in evidence.split("\n") if ln.startswith(FIELD_MARK)]
        if bad:
            raise TodoError(f"cannot import a block with a line starting {FIELD_MARK!r} (the render's field mark): {bad[0][:80]!r}")
        kind, status = VOCAB.heading_rule(blk.headings)
        done = None
        dm = VOCAB.done_marker.match(body)
        if dm:
            status, done = VOCAB.closed, dm.group(1)
        item = new_item(title=title, kind=kind, status=status, evidence=evidence, repo=store.repo,
                        added=today, done=done,
                        imported={"sha": sha, "section": section, "title_from": title_from, "sep": sep})
        plan.new.append((item, "history" if status == VOCAB.closed else "store"))
    if plan.rendered:
        plan.missing = [it["id"] for it in store.items if it["id"] not in seen_ids]
    return plan
