"""Plans generate their items (PLAN-services.md §3 G6, step 6.3 of its §4).

`todo sync-plans` reads each plan's steps through the setup tool's `setup plans
steps <file> --json`, the one parser of G1's grammar (never parsed here), and
compares them with the items it made before: kind plan-step (role plan_step_kind;
the plan calls it `step`, a word `todo steps` and jacob-step already use),
each holding `plan_step` {file, section, step, hash, text}.

- A new step gets an item in its owner repo's store, pinned to its section, open
  when the plan records Jacob's approval on it or a step above it, else
  waiting-jacob on his approval (or, tracked needs-yes, on that decision, which
  the sync makes once in the store it runs from).
- A step is matched by its text hash first, then by its number, so inserting a
  step re-points nothing. A renumbered step's item takes the new number; a changed
  step's item takes the new title, step text and pin, and is listed `stale` with
  the old and the new text (its judgement fields are left to its owner). An item
  already dispatched is never changed: it is flagged.
- A removed step's item is listed `gone`, never closed.
- It sets no blocked_by, and fails open: a plan it cannot read is one notice line
  and its items are judged neither changed nor gone.

This module decides; todolib/cli.py validates and writes (the one way in)."""
import json
import re
import subprocess
from pathlib import Path

from . import decisions as decide
from . import plans
from .store import new_item
from .vocab import VOCAB

STEPS = ("plans", "steps")
TIMEOUT = 120
# The plans CLI's record keys, not vocabulary names (one of them spells a kind).
RECORD_KEYS = tuple("file section step parent text hash owners track placeable".split())
FIELDS = tuple("file section step hash text".split())  # what plan_step keeps of a record
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
TRACK_TAIL = re.compile(r"\s*\btrack:\s.*$", re.S)
OWNER_LEAD = re.compile(r"^(?:`[^`\n]+`\s*(?:,|and|&)?\s*)+:\s*")
BOLD = re.compile(r"^\*\*(.+?)\*\*")
SENTENCE = re.compile(r"(?<=[.;:])\s")
EMPTY_PARENS = re.compile(r"\s*\(\s*\)")

CREATE, DECIDE, LIST, SKIP = "create", "decide", "list", "skip"
ACTIONS = (CREATE, DECIDE, LIST, SKIP)

NEW, DECISION, UPDATED, RENUMBERED, STALE, FLAGGED, GONE, LISTED = (
    "new", "new-decision", "updated", "renumbered", "stale", "flagged", "gone", "listed")
ORDER = (NEW, DECISION, UPDATED, RENUMBERED, STALE, FLAGGED, GONE, LISTED)
WRITES = (NEW, DECISION, UPDATED, RENUMBERED, STALE)  # the actions that change a store; the rest only say


def spec():
    return VOCAB.sync_plans


def kind():
    return VOCAB.role("plan_step_kind")


def is_step_item(it):
    return it.get("kind") == kind()


def where(ps):
    """How a step is named: `PLAN-x.md §4 step 6.3`."""
    return f"{ps['file']} §{ps['section']} step {ps['step']}"


# -- reading -------------------------------------------------------------------

def record_problem(s):
    """Why one record of `plans steps --json` is not what this module reads, or None."""
    if not isinstance(s, dict):
        return "is not an object"
    missing = [k for k in RECORD_KEYS if k not in s]
    if missing:
        return "lacks " + ", ".join(missing)
    for k in ("file", "section", "step", "text"):
        if not (isinstance(s[k], str) and s[k].strip()):
            return f"{k} is not a non-empty string"
    if not HASH_RE.match(str(s["hash"])):
        return "hash is not a sha256 hex digest"
    if not (isinstance(s["owners"], list) and all(isinstance(o, str) and o for o in s["owners"])):
        return "owners is not a list of names"
    t = s["track"]
    if t is not None:
        if not (isinstance(t, dict) and isinstance(t.get("kind"), str) and isinstance(t.get("fields"), dict)):
            return "track is not {kind, value, fields}"
        if t["kind"] not in spec()["track"]:
            return f"track kind {t['kind']!r} is not in vocab.json sync_plans.track ({', '.join(spec()['track'])})"
    return None


def read_steps(cli, path):
    """(steps, None) | (None, why) for one plan file, read by `<cli> plans steps <path> --json`."""
    try:
        r = subprocess.run([str(cli), *STEPS, str(path), "--json"], capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"{' '.join(STEPS)} {path.name} could not run: {e}"
    if r.returncode != 0:
        first = (r.stderr.strip().splitlines() or ["(no stderr)"])[0]
        return None, f"{' '.join(STEPS)} {path.name}: exit {r.returncode}, {first}"
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None, f"{' '.join(STEPS)} {path.name} printed no JSON"
    if not isinstance(data, list):
        return None, f"{' '.join(STEPS)} {path.name} printed no list of steps"
    for i, s in enumerate(data):
        why = record_problem(s)
        if why:
            return None, f"{' '.join(STEPS)} {path.name}, record {i}: {why}"
        if s["file"] != path.name:
            return None, f"{' '.join(STEPS)} {path.name}, record {i}: names file {s['file']!r}"
    return data, None


# -- what a step gives its item --------------------------------------------------

def pointer_of(track):
    f = track.get("fields") or {}
    if not (f.get("file") and f.get("ref")):
        return None
    return f"{f['file']} §{f['ref']}"


def decision_pointer(step):
    """The normalised FILE §n a decide step waits on, or None when its track names
    none a decision's pointer takes (the step is then listed, never guessed)."""
    return decide.normal_pointer(pointer_of(step["track"]) or "")


def action_of(step):
    t = step["track"]
    return spec()["track"][t["kind"]] if t else spec()["untracked"]


def makes_item(step):
    act = action_of(step)
    return act == CREATE or (act == DECIDE and decision_pointer(step) is not None)


def core(text):
    """The step's text without its track tag: a re-tag is no change of the step."""
    return TRACK_TAIL.sub("", text).strip()


def title_of(step):
    """One line from the step: its bold lead, else its first sentence, owner and
    track tag left out, at most sync_plans.title_max characters."""
    t = OWNER_LEAD.sub("", core(step["text"]))
    t = EMPTY_PARENS.sub("", VOCAB.import_approval.sub("", t))  # his yes is state, not title; its colon no sentence end
    m = BOLD.match(t)
    t = m.group(1) if m else SENTENCE.split(t, 1)[0]
    t = " ".join(t.replace("**", "").split()).rstrip(".:;, ")
    n = spec()["title_max"]
    if len(t) > n:
        t = t[:n].rsplit(" ", 1)[0].rstrip(".:;, ") + "..."
    return t or f"step {step['step']}"


def evidence_of(step, date):
    return f"made by todo sync-plans {date} from {where(step)}:\n{core(step['text'])}"


def approval_of(step, by_step):
    """(date, step number) of the `approved: Jacob <date>` the plan records on the
    step or a step above it, or (None, None)."""
    cur, seen = step, set()
    while cur is not None and cur["step"] not in seen:
        seen.add(cur["step"])
        m = VOCAB.import_approval.search(cur["text"])
        if m:
            return m.group("date"), cur["step"]
        cur = by_step.get(cur.get("parent"))
    return None, None


def wanted(step, by_step):
    """(status, waits_on, approved) the sync gives a step's item."""
    if action_of(step) == DECIDE and decision_pointer(step):
        return VOCAB.jacob_status, decide.waits_on_for(decision_pointer(step)), None
    date, at = approval_of(step, by_step)
    if date:
        src = f"{step['file']} §{step['section']} step {at}: approved: Jacob {date}"
        return VOCAB.role("default_status"), None, {"by": VOCAB.approval_by, "date": date, "source": src}
    return VOCAB.jacob_status, VOCAB.role("approval_waits_on"), None


def sync_state(it):
    """True when the item's status is one the sync sets (waiting on his approval or
    a decision), so the sync may move it; a status a person set is left alone."""
    w = it.get("waits_on") or ""
    return it.get("status") == VOCAB.jacob_status and (
        w == VOCAB.role("approval_waits_on") or w.startswith(VOCAB.role("decision_waits_on") + ":"))


def tag_of(ps):
    return f"{plans.namespace()}:{ps['file']}§{ps['section']}"


def plan_step_of(step):
    return {k: step[k] for k in FIELDS}


def plan_step_problems(it):
    """Why an item's plan_step is wrong for it, as phrases (check runs this)."""
    ps = it.get("plan_step")
    if not is_step_item(it):
        return [f"plan_step is set on a {it.get('kind')}: only a {kind()} holds one"] if ps is not None else []
    if not (isinstance(ps, dict) and set(ps) == set(FIELDS)):
        return [f"plan_step must be {{{', '.join(FIELDS)}}}"]
    out = [f"plan_step.{k} is not a non-empty string" for k in FIELDS if not (isinstance(ps[k], str) and ps[k].strip())]
    if not out and not HASH_RE.match(ps["hash"]):
        out.append("plan_step.hash is not a sha256 hex digest")
    if not out and not ps["file"].endswith(".md"):
        out.append("plan_step.file is not a .md file")
    return out


# -- citing (todo list --cites) -------------------------------------------------

CITE_FILE = re.compile(r"^[A-Za-z0-9_./-]+\.md$")


def citation(text):
    """(file, section or None) for `PLAN-x.md §3`, `PLAN-x.md§3` or `PLAN-x.md`; None
    for anything else."""
    text = str(text or "").strip()
    ptr = decide.normal_pointer(text)
    if ptr:
        file, _, section = ptr.partition(" §")
        return file, section
    return (text, None) if CITE_FILE.match(text) else None


def _within(section, wanted):
    return wanted is None or (section is not None and (section == wanted or section.startswith(wanted + ".")))


def cites(it, file, section):
    """True when the item cites FILE §section or a section inside it (§3 holds §3.1):
    by a plan: tag, by its plan_step, or as a decision's pointer."""
    found = [plans.split(ref) for ref in plans.refs(it)]
    ps = it.get("plan_step")
    if isinstance(ps, dict):
        found.append((ps.get("file"), ps.get("section")))
    ptr = decide.normal_pointer(it.get("pointer")) if decide.is_decision(it) else None
    if ptr:
        found.append(tuple(ptr.split(" §", 1)))
    return any(f == file and _within(s, section) for f, s in found)


# -- matching ------------------------------------------------------------------

def match(steps, items):
    """[(step, item or None, how)] for the steps and the items made from that plan
    in one store, open or closed, and the items no step matches. A step matches by
    its hash first (how: same, or renumbered when its place moved), then by its
    section and number (how: changed)."""
    used, found = set(), {}
    for st in steps:
        for it in items:
            if id(it) not in used and it["plan_step"]["hash"] == st["hash"]:
                ps = it["plan_step"]
                same = (ps["section"], ps["step"]) == (st["section"], st["step"])
                found[id(st)] = (it, "same" if same else RENUMBERED)
                used.add(id(it))
                break
    for st in steps:
        if id(st) in found:
            continue
        for it in items:
            ps = it["plan_step"]
            if id(it) not in used and (ps["section"], ps["step"]) == (st["section"], st["step"]):
                found[id(st)] = (it, "changed")
                used.add(id(it))
                break
    pairs = [(st, *found.get(id(st), (None, NEW))) for st in steps]
    return pairs, [it for it in items if id(it) not in used]


# -- the plan of a sync ----------------------------------------------------------

def _act(action, store, item, ps, detail, changes=None, quiet=False):
    return {"action": action, "store": store, "item": item, "plan": where(ps) if ps else None,
            "detail": detail, "changes": changes or {}, "quiet": quiet}


def _replace_tag(tags, old, new):
    tags = [t for t in (tags or []) if t != old]
    return tags if new in tags else tags + [new]


def _changes(it, st, how, by_step, pin, notices, date):
    """(changes, stale) for an open item matched to step st."""
    old = it["plan_step"]
    new = plan_step_of(st)
    changes, stale = {}, False
    if new != old:
        changes["plan_step"] = new
    if how == "changed" and core(old["text"]) != core(new["text"]):
        stale = True
        if title_of(st) != it.get("title"):
            changes["title"] = title_of(st)
    if tag_of(old) != tag_of(new):
        changes["tags"] = _replace_tag(it.get("tags"), tag_of(old), tag_of(new))
    if sync_state(it):
        status, waits_on, approved = wanted(st, by_step)
        if (status, waits_on) != (it.get("status"), it.get("waits_on")):
            changes.update(status=status, waits_on=waits_on, approved=approved)
    ref = tag_of(new).split(":", 1)[1]
    state, digest = pin(ref)
    if state != plans.OK:
        notices.append(f"{where(new)}: its section could not be pinned ({digest})")
    else:
        pins = [p for p in (it.get("plan_pins") or []) if p.get("plan") not in (ref, tag_of(old).split(":", 1)[1])]
        cur = [p for p in (it.get("plan_pins") or []) if p.get("plan") == ref]
        if not cur or cur[0].get("digest") != digest:
            changes["plan_pins"] = pins + [{"plan": ref, "digest": digest, "date": date}]
    if stale:
        changes["evidence"] = ((it.get("evidence") or "").rstrip("\n") + "\n" if it.get("evidence") else "") + (
            f"{date} sync-plans: {where(old)} changed; it was: {core(old['text'])}")
    return changes, stale


def plan(ws, here, steps_by_file, judged, pin, date):
    """(actions, notices) of one sync, writing nothing. steps_by_file holds each
    plan read ({file: [step]}); judged names the files whose items may be listed
    gone (each plan read, and in a full run each plan file no longer there);
    pin(ref) is plans.show for `FILE§n`. A plan not read is in neither: its items
    are left as they are."""
    actions, notices = [], []
    made = {}
    for s in ws.stores:
        opened = {id(it) for it in s.items}
        for it in list(s.items) + list(s.closed):
            if is_step_item(it) and not plan_step_problems(it):
                made.setdefault((str(s.dir), it["plan_step"]["file"]), []).append((it, id(it) in opened))
    for file in sorted(set(steps_by_file) | set(judged)):
        steps = steps_by_file.get(file, [])
        by_step = {st["step"]: st for st in steps}
        for s in ws.stores:
            mine = [st for st in steps if s.repo in st["owners"]]
            items = made.get((str(s.dir), file), [])
            if not mine and not items:
                continue
            opened = {id(it) for it, o in items if o}
            pairs, rest = match(mine, [it for it, _ in items])
            for st, it, how in pairs:
                if it is None:
                    made_now = new_step_item(st, s, by_step, pin, date, notices) if makes_item(st) else None
                    if made_now is not None:
                        actions.append(_act(NEW, s, made_now, st, state_line(made_now)))
                    continue
                if id(it) not in opened:
                    continue  # closed: done or dropped, and history never changes
                changes, stale = _changes(it, st, how, by_step, pin, notices, date)
                if not changes:
                    continue
                if it.get("dispatched"):
                    actions.append(_act(FLAGGED, s, it, st, "dispatched, so not changed; it would change: "
                                        + ", ".join(sorted(changes))))
                    continue
                if stale:
                    actions.append(_act(STALE, s, it, st, f"was: {core(it['plan_step']['text'])} | now: {core(st['text'])}",
                                        changes))
                elif how == RENUMBERED:
                    actions.append(_act(RENUMBERED, s, it, st, f"was {where(it['plan_step'])}", changes))
                else:
                    actions.append(_act(UPDATED, s, it, st, ", ".join(sorted(changes)), changes,
                                        quiet=set(changes) <= {"plan_pins", "plan_step"}))
            if file in judged:
                for it in rest:
                    if id(it) in opened:
                        actions.append(_act(GONE, s, it, it["plan_step"], "no longer in the plan: close it, or keep it, by hand"))
        for st in steps:
            actions.extend(_act(LISTED, None, None, st, why) for why in listed_why(st, ws))
    actions.extend(decisions_needed(ws, here, steps_by_file, pin, date, notices))
    return actions, notices


def state_line(it):
    """How a made item stands: `open, approved: <source>` or `waiting-jacob on <waits_on>`."""
    if it.get("approved"):
        return f"{it['status']}, approved: {it['approved']['source']}"
    return f"{it['status']} on {it.get('waits_on')}"


def listed_why(st, ws):
    """Why a step gets no item of its own here, for a person to place: [] when it gets one."""
    act = action_of(st)
    if act == SKIP:
        return []
    if act == LIST:
        return [f"tracked in {st['track'].get('value')}: a hand-written file the sync does not write"]
    if act == DECIDE and decision_pointer(st) is None:
        return [f"track {st['track'].get('value')!r} names no FILE §n a decision's pointer takes (decisions.pointer)"]
    if not st["owners"]:
        if st.get("children"):
            return []  # a heading over its sub-steps, which carry the owners
        return [st.get("why") or "names no owner repo"]
    return [f"no scanned store for owner {o}" for o in st["owners"] if ws.by_repo(o) is None]


def new_step_item(st, s, by_step, pin, date, notices):
    status, waits_on, approved = wanted(st, by_step)
    ps = plan_step_of(st)
    it = new_item(title=title_of(st), kind=kind(), status=status, evidence=evidence_of(st, date),
                  repo=s.repo, waits_on=waits_on, added=date)
    it.update(approved=approved, plan_step=ps, tags=[tag_of(ps)])
    ref = tag_of(ps).split(":", 1)[1]
    state, digest = pin(ref)
    if state != plans.OK:
        notices.append(f"{where(ps)}: its section could not be pinned ({digest}); no item made")
        return None
    it["plan_pins"] = [{"plan": ref, "digest": digest, "date": date}]
    return it


def decisions_needed(ws, here, steps_by_file, pin, date, notices):
    """One decision per needs-yes pointer no decision in any scanned store, open or
    closed, already holds: made in the store the sync runs from."""
    wait = {}
    for steps in steps_by_file.values():
        for st in steps:
            if action_of(st) == DECIDE and decision_pointer(st):
                wait.setdefault(decision_pointer(st), []).append(st)
    have = {it.get("pointer") for it, _, _ in ws.everything() if decide.is_decision(it)}
    out = []
    for ptr, steps in sorted(wait.items()):
        if ptr in have:
            continue
        ref = decide.pointer_ref(ptr)
        state, why = pin(ref)
        if state != plans.OK:
            notices.append(f"{ptr}: no decision made, its section could not be read ({why})")
            continue
        hinges = "whether to start " + "; ".join(f"step {st['step']} ({title_of(st)})" for st in steps)
        n = spec()["title_max"] * 2
        if len(hinges) > n:
            hinges = hinges[:n].rsplit(" ", 1)[0] + "..."
        it = new_item(title="start the plan steps that wait on this section", kind=VOCAB.role("decision_kind"),
                      status=decide.D["status"], waits_on=decide.D["waits_on"], repo=here.repo, added=date,
                      evidence=f"made by todo sync-plans {date}: " + ", ".join(where(st) for st in steps)
                      + f" carry track needs-yes {ptr}")
        it.update(pointer=ptr, hinges_on=hinges, recommend=decide.D["generated_recommend"],
                  tags=[f"{plans.namespace()}:{ref}"])
        out.append(_act(DECISION, here, it, None, f"{ptr}: {len(steps)} step(s) wait on it"))
    return out
