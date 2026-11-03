"""Audits (PLAN-hard-gates.md §9): a rule refused at write time is also run over the
data already there, by a detector, so nothing old sits unseen.

`todo audit RULE` prints the findings of one rule over every scanned store, as a
detector prints them (todolib/detect.py): one finding per store, with its count. A
rule here is a vocab.json block a detector names as `audits`:

- `decisions` (detector D1): open decisions that `decisions.incomplete` finds, the
  predicate add and edit refuse by (rule 1: one predicate, two callers).
- `sizes` (detector D2): open items with no size, never ready until sized. A
  detector's own items (stall, lag) are left out: they are made unsized, and
  counting them would keep the finding alive by itself.

A finding's evidence starts `oldest YYYY-MM-DD:` (the earliest `added` among the
offenders, or `oldest unknown:` when none carries one), which AUDITS.md reads back
from the item.

`render` is AUDITS.md: what `todo detect` writes after every run, read without an
agent. Nothing here writes a file.
"""
import re

from . import decisions as decide
from . import detect
from .vocab import VOCAB

OLDEST = re.compile(r"^oldest (\d{4}-\d{2}-\d{2})\b")
AUDITS_TITLE = "# Audits"


def _decisions(store):
    return [(it, decide.incomplete(it)) for it in store.items if decide.incomplete(it)]


def _sizes(store):
    return [(it, []) for it in store.items
            if it.get("size") is None and it.get("kind") not in VOCAB.detector_kinds]


# rule -> (offenders of one store, the finding's subject, what clears it)
RULES = {
    "decisions": (_decisions, f"open {VOCAB.role('decision_kind')}s lacking fields", decide.FILL_HINT),
    "sizes": (_sizes, "unsized open items",
              f"todo edit ID --size {'|'.join(VOCAB.sizes)} (never ready until sized), or close it"),
}


def finding(store, offenders, subject, clears):
    """One finding for one store's offenders [(item, why)]."""
    dates = sorted(str(it["added"]) for it, _ in offenders if it.get("added"))
    named = "; ".join(f"{it['id']} ({', '.join(why)})" if why else it["id"] for it, why in offenders)
    return {"repo": store.repo, "subject": subject, "count": len(offenders),
            "evidence": f"oldest {dates[0] if dates else 'unknown'}: {named}", "clears_with": clears}


def findings(ws, rule):
    """The findings of `rule` over every scanned store, by repo."""
    offenders, subject, clears = RULES[rule]
    out = []
    for s in sorted(ws.stores, key=lambda s: s.repo):
        found = offenders(s)
        if found:
            out.append(finding(s, found, subject, clears))
    return out


def oldest(evidence):
    m = OLDEST.match(str(evidence or ""))
    return m.group(1) if m else None


def _cell(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def render(ws, here, detectors, runs, at):
    """AUDITS.md: one row per detector and repo (every scanned repo, and any other an
    open item of it names), with the count its open items hold, the oldest offender's
    date, the end date of the exemption it audits, and its last run from this store.
    A detector that failed or never ran is said so on each of its rows: never a gap."""
    held = {}
    for s in ws.stores:
        for it in s.items:
            if detect.is_detector_item(it) and it.get("detector") and not detect.field_problems(it):
                held.setdefault((it["detector"]["id"], it["repo"]), []).append(it)
    repos = {s.repo for s in ws.stores}
    lines = [AUDITS_TITLE, "",
             f"Rendered by `todo detect` in {here.repo} at {at}; read-only, rewritten by every run "
             "(PLAN-hard-gates.md §9). Each count is held by open items in that repo's TODO.md; "
             "`ends` is the date past which todo check fails them.", "",
             "| rule | detector | repo | count | oldest | ends | last run | outcome |",
             "|---|---|---|---|---|---|---|---|"]
    for det in detectors:
        rec = runs.get(det["id"]) if isinstance(runs, dict) else None
        if not isinstance(rec, dict) or detect.run_problem(rec):
            last, outcome = "never", "never run here"
        else:
            last, outcome = rec["at"], "ok" if rec["ok"] else f"failed: {rec['why']}"
        ends = VOCAB.end_date(det["audits"]) or "-"
        for repo in sorted(repos | {r for d, r in held if d == det["id"]}):
            its = held.get((det["id"], repo), [])
            dates = sorted(d for d in (oldest(it.get("evidence")) for it in its) if d)
            count = sum(it["detector"]["count"] for it in its)
            lines.append("| " + " | ".join(_cell(c) for c in (
                det["audits"], det["id"], repo, count, dates[0] if dates else "-", ends, last, outcome)) + " |")
    return "\n".join(lines) + "\n"
