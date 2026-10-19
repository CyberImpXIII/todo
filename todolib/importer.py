"""`todo import FILE`: a hand-written (or hand-edited) TODO.md into items.

One top-level bullet, or one paragraph, is one item; nothing is dropped. A
block's kind and status come from its headings (vocab.json "import"); a block
whose own text starts with the done marker ("DONE 2026-10-03: ...") goes to
history with that date; every closed block gets the resolution vocab.json
names for the import (done-deprecated), since a bullet carries none. A bold lead becomes the title and the rest the
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
from . import tags as tagging
from .store import ID_RE, TodoError, new_item, read_fallback_lead
from .vocab import VOCAB

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
BULLET_RE = re.compile(r"^([-*+]|\d+[.)])(\s+)")
RULE_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
TITLE_MAX = 100
BOLD_TITLE_MAX = 300


class Block:
    def __init__(self, kind, headings, first, marker_width=0, levels=(), section_no=0):
        self.kind = kind            # "bullet" | "para"
        self.headings = list(headings)
        self.levels = list(levels)  # each heading's level (1 for #), outermost first
        self.section_no = section_no  # which heading the block sits under, in file order
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
    cur, prev_blank, fence, section_no = None, True, None, 0

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
            section_no += 1
            skipped["headings"] += 1
            prev_blank = True
            continue
        if indent == 0 and RULE_RE.match(raw):
            close()
            skipped["rules"] += 1
            prev_blank = True
            continue
        b = BULLET_RE.match(raw) if indent == 0 else None
        where = {"levels": [s[0] for s in stack], "section_no": section_no}
        headings = [s[1] for s in stack]
        if b:
            close()
            cur = Block("bullet", headings, raw, marker_width=len(b.group(0)), **where)
        elif indent > 0 and cur is not None:
            cur.add(raw)
        elif indent > 0:
            cur = Block("para", headings, raw, **where)
        elif cur is not None and not prev_blank and not cur.pending:
            cur.add(raw)  # a lazy continuation line
        else:
            close()
            cur = Block("para", headings, raw, **where)
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


def skip_reasons(blocks, vocab=VOCAB):
    """{index: why} for the blocks that are not items (vocab.json import.skip): a
    paragraph above the first bullet of a section holding bullets, a paragraph under
    the top heading alone in a file with deeper ones, and a block that is only a heading."""
    out = {}
    bullets = {}
    for i, b in enumerate(blocks):
        if b.kind == "bullet":
            bullets.setdefault(b.section_no, i)
    deeper = any(lv > 1 for b in blocks for lv in b.levels)
    for i, b in enumerate(blocks):
        text = b.text().strip()
        if vocab.import_heading_only.match(text):
            out[i] = "only a heading"
        elif vocab.import_skip_intro and b.kind == "para":
            if b.section_no in bullets and i < bullets[b.section_no]:
                out[i] = "text above the section's first bullet"
            elif deeper and max(b.levels, default=0) <= 1:
                out[i] = "text under the top heading alone"
    return out


def lead(text):
    """A block's lead: its text up to the first blank line or nested list line."""
    out = []
    for ln in text.split("\n"):
        if not ln.strip() or (out and BULLET_RE.match(ln.lstrip(" "))):
            break
        out.append(ln)
    return "\n".join(out)


def flat(text):
    return " ".join(text.split())


def read_approval(text, today, vocab=VOCAB):
    """(approved, None) | (None, why listed) | (None, None) when the lead says nothing."""
    m = vocab.import_approval.search(lead(text))
    if not m:
        return None, None
    date = m.group("date")
    if date > today:
        return None, f"approval dated {date}, after today: not applied"
    quote = m.group("quote")
    source = flat(quote.strip("\"“”") if quote else m.group(0))
    return {"by": vocab.approval_by, "date": date, "source": source}, None


def read_waits_on(text, resolve_plan=None, vocab=VOCAB):
    """(value, None) | (None, why listed): the earliest rule match whose value is a
    declared waits_on and, for a rule with `plan`, whose plan section reads.
    resolve_plan(ref) -> None when the section reads, else why not."""
    hits = sorted(((m.start(), r, m) for r in vocab.import_waits_on for m in r["match"].finditer(text)),
                  key=lambda h: h[0])
    why = []
    for _, r, m in hits:
        value = m.expand(r["value"])
        bad = vocab.waits_on_problem(value)
        if bad is None and r["plan"] and resolve_plan is not None:
            bad = resolve_plan(m.expand(r["plan"]))
        if bad is None:
            return value, None
        why.append(bad)
    mention = vocab.import_waits_mention.search(text)
    if why:
        return None, "no pointer resolves: " + "; ".join(why)
    if mention:
        return None, f"{flat(mention.group(0))!r} resolves to no waits_on"
    return None, "names nothing it waits on"


def read_probe(text, vocab=VOCAB):
    m = vocab.import_probe.search(text)
    if not m:
        return None
    rest, tick = flat(text[m.end():]), False
    for i, ch in enumerate(rest):
        if ch == "`":
            tick = not tick
        elif ch == "." and not tick and (i + 1 == len(rest) or rest[i + 1] == " "):
            return rest[:i + 1].strip() or None
    return rest.strip() or None


def read_reported_here(text):
    """For a block under report_fallback.heading (what `todo report` filed in this
    repo while it had no store): {parent, title}, or None when its text starts with
    no todo:<id> marker. The parent is the reported item's id; the title is the
    report's own when the lead is the one store.fallback_lead writes, else None."""
    first = text.split("\n", 1)[0]
    marker = first.split(" ", 1)[0]
    local = tagging.local_id(marker)
    if local == marker or not ID_RE.match(local):
        return None
    parsed = read_fallback_lead(first)
    return {"parent": local, "title": parsed["title"] if parsed and parsed["marker"] == marker else None}


def read_owner(text, repos, own, today, vocab=VOCAB):
    """reported_to from the lead's first word, or None: only a repo the scan finds."""
    first = lead(text)
    m = vocab.import_owner.match(first.replace("**", ""))
    if not m or m.group("repo") not in repos or m.group("repo") == own:
        return None
    d = vocab.import_report_date.match(first.split("\n")[0])
    return {"repo": m.group("repo"), "date": d.group("date") if d else today, "their_id": None}


# The fields a kind may require that a block's text can fill, each with its reader
# (ctx: vocab, repos, own, today). A required field with no reader is never guessed:
# the block imports as roles.default_kind (vocab.json import._fallback).
FIELD_READERS = {
    "probe": lambda body, ctx: read_probe(body, ctx["vocab"]),
    "reported_to": lambda body, ctx: read_owner(body, ctx["repos"], ctx["own"], ctx["today"], ctx["vocab"]),
}


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
        self.not_items = []    # (why, text): blocks import.skip says are not items
        self.listed = []       # (title, why): what a rule could not read, for whoever imports
        self.unnamed_waits = []  # titles of waiting-jacob items naming no waits_on


def plan_import(text, store, today, repos=frozenset(), resolve_plan=None, waits_on=None, vocab=VOCAB):
    """repos: the repo names a report's owner may be (the scan's); resolve_plan: see
    read_waits_on; waits_on: the value for a waiting-jacob item that names none."""
    plan = Plan()
    plan.rendered = text.startswith(HEADER_PREFIX)
    blocks, plan.skipped = md_blocks(text)
    known_shas = {(it.get("imported") or {}).get("sha") for it in list(store.items) + list(store.closed)}
    seen_ids, occurrences = set(), {}
    skip = skip_reasons(blocks, vocab) if not plan.rendered else {}
    for i, blk in enumerate(blocks):
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
        if i in skip:
            plan.not_items.append((skip[i], flat(body)))
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
        kind, status = vocab.heading_rule(blk.headings)
        extra, wanted = {}, None
        if vocab.fallback_heading in blk.headings:
            # Reported here by another repo (td-70): the counterpart of that report,
            # never a report from this repo (its "Reported" would match the heading
            # rule, and the marker's `todo:` the owner rule).
            kind = vocab.role("default_kind")
            here = read_reported_here(body)
            if here:
                extra["parent"] = here["parent"]
                title = here["title"] or title
            else:
                plan.listed.append((title, f"under {vocab.fallback_heading!r} with no {tagging.PREFIX}<id> marker: "
                                           "imported as a note with no parent"))
        done = None
        dm = vocab.done_marker.match(body)
        if dm:
            status, done = vocab.closed, dm.group(1)
        if status != vocab.closed:
            approved, why = read_approval(body, today, vocab)
            if why:
                plan.listed.append((title, why))
            if approved:
                extra["approved"] = approved
                if status == vocab.jacob_status:
                    status = vocab.role("default_status")
            if status == vocab.jacob_status:
                value, why = read_waits_on(body, resolve_plan, vocab)
                if value is None:
                    plan.listed.append((title, why + (f"; --waits-on {waits_on} given" if waits_on else "")))
                    if waits_on:
                        value = waits_on
                    else:
                        plan.unnamed_waits.append(title)
                extra["waits_on"] = value
        # A closed block is held to its kind's required fields too: a DONE bullet
        # under the reports heading naming no owner is a note, not a report with
        # no reported_to that check fails and history never lets be edited (td-47).
        ctx = {"vocab": vocab, "repos": repos, "own": store.repo, "today": today}
        for f in vocab.kinds.get(kind, {}).get("requires", []):
            value = FIELD_READERS[f](body, ctx) if f in FIELD_READERS else None
            if value is None:
                wanted, kind = kind, vocab.role("default_kind")
                fix = "history keeps it as it is" if status == vocab.closed else \
                    f"todo edit ID --kind {wanted} --{f.replace('_', '-')} ..."
                plan.listed.append((title, f"no {f} read: imported as {kind} ({fix})"))
                break
            extra[f] = value
        if wanted:
            extra = {k: v for k, v in extra.items() if k not in vocab.kinds[wanted].get("requires", [])}
        # A bullet carries no resolution field: a closed one gets the import's own
        # value, never a guess from its text (td-1, PLAN-todo-tool.md end).
        resolution = VOCAB.role("import_resolution") if status == VOCAB.closed else None
        item = new_item(**extra, title=title, kind=kind, status=status, evidence=evidence, repo=store.repo,
                        added=today, done=done, resolution=resolution,
                        imported={"sha": sha, "section": section, "title_from": title_from, "sep": sep,
                                  **({"wanted": wanted} if wanted else {})})
        plan.new.append((item, "history" if status == VOCAB.closed else "store"))
    if plan.rendered:
        plan.missing = [it["id"] for it in store.items if it["id"] not in seen_ids]
    return plan
