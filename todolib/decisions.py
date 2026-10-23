"""Decisions (PLAN-todo-tool.md §10.3, §10.3a, §10.3b): the fields a decision
carries, the table `todo decisions` prints and records, and the reply grammar
`todo answer` reads. vocab.json `decisions` holds every name and pattern; this
module is their one reader, so add, edit, check, decisions and answer cannot
disagree about what a complete decision or a valid answer is.

Nothing here writes a file: the CLI applies what these functions return and
saves through todolib/store.py.
"""
import re

from .store import id_number
from .vocab import VOCAB

D = VOCAB.decisions
# The fields only a decision carries (a tuple of field names, read as fields).
FIELDS = ("pointer", "hinges_on", "recommend", "options", "chosen", "jacob_words")
YES, NO = "yes", "no"
OPTION, WORDS = "option", "words"
MARKER = re.compile(r"(?:(?<=\s)|^)(\d+)\)")
TABLE_LEAD = re.compile(r"^\s*(%s-[1-9][0-9]*)\s*:\s*" % D["table_prefix"])
TABLE_ID = re.compile(r"^%s-([1-9][0-9]*)$" % D["table_prefix"])
HEADER = "| # | decision | hinges on | recommend |"
SEPARATOR = "|---|---|---|---|"


def is_decision(it):
    return (it or {}).get("kind") == VOCAB.role("decision_kind")


def normal_pointer(text):
    """`PLAN-x.md §3` for `PLAN-x.md §3` or `PLAN-x.md§3`; None when it is no FILE §n."""
    m = D["pointer"].match(str(text or "").strip())
    return f"{m.group('file')} §{m.group('section')}" if m else None


def pointer_ref(pointer):
    """The plans CLI's ref for a pointer: `PLAN-x.md§3`."""
    m = D["pointer"].match(pointer)
    return f"{m.group('file')}§{m.group('section')}"


def waits_on_for(pointer):
    """What an item waits on once the decision at `pointer` is rejected."""
    return f"{VOCAB.role('decision_waits_on')}:{pointer}"


def parse_option(text):
    """{name, text} from `NAME=TEXT`; ValueError saying why not."""
    name, sep, body = str(text).partition("=")
    name, body = name.strip(), body.strip()
    if not sep or not body or "\n" in body:
        raise ValueError(f"--option {text!r}: NAME=TEXT, the text one line")
    return {"name": name, "text": body}


def option_names(it):
    return [o.get("name") for o in it.get("options") or [] if isinstance(o, dict)]


def _line(v):
    return isinstance(v, str) and bool(v.strip()) and "\n" not in v


def field_problems(it):
    """Why the decision fields this item carries are malformed, as phrases; [] when
    they are sound (or it carries none). Shared by add, edit and check."""
    out = []
    held = [f for f in FIELDS if it.get(f) not in (None, "", [])]
    if held and not is_decision(it):
        return [f"{', '.join(held)} belong(s) to a {VOCAB.role('decision_kind')}, and this item is a {it.get('kind')}"]
    p = it.get("pointer")
    if p is not None and (not isinstance(p, str) or normal_pointer(p) != p):
        out.append(f"pointer {p!r} is not FILE §n ({D['pointer'].pattern})")
    if it.get("hinges_on") is not None and not _line(it["hinges_on"]):
        out.append("hinges_on must be one non-empty line")
    opts = it.get("options")
    names = []
    if opts is not None:
        if not (isinstance(opts, list) and opts and all(isinstance(o, dict) and set(o) == {"name", "text"} for o in opts)):
            out.append("options must be a non-empty list of {name, text}, or null")
        else:
            names = [o["name"] for o in opts]
            words = {w for ws in D["verdicts"].values() for w in ws}
            for o in opts:
                if not (isinstance(o["name"], str) and D["option_name"].match(o["name"])):
                    out.append(f"option name {o['name']!r} does not match {D['option_name'].pattern}")
                elif o["name"] in words:
                    out.append(f"option name {o['name']!r} is an answer word (decisions.verdicts): name it otherwise")
                if not _line(o["text"]):
                    out.append(f"option {o['name']!r}: its text must be one non-empty line")
            if len(set(names)) != len(names):
                out.append("options name one option twice")
    r = it.get("recommend")
    if r is not None and r not in (*D["verdicts"], *names):
        out.append(f"recommend {r!r} is not {' or '.join(D['verdicts'])}"
                   + (f" or an option ({', '.join(names)})" if names else " (it has no options)"))
    c = it.get("chosen")
    if c is not None and c not in names:
        out.append(f"chosen {c!r} names none of its options")
    jw = it.get("jacob_words")
    if jw is not None and not (isinstance(jw, list) and jw and all(
            isinstance(w, dict) and set(w) == {"date", "table", "row", "text"} and _line(w["text"])
            and isinstance(w["row"], int) and TABLE_ID.match(str(w["table"])) for w in jw)):
        out.append("jacob_words must be a non-empty list of {date, table, row, text}, written by todo answer")
    return out


def missing(it):
    """The required decision fields this decision lacks (decisions.requires)."""
    return [f for f in D["requires"] if it.get(f) in (None, "", [])]


def is_complete(it):
    return is_decision(it) and not missing(it) and not field_problems(it)


def resolution_problems(it):
    """Why a closed item's decision resolution is wrong for it, as phrases."""
    res = it.get("resolution")
    accepted, chosen, rejected = (VOCAB.role("decision_accepted_resolution"), VOCAB.role("decision_option_resolution"),
                                  VOCAB.role("decision_rejected_resolution"))
    if res not in (accepted, chosen, rejected):
        return ["chosen is set, and the item did not close on an option"] if it.get("chosen") is not None else []
    out = []
    if not is_decision(it):
        out.append(f"resolution {res!r} closes a {VOCAB.role('decision_kind')} only")
    if res in (accepted, chosen) and it.get("approved") is None:
        out.append(f"resolution {res!r} is set with Jacob's approval (todo approve, todo answer), and none is recorded")
    if res == chosen and it.get("chosen") is None:
        out.append(f"resolution {res!r} names no chosen option")
    if res != chosen and it.get("chosen") is not None:
        out.append("chosen is set, and the item did not close on an option")
    return out


# -- closing -------------------------------------------------------------------

def accepted(item, date, approved, option=None):
    """The closed form of a decision Jacob said yes to (or chose `option` on)."""
    res = VOCAB.role("decision_option_resolution" if option else "decision_accepted_resolution")
    return dict(item, status=VOCAB.closed, done=date, resolution=res, approved=approved,
                chosen=option, waits_on=item.get("waits_on"))


def rejected(item, date):
    return dict(item, status=VOCAB.closed, done=date, resolution=VOCAB.role("decision_rejected_resolution"))


def dependents(ws, item_id):
    """(item, store) for every open item, in any scanned store, whose blocked_by names item_id."""
    return [(it, s) for s in ws.stores for it in s.items if item_id in (it.get("blocked_by") or [])]


def requeued(dep, decision, reason, date):
    """The fields a dependent of a rejected decision takes: waiting on Jacob again,
    on that decision's pointer (or his approval when it names none), with why."""
    w = waits_on_for(decision["pointer"]) if decision.get("pointer") else VOCAB.role("approval_waits_on")
    line = f"{date}: {decision['id']} was rejected ({reason}); waits on {w} again"
    ev = dep.get("evidence")
    return {"status": VOCAB.jacob_status, "waits_on": w, "evidence": f"{ev}\n{line}" if ev else line}


# -- the table -----------------------------------------------------------------

def frees(ws):
    """{item id: how many open items wait behind it}, following blocked_by back
    through open items only, every scanned store."""
    behind = {}
    for s in ws.stores:
        for it in s.items:
            for b in it.get("blocked_by") or []:
                behind.setdefault(b, []).append(it["id"])

    def count(root):
        seen, stack = set(), list(behind.get(root, []))
        while stack:
            cur = stack.pop()
            if cur in seen or cur == root:
                continue
            seen.add(cur)
            stack.extend(behind.get(cur, []))
        return len(seen)
    return {it["id"]: count(it["id"]) for s in ws.stores for it in s.items if is_decision(it)}


def esc(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def cells(it):
    """[decision, hinges on, recommend], as a plan's Decisions table reads them
    (PLAN-todo-tool.md §10.3): the decision cell starts with FILE §n."""
    hinges = it["hinges_on"]
    if it.get("options"):
        hinges += "; options: " + "; ".join(f"{o['name']} = {o['text']}" for o in it["options"])
    return [esc(f"{it['pointer']}: {it['title']}"), esc(hinges), esc(it["recommend"])]


def open_rows(ws, repo=None):
    """(complete, incomplete): the open decisions of every scanned store, the
    complete ones as (item, store) most items freed first, then by repo and id;
    the others as (item, store, why)."""
    counts = frees(ws)
    complete, incomplete = [], []
    for s in ws.stores:
        for it in s.items:
            if not is_decision(it) or (repo and it.get("repo") != repo):
                continue
            why = missing(it) + field_problems(it)
            if why:
                incomplete.append((it, s, why))
            else:
                complete.append((it, s))
    complete.sort(key=lambda r: (-counts.get(r[0]["id"], 0), r[1].repo, id_number(r[0]["id"])))
    incomplete.sort(key=lambda r: (r[1].repo, id_number(r[0]["id"])))
    return complete, incomplete, counts


def record_rows(found):
    """The rows a table record keeps: numbered 1..n, tied to item ids."""
    return [{"n": n, "item": it["id"], "repo": s.repo, "status": it["status"], "cells": cells(it)}
            for n, (it, s) in enumerate(found, 1)]


def same_rows(a, b):
    return [(r["item"], r["cells"]) for r in a] == [(r["item"], r["cells"]) for r in b]


def table_number(table_id):
    m = TABLE_ID.match(str(table_id or ""))
    return int(m.group(1)) if m else None


def next_table_id(tables):
    return f"{D['table_prefix']}-{max([table_number(t.get('id')) or 0 for t in tables] + [0]) + 1}"


def find_table(tables, table_id):
    return next((t for t in tables if t.get("id") == table_id), None)


def latest_table(tables):
    return max(tables, key=lambda t: table_number(t.get("id")) or 0) if tables else None


def table_lines(table, counts=None):
    """The Decisions section, in the shape a plan's question gate parses."""
    out = ["## Decisions", "",
           f"{table['id']} ({table['date']}): {len(table['rows'])} decision(s), the one freeing most items first. "
           f"Answer: todo answer \"1) yes 2) no\" (or an option's name; other words are kept as his words, applying nothing)",
           HEADER, SEPARATOR]
    out += [f"| {r['n']} | " + " | ".join(r["cells"]) + " |" for r in table["rows"]]
    return out


def untabled_lines(listed, n=None):
    """The footer under the table for the open decisions lacking a row field
    (`listed`: {id, repo, missing}, as `todo decisions --json` gives them). They
    are their owners' to table, not questions for the reader (td-93: a bare count
    read as Jacob's backlog), so the first line says whose they are, a count per
    repo, most first; the second names the first `n` for those owners."""
    if not listed:
        return []
    n = D["max_listed"] if n is None else n
    per = {}
    for r in listed:
        per[r["repo"]] = per.get(r["repo"], 0) + 1
    repos = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ", ".join(f"{repo} {k}" for repo, k in repos[:n]) + (", ..." if len(repos) > n else "")
    ids = "; ".join(f"{r['id']} ({', '.join(r['missing'])})" for r in listed[:n])
    more = f"; +{len(listed) - n} more (--json lists them)" if len(listed) > n else ""
    return [f"{len(listed)} decision item(s) in owners' stores lack row fields ({shown}): "
            f"not questions for you until an owner tables them",
            f"for their owners (todo edit ID --pointer --hinges-on --recommend): {ids}{more}"]


# -- the reply -----------------------------------------------------------------

def parse_reply(text):
    """(table id or None, [(row number, answer text)]) from `dt-4: 1) yes 2) no 3) b`.
    ValueError for a reply naming no row, text before the first `N)`, a row named
    twice, or an empty answer: the reply is refused whole, never applied in part."""
    text = str(text or "").strip()
    table = None
    m = TABLE_LEAD.match(text)
    if m:
        table, text = m.group(1), text[m.end():]
    marks = list(MARKER.finditer(text))
    if not marks:
        raise ValueError(f"no row named: write each answer after its row number, `1) yes 2) no 3) <option> 4) <words>`")
    if text[:marks[0].start()].strip():
        raise ValueError(f"{text[:marks[0].start()].strip()!r} comes before the first row number: say which row it answers")
    out, seen = [], set()
    for i, mk in enumerate(marks):
        n = int(mk.group(1))
        body = text[mk.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        body = " ".join(body.split())
        if n in seen:
            raise ValueError(f"row {n} is answered twice")
        if not body:
            raise ValueError(f"row {n} has no answer")
        seen.add(n)
        out.append((n, body))
    return table, out


def verdict(answer, it):
    """(YES|NO|OPTION, option name or None) when the whole answer is a word of
    decisions.verdicts or one of the item's option names (case and a trailing
    full stop or exclamation aside); else (WORDS, the answer). A yes on a decision
    recommending an option chooses that option: the yes is to the recommendation."""
    word = answer.strip().rstrip(".!").strip().lower()
    for v in (YES, NO):
        if word in D["verdicts"][v]:
            if v == YES and it.get("recommend") in option_names(it):
                return OPTION, it["recommend"]
            return v, None
    if word in option_names(it):
        return OPTION, word
    return WORDS, answer
