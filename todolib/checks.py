"""`todo check`: every gate over one store, its history and its cross-repo links.

Each finding is (level, gate, where, message); FAIL makes the exit non-zero,
WARN and INFO never do. Every gate prints an `ok` line when it found nothing,
so a gate that silently stopped running shows up as a missing line.
"""
import json
import re
import subprocess

from . import approval, deps, plans, tags
from . import decisions as decide
from . import detect, syncplans
from .render import HEADER_PREFIX, is_sealed, render_store, unseal
from .store import (DATE_RE, HISTORY_KEYS, ID_RE, RECORDS_FILE, RECORDS_KEYS, SEAL_KEY, SEAL_STATES, STORE_KEYS,
                    HISTORY_FILE, RENDER_FILE, TodoError, git_toplevel, id_number, never_scanned, seal_state, today)
from .vocab import VOCAB

GATES = ["schema", "seal", "vocab", "required", "ids", "parents", "sizes", "blockers", "tags", "groups", "reports",
         "workspace", "render", "history", "records", "detectors"]
SINGLE_LINE = ["title", "probe", "done_when", "done_check", "retire", "resolution", "parent", "repo",
               "pointer", "hinges_on", "recommend", "chosen"]
# What an imported closed item may lack: its date (a Resolved bullet has none). Its
# resolution it never lacks: the import sets vocab.json's import_resolution (td-1),
# so a closed item without one is red wherever it came from (PLAN §5).
IMPORT_MAY_LACK = ("done",)


HAND_STATES = ("hand-edited", "hand-written")


def render_state(store):
    """absent | clean | stale (an unedited render, of another store or format:
    rewriting it loses nothing) | hand-edited (a render, changed) | hand-written
    (never rendered). An unsealed file equal to today's render without its seal
    was written by the render format before seals, so it is stale too."""
    if not store.render_path.is_file():
        return "absent"
    text = store.render_path.read_text()
    current = render_store(store)
    if text == current:
        return "clean"
    if is_sealed(text) or text == unseal(current):
        return "stale"
    return "hand-edited" if text.startswith(HEADER_PREFIX) else "hand-written"


def _empty(v):
    return v is None or v == "" or v == []


SHA_RE = re.compile(r"^[0-9a-f]{4,40}$")


def handoff_ok(h):
    """The shape `todo edit --handoff` writes: {date, text, commit}."""
    return (isinstance(h, dict) and set(h) == {"date", "text", "commit"}
            and isinstance(h["date"], str) and bool(DATE_RE.match(h["date"]))
            and isinstance(h["text"], str) and bool(h["text"].strip()) and "\n" not in h["text"]
            and (h["commit"] is None or (isinstance(h["commit"], str) and bool(SHA_RE.match(h["commit"])))))


def _one_line(v):
    return isinstance(v, str) and bool(v.strip()) and "\n" not in v


def approved_ok(a):
    """The shape `todo approve` writes: {by (vocab.json approval.by), date, source}."""
    return (isinstance(a, dict) and set(a) == {"by", "date", "source"} and a["by"] == VOCAB.approval_by
            and isinstance(a["date"], str) and bool(DATE_RE.match(a["date"])) and _one_line(a["source"]))


def dispatched_ok(d):
    """The shape `todo dispatch` writes: {date, text (one line, or null)}."""
    return (isinstance(d, dict) and set(d) == {"date", "text"}
            and isinstance(d["date"], str) and bool(DATE_RE.match(d["date"]))
            and (d["text"] is None or _one_line(d["text"])))


def plan_pins_problem(it):
    """Why the item's plan_pins is not what `--pin-plan` writes, or None: a non-empty
    list of {plan, digest, date}, one per plan:FILE§n tag the item still carries
    (a pin with no tag would be checked by stale-plans for a section the item no
    longer claims), a sha256 hex digest, a YYYY-MM-DD date."""
    pins = it.get("plan_pins")
    if pins is None:
        return None
    if not isinstance(pins, list) or not pins:
        return "plan_pins must be a non-empty list of {plan, digest, date}, or null"
    tagged = plans.refs(it)
    seen = set()
    for p in pins:
        if not (isinstance(p, dict) and set(p) == {"plan", "digest", "date"}):
            return f"plan_pins entry {p!r} is not {{plan, digest, date}}"
        if p["plan"] not in tagged or plans.split(p["plan"])[1] is None:
            return f"plan_pins pins {p['plan']!r}, which is no {plans.namespace()}:FILE§n tag of the item"
        if p["plan"] in seen:
            return f"plan_pins pins {p['plan']!r} twice"
        seen.add(p["plan"])
        if not (isinstance(p["digest"], str) and plans.DIGEST_RE.match(p["digest"])):
            return f"plan_pins {p['plan']}: digest is not a sha256 hex digest"
        if not (isinstance(p["date"], str) and DATE_RE.match(p["date"])):
            return f"plan_pins {p['plan']}: date is not YYYY-MM-DD"
    return None


def research_problem(value):
    """Why an item's `research` is malformed, or None: null, or a non-empty list of the
    research service's ids (vocab.json `research`). add, edit and check share it."""
    if value is None:
        return None
    if not (isinstance(value, list) and value and all(isinstance(x, str) and VOCAB.research_id.match(x) for x in value)):
        return (f"research must be a non-empty list of {VOCAB.research_service} ids matching "
                f"{VOCAB.research_id.pattern} (null when none)")
    if len(set(value)) != len(value):
        return "research names an id twice"
    return None


def check_item(it, where, store, out):
    iid = it.get("id", "?")
    fields = set(VOCAB.field_names())
    extra = sorted(set(it) - fields)
    missing = sorted(fields - set(VOCAB.optional_fields()) - set(it))
    if extra or missing:
        out.append(("FAIL", "schema", iid, f"fields differ from vocab.json: extra {extra}, missing {missing}"))
    kind, status, work = it.get("kind"), it.get("status"), it.get("work")
    if kind not in VOCAB.kinds:
        out.append(("FAIL", "vocab", iid, f"kind {kind!r} is not declared"))
    if status not in VOCAB.statuses:
        out.append(("FAIL", "vocab", iid, f"status {status!r} is not declared"))
    if work is not None and work not in VOCAB.works:
        out.append(("FAIL", "vocab", iid, f"work {work!r} is not declared"))
    if it.get("size") is not None and it["size"] not in VOCAB.sizes:
        out.append(("FAIL", "vocab", iid, f"size {it['size']!r} is not declared (one of {', '.join(VOCAB.sizes)})"))
    if where == "store" and status == VOCAB.closed:
        out.append(("FAIL", "schema", iid, f"status {status} in {store.path.name}: closed items live in {HISTORY_FILE} (todo done moves them)"))
    if where == "history" and status != VOCAB.closed:
        out.append(("FAIL", "schema", iid, f"status {status} in {HISTORY_FILE}: only closed items live there"))
    if where == "store":
        for f in ("done", "resolution"):
            if not _empty(it.get(f)):
                out.append(("FAIL", "schema", iid, f"{f} is set on an open item"))
    for f in SINGLE_LINE:
        v = it.get(f)
        if isinstance(v, str) and "\n" in v:
            out.append(("FAIL", "schema", iid, f"{f} spans lines; only evidence may"))
    title = it.get("title")
    if not isinstance(title, str) or not title.strip() or "**" in title:
        out.append(("FAIL", "schema", iid, "title must be one non-empty line without **"))
    if isinstance(it.get("evidence"), str) and any(ln.startswith("· ") for ln in it["evidence"].split("\n")):
        out.append(("FAIL", "schema", iid, "an evidence line starts with '· ', the render's field mark"))
    for f in ("added", "done"):
        v = it.get(f)
        if v is not None and not (isinstance(v, str) and DATE_RE.match(v)):
            out.append(("FAIL", "schema", iid, f"{f} {v!r} is not YYYY-MM-DD"))
    files = it.get("files")
    if files is not None and not (isinstance(files, list) and all(isinstance(x, str) for x in files)):
        out.append(("FAIL", "schema", iid, "files must be a list of paths"))
    why = research_problem(it.get("research"))
    if why:
        out.append(("FAIL", "schema", iid, why))
    blockers = it.get("blocked_by")
    if blockers is not None and not (isinstance(blockers, list) and blockers
                                     and all(isinstance(x, str) and ID_RE.match(x) for x in blockers)):
        out.append(("FAIL", "schema", iid, "blocked_by must be a non-empty list of item ids (null when none)"))
    rt = it.get("reported_to")
    if rt is not None:
        if not isinstance(rt, dict) or set(rt) != {"repo", "date", "their_id"} or not DATE_RE.match(str(rt.get("date"))):
            out.append(("FAIL", "schema", iid, "reported_to must be {repo, date (YYYY-MM-DD), their_id}"))
    if it.get("handoff") is not None and not handoff_ok(it["handoff"]):
        out.append(("FAIL", "schema", iid, "handoff must be {date (YYYY-MM-DD), text (one non-empty line), "
                                           "commit (a hex sha, or null)}: set it with todo edit --handoff"))
    if it.get("approved") is not None and not approved_ok(it["approved"]):
        out.append(("FAIL", "schema", iid, f"approved must be {{by ({VOCAB.approval_by}), date (YYYY-MM-DD), "
                                           "source (one non-empty line)}: set it with todo approve"))
    if it.get("dispatched") is not None:
        if not dispatched_ok(it["dispatched"]):
            out.append(("FAIL", "schema", iid, "dispatched must be {date (YYYY-MM-DD), text (one line, or null)}: "
                                               "set it with todo dispatch"))
        if it.get("approved") is None:
            out.append(("FAIL", "schema", iid, "dispatched without approved: todo dispatch refuses an unapproved "
                                               "item, so this was written around the CLI"))
    elif where == "store" and approval.is_rule(it.get("approved")):
        out.append(("FAIL", "schema", iid, f"a rule {VOCAB.approval_rule['id']} approval stored on an item not "
                                           "dispatched: only todo dispatch stores one, and dispatch --clear removes it; "
                                           "the rule is judged afresh at every read (todo approve --clear it)"))
    waits_why = waits_on_problem(it, require=False)
    if waits_why:
        out.append(("FAIL", "vocab", iid, waits_why))
    pin_why = plan_pins_problem(it)
    if pin_why:
        out.append(("FAIL", "schema", iid, pin_why + ": set it with todo edit ID --pin-plan"))
    imported = it.get("imported") is not None
    for f in VOCAB.required(it):
        if _empty(it.get(f)):
            if where == "history" and imported and f in IMPORT_MAY_LACK:
                continue  # counted below: a Resolved bullet carries no date
            out.append(("FAIL", "required", iid, f"{kind}/{status} requires {f}"))
    reserved = VOCAB.role("import_resolution")
    if it.get("resolution") == reserved and not imported:
        out.append(("FAIL", "vocab", iid, f"resolution {reserved!r} is set by todo import only, and this item was not imported"))
    stepped = VOCAB.role("step_resolution")
    if it.get("resolution") == stepped and (_empty(it.get("done_check")) or kind != VOCAB.role("step_kind")):
        out.append(("FAIL", "vocab", iid, f"resolution {stepped!r} is set by todo steps --run only, on a "
                                          f"{VOCAB.role('step_kind')} whose done_check passed, and this item has none"))
    for why in decide.field_problems(it):
        out.append(("FAIL", "schema", iid, why))
    for why in detect.field_problems(it):
        out.append(("FAIL", "schema", iid, why + " (todo detect sets it)"))
    detected = VOCAB.role("detector_resolution")
    if it.get("resolution") == detected and (not detect.is_detector_item(it) or it.get("detector") is None):
        out.append(("FAIL", "vocab", iid, f"resolution {detected!r} is set by todo detect only, on an item whose "
                                          "detector no longer reports it, and this item has no detector"))
    if it.get("plan_step") is not None:  # a step without one fails `required` above
        for why in syncplans.plan_step_problems(it):
            out.append(("FAIL", "schema", iid, why + " (todo sync-plans sets it)"))
    if where == "history":
        for why in decide.resolution_problems(it):
            out.append(("FAIL", "vocab", iid, why))
    else:
        # One written before the decision fields (no pointer) is listed by check_waiting instead.
        if decide.is_decision(it) and it.get("pointer") is not None and status != decide.D["status"]:
            out.append(("FAIL", "vocab", iid, f"a {kind} is {decide.D['status']} until Jacob answers it, and this one "
                                              f"is {status}: todo approve, todo done --as or todo answer closes it"))
        if it.get("chosen") is not None:
            out.append(("FAIL", "schema", iid, "chosen is set on an open item: it is set as the item closes"))


def waits_on_problem(item, require=True):
    """Why an item's waits_on is wrong for it, or None (PLAN-todo-tool.md §10.2 step 2):
    a declared value of the declared form, on a waiting-jacob item only (a closed one
    keeps what it had). `require`: a waiting-jacob item without one is wrong too; check
    passes False and lists such items instead (written before the field existed), the
    CLI passes True wherever it makes the item or sets its status."""
    w, status = item.get("waits_on"), item.get("status")
    if w is not None:
        why = VOCAB.waits_on_problem(w)
        if why:
            return why
        if status not in (VOCAB.jacob_status, VOCAB.closed):
            return f"waits_on is for a {VOCAB.jacob_status} item, and this one is {status}: clear it with --waits-on ''"
    elif require and status == VOCAB.jacob_status:
        return f"a {status} item needs --waits-on, what clears it: {VOCAB.waits_on_forms()}"
    return None


def check_waiting(store, out):
    """List, never fail, the open waiting-jacob items that name nothing they wait on:
    written before waits_on existed, so `todo blockers` cannot group them."""
    bare = [it["id"] for it in store.items if it.get("status") == VOCAB.jacob_status and it.get("waits_on") is None]
    if bare:
        shown = ", ".join(bare[:10]) + (f" (+{len(bare) - 10})" if len(bare) > 10 else "")
        out.append(("INFO", "required", "-", f"{len(bare)} {VOCAB.jacob_status} item(s) name no waits_on, so "
                                             f"`todo blockers` cannot group them: {shown} -- todo edit ID --waits-on "
                                             f"({VOCAB.waits_on_forms()})"))
    lacking = [f"{it['id']} ({', '.join(decide.missing(it))})" for it in store.items
               if decide.is_decision(it) and decide.missing(it)]
    if lacking:
        n = decide.D["max_listed"]
        out.append(("INFO", "required", "-", f"{len(lacking)} open {VOCAB.role('decision_kind')}(s) lack what "
                                             f"`todo decisions` tables them by: {'; '.join(lacking[:n])}"
                                             + (f" (+{len(lacking) - n})" if len(lacking) > n else "")
                                             + " -- todo edit ID --pointer --hinges-on --recommend"))


def committed_records(store):
    """The records file as git's HEAD holds it: (data or None, why not read)."""
    top = git_toplevel(store.dir)
    if not top:
        return None, "not a git repo"
    rel = store.records_path.resolve().relative_to(top.resolve())
    shown = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=top, capture_output=True, text=True)
    if shown.returncode != 0:
        return None, "not committed"
    try:
        return json.loads(shown.stdout), None
    except ValueError:
        return None, "does not parse at HEAD"


def table_problem(t):
    """Why a decisions table record is not what `todo decisions` writes, or None."""
    if not (isinstance(t, dict) and set(t) == {"id", "date", "rows", "supersedes", "answers"}):
        return "is not {id, date, rows, supersedes, answers}"
    if decide.table_number(t["id"]) is None or not (isinstance(t["date"], str) and DATE_RE.match(t["date"])):
        return f"id {t['id']!r} or date {t['date']!r} is malformed ({decide.D['table_prefix']}-N, YYYY-MM-DD)"
    rows = t["rows"]
    if not (isinstance(rows, list) and rows and all(
            isinstance(r, dict) and set(r) == {"n", "item", "repo", "status", "cells"} and isinstance(r["cells"], list)
            and len(r["cells"]) == 3 and ID_RE.match(str(r["item"])) for r in rows)):
        return "rows must be a non-empty list of {n, item, repo, status, cells (3)}"
    if [r["n"] for r in rows] != list(range(1, len(rows) + 1)):
        return "rows are not numbered 1..n"
    if not isinstance(t["supersedes"], list) or not isinstance(t["answers"], list):
        return "supersedes and answers must be lists"
    return None


def check_records(store, out):
    """The decision tables (PLAN-todo-tool.md §10.3b): the keys, each table's shape,
    and append-only against git's HEAD -- a table committed keeps its id, date, rows
    and supersedes, and its answers only grow."""
    if store.records is None:
        out.append(("INFO", "records", "-", f"no {RECORDS_FILE}: no table recorded yet"))
        return
    data = store.records
    if set(data) != set(RECORDS_KEYS) or data.get("repo") != store.repo:
        out.append(("FAIL", "records", "-", f"{RECORDS_FILE} must hold exactly {RECORDS_KEYS}, repo {store.repo}"))
        return
    tables = data["tables"] if isinstance(data["tables"], list) else []
    ids = []
    for t in tables:
        why = table_problem(t)
        if why:
            out.append(("FAIL", "records", str(t.get("id", "?") if isinstance(t, dict) else "?"), "table " + why))
        elif t["id"] in ids:
            out.append(("FAIL", "records", t["id"], "two tables share this id"))
        else:
            ids.append(t["id"])
    head, why = committed_records(store)
    if head is None:
        out.append(("INFO", "records", "-", f"{RECORDS_FILE} {why}: the append-only audit against HEAD is skipped"))
        return
    now = {t.get("id"): t for t in tables if isinstance(t, dict)}
    for old in head.get("tables") or []:
        tid = old.get("id")
        cur = now.get(tid)
        if cur is None:
            out.append(("FAIL", "records", str(tid), "was committed and is gone: a table record is never removed"))
        elif any(cur.get(k) != old.get(k) for k in ("date", "rows", "supersedes")):
            out.append(("FAIL", "records", str(tid), "changed since HEAD: a table record never changes"))
        elif (cur.get("answers") or [])[:len(old.get("answers") or [])] != (old.get("answers") or []):
            out.append(("FAIL", "records", str(tid), "an answer committed at HEAD changed or is gone: answers are appended only"))


def check_detectors(store, out):
    """The detectors' runs and items (PLAN-todo-tool.md §10.5): each recorded run is
    well formed; a detector not run within stale_factor times its cadence, in a
    store whose records hold any run, is a FAIL (one present, silent and not running
    is the worst state there is); and no two open items of this store hold one key."""
    runs = store.runs
    if not isinstance(runs, dict):
        out.append(("FAIL", "detectors", "-", f"{RECORDS_FILE} runs is not an object of detector id -> last run"))
        return
    for did, rec in sorted(runs.items()):
        why = detect.run_problem(rec)
        if why:
            out.append(("FAIL", "detectors", str(did), "last run " + why + " (todo detect records it)"))
    try:
        registered, _ = detect.registered()
        at = detect.now()
    except TodoError as e:
        out.append(("FAIL", "detectors", "-", str(e)))
        return
    for did, why in detect.silent(runs, registered, at):
        out.append(("FAIL", "detectors", did, why + f": run todo detect --id {did}, or find why it stopped"))
    keys = {}
    for it in store.items:
        if detect.is_detector_item(it) and not detect.field_problems(it) and it.get("detector") is not None:
            k = detect.key_of(it)
            if k in keys:
                out.append(("FAIL", "detectors", it["id"], f"holds {k}, as {keys[k]} does: one item per finding"))
            keys.setdefault(k, it["id"])


def check_ids(store, out):
    seen = {}
    for where, items in (("store", store.items), ("history", store.closed)):
        for it in items:
            iid = it.get("id")
            m = ID_RE.match(iid or "")
            if not m or m.group(1) != store.prefix:
                out.append(("FAIL", "ids", str(iid), f"id is not {store.prefix}-N"))
                continue
            if iid in seen:
                where_both = "both files" if seen[iid] != where else f"{where} twice"
                hint = " (an interrupted close: `todo done ID` finishes it)" if seen[iid] != where else ""
                out.append(("FAIL", "ids", iid, f"id appears in {where_both}{hint}"))
            seen[iid] = where
            if id_number(iid) >= store.data.get("next", 0):
                out.append(("FAIL", "ids", iid, f"id number is not below next ({store.data.get('next')}): it could be handed out again"))


def outside_scan(ws, item_id):
    """True when item_id is a well-formed id whose prefix no scanned store holds:
    a parent there can be neither confirmed nor refuted by this scan (td-15, a
    report arriving from a repo outside a narrow root), the same reason an
    unpaired report is a WARN. A prefix some scanned store holds is judged, and a
    malformed id is never outside the scan: both stay red when they do not resolve."""
    m = ID_RE.match(item_id or "")
    return bool(m) and not any(s.data and s.prefix == m.group(1) for s in ws.stores)


def check_parents(store, ws, out):
    for where, items in (("store", store.items), ("history", store.closed)):
        for it in items:
            p = it.get("parent")
            if p is None:
                continue
            if ws.find(p)[0] is None:
                if outside_scan(ws, p):
                    out.append(("WARN", "parents", it["id"], f"parent {p} unchecked: no scanned store has prefix {ID_RE.match(p).group(1)} (the scan root is {ws.root}); a check whose scan reaches that store judges it"))
                else:
                    out.append(("FAIL", "parents", it["id"], f"parent {p} resolves in no scanned store or history"))
                continue
            chain, cur = {it["id"]}, p
            while cur:
                if cur in chain:
                    out.append(("FAIL", "parents", it["id"], f"parent chain loops back through {cur}"))
                    break
                chain.add(cur)
                nxt = ws.find(cur)[0]
                cur = nxt.get("parent") if nxt else None


def children_of(ws, item_id):
    """Ids of every item, open or closed, in any scanned store, whose parent is item_id."""
    return [it["id"] for s in ws.stores for it in s.items + s.closed if it.get("parent") == item_id]


def check_sizes(store, ws, out):
    """PLAN-small-tasks.md §2: an item too big for one checkpoint (the size vocab.json
    marks `ready: false`) is split into children before anyone starts it, so an
    open one with none fails. An unsized open item is counted: it is never ready."""
    unsized = 0
    for it in store.items:
        if it.get("size") is None:
            unsized += 1
        elif it["size"] == VOCAB.split_size and not children_of(ws, it["id"]):
            out.append(("FAIL", "sizes", it["id"], f"size {VOCAB.split_size} and no children: `todo split {it['id']}` it into {' and '.join(VOCAB.ready_sizes)} items first"))
    if unsized:
        out.append(("INFO", "sizes", "-", f"{unsized} open item(s) unsized: never ready until `todo edit ID --size` ({'|'.join(VOCAB.sizes)})"))


def check_blockers(store, ws, out):
    """Every blocked_by id resolves (open or closed, any scanned store), and no open
    item's blockers lead back to it (PLAN-todo-tool.md §9 step 3)."""
    for where, items in (("store", store.items), ("history", store.closed)):
        for it in items:
            blockers = it.get("blocked_by")
            if not isinstance(blockers, list):
                continue
            for b in blockers:
                if not isinstance(b, str) or ws.find(b)[0] is not None:
                    continue
                if outside_scan(ws, b):
                    out.append(("WARN", "blockers", it["id"], f"blocked_by {b} unchecked: no scanned store has prefix {ID_RE.match(b).group(1)} (the scan root is {ws.root})"))
                else:
                    out.append(("FAIL", "blockers", it["id"], f"blocked_by {b} is in neither todo.json nor todo-history.json of any scanned store"))
            if where == "store":
                path = deps.cycle(ws, it["id"], [b for b in blockers if isinstance(b, str)])
                if path:
                    out.append(("FAIL", "blockers", it["id"], f"blocked_by cycle: {' -> '.join(path)}; nothing in it can ever be ready"))


def check_tags(store, ws, out):
    """Every stored tag is in the vocabulary and in a namespace that is set by hand,
    and every ref:todo:<id> tag resolves (PLAN-services.md §3: a dangling ref: is a
    failure). A ref: to another service is unchecked until a registry answers for
    it, and counted, never passed silently."""
    foreign = 0
    for it in list(store.items) + list(store.closed):
        if isinstance(it.get("research"), list):
            foreign += len(it["research"])  # its derived ref:research: tags, as unchecked as a stored one
        given = it.get("tags")
        if given is None:
            continue
        if not (isinstance(given, list) and given and all(isinstance(t, str) for t in given)):
            out.append(("FAIL", "schema", it["id"], "tags must be a non-empty list of <namespace>:<value> (null when none)"))
            continue
        for t in given:
            why = tags.problem(t, stored=True)
            if why:
                out.append(("FAIL", "tags", it["id"], why))
                continue
            target = tags.ref_target(t)
            if tags.is_foreign_ref(t):
                foreign += 1
            elif target is not None and ws.find(target)[0] is None:
                if outside_scan(ws, target):
                    out.append(("WARN", "tags", it["id"], f"{t} unchecked: no scanned store has prefix {target.split('-')[0]} (the scan root is {ws.root})"))
                else:
                    out.append(("FAIL", "tags", it["id"], f"{t} is dangling: {target} is in no scanned store or history"))
    if foreign:
        out.append(("INFO", "tags", "-", f"{foreign} ref: tag(s) name another service's record: unchecked until a registry resolves them"))


def check_groups(store, ws, out):
    """A heading is not an item (PLAN-todo-tool.md §10.2 step 4): an open item with
    no work, used as a group by open items (their parent, or a todo.group: tag
    naming its id), is a WARN, so a store still holding headings is not red while
    its owner converts them. Not a report (its work is the owner's). A split item
    with no work is one too: the imported headings inc-2..12 are size L."""
    users = {}
    for s in ws.stores:
        for it in s.items:
            for g in [it.get("parent")] + tags.group_names(it):
                if g:
                    users.setdefault(g, []).append(it["id"])
    for it in store.items:
        if it.get("work") or it.get("kind") == VOCAB.role("report_kind"):
            continue
        who = list(dict.fromkeys(users.get(it["id"], [])))
        if who:
            shown = ", ".join(who[:5]) + (f" (+{len(who) - 5})" if len(who) > 5 else "")
            out.append(("WARN", "groups", it["id"], f"a heading, not an item: it has no work and {len(who)} open "
                        f"item(s) use it as a group ({shown}). Tag them {tags.GROUP_NS}:{it['id']} "
                        f"(todo edit ID --tags ...), then close it (PLAN-todo-tool.md §10.2 step 4)"))


def check_reports(store, ws, out):
    for it in store.items:
        rt = it.get("reported_to")
        if not isinstance(rt, dict):
            continue
        if never_scanned(rt.get("repo")):
            out.append(("INFO", "reports", it["id"], f"relayed by hand: {rt.get('repo')!r} is a hidden folder, which the scan never enters, so this report never pairs; close it by its done_when"))
            continue
        owner = ws.by_repo(rt.get("repo"))
        if owner is None:
            out.append(("WARN", "reports", it["id"], f"unpaired: no store for repo {rt.get('repo')!r} in the scan (not migrated yet?); pair it later with `todo report {it['id']} --to {rt.get('repo')}`"))
            continue
        their = rt.get("their_id")
        if not their:
            if it.get("imported") is not None:
                # Read from a hand-written TODO.md: the owner may hold it under any id, or
                # never have had it; a guess at either is worse than saying so.
                out.append(("WARN", "reports", it["id"], f"imported, not paired with {rt['repo']}'s store: `todo edit {it['id']} --reported-to {rt['repo']}:THEIR_ID` if it holds the counterpart, else `todo report {it['id']} --to {rt['repo']}` writes one"))
            else:
                out.append(("FAIL", "reports", it["id"], f"{rt['repo']} has a store now: pair it with `todo report {it['id']} --to {rt['repo']}`"))
            continue
        c, where = owner.find(their)
        if c is None:
            out.append(("FAIL", "reports", it["id"], f"counterpart {their} is in neither {rt['repo']}'s store nor its history"))
        elif c.get("parent") != it["id"]:
            out.append(("FAIL", "reports", it["id"], f"counterpart {their} has parent {c.get('parent')}, not {it['id']}"))
        elif where == "history":
            out.append(("INFO", "reports", it["id"], f"counterpart {their} closed {c.get('done') or '(undated)'}: {c.get('resolution') or ''} -- close yours with todo done"))
    answered = []
    for it in store.items:
        p = it.get("parent")
        if not p or store.owns(p):
            continue
        parent, _, pstore = ws.find(p)
        rt = (parent or {}).get("reported_to")
        if isinstance(rt, dict) and rt.get("repo") == store.repo:
            if rt.get("their_id") != it["id"]:
                out.append(("FAIL", "reports", it["id"], f"parent {p} in {pstore.repo} points at {rt.get('their_id')}, not here"))
            else:
                answered.append(it["id"])
    if answered:
        out.append(("INFO", "reports", "-", f"{len(answered)} report(s) from other repos still open here: {', '.join(answered)}"))


def check_workspace(store, ws, out):
    for s in ws.stores:
        if s is store or not s.data:
            continue
        if s.data.get("prefix") == store.prefix:
            out.append(("FAIL", "workspace", "-", f"prefix {store.prefix} is also used by {s.dir}: ids would collide"))
        if s.data.get("repo") == store.repo:
            out.append(("FAIL", "workspace", "-", f"repo name {store.repo} is also used by {s.dir}: reports could not tell them apart"))
    for e in ws.errors:
        out.append(("WARN", "workspace", "-", f"a scanned store did not load: {e}"))


def check_render(store, out):
    state = render_state(store)
    if state == "clean":
        pass
    elif state == "absent":
        out.append(("FAIL", "render", "-", f"{RENDER_FILE} missing: run todo render"))
    elif state == "stale":
        out.append(("FAIL", "render", "-", f"{RENDER_FILE} is a stale render: unedited, but not the render of todo.json "
                    "as it is now (the render format changed, or todo.json changed without a re-render). "
                    "`todo render` rewrites it; nothing to recover, nothing recorded"))
    else:
        gate_from = store.data.get("render_gate_from") or "0000-00-00"
        level = "WARN" if today() < gate_from else "FAIL"
        what = "edited by hand since it was rendered" if state == "hand-edited" else "hand-written, never rendered"
        tail = f" (a counted warning until {gate_from})" if level == "WARN" else ""
        out.append((level, "render", "-", f"{RENDER_FILE} is {what}: `todo import {RENDER_FILE}` recovers new bullets, `todo render --force` keeps the diff in todo.json and rewrites it{tail}"))
    edits = store.data.get("hand_edits") or []
    if edits:
        out.append(("INFO", "render", "-", f"hand edits recorded: {len(edits)} (todo.json hand_edits)"))


def history_versions(store):
    """[(sha, items-by-id)] for every committed version of the history file."""
    top = git_toplevel(store.dir)
    if not top:
        return None
    rel = store.history_path.resolve().relative_to(top.resolve())
    log = subprocess.run(["git", "log", "--format=%h", "--", str(rel)], cwd=top, capture_output=True, text=True)
    versions = []
    for sha in log.stdout.split():
        shown = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=top, capture_output=True, text=True)
        if shown.returncode != 0:
            continue  # the commit deleted the file; the next older one still counts
        try:
            items = json.loads(shown.stdout).get("items", [])
        except ValueError:
            versions.append((sha, None))
            continue
        versions.append((sha, {it.get("id"): it for it in items}))
    return versions


def check_history(store, out):
    if store.history is None:
        out.append(("FAIL", "history", "-", f"{HISTORY_FILE} missing (todo init writes it; it is never deleted)"))
        return
    if set(store.history) != expected_keys(store.history, HISTORY_KEYS) or store.history.get("repo") != store.repo:
        out.append(("FAIL", "history", "-", f"{HISTORY_FILE} must hold exactly {HISTORY_KEYS}, repo {store.repo}"))
    undated = [it["id"] for it in store.closed if it.get("imported") and not it.get("done")]
    if undated:
        out.append(("INFO", "history", "-", f"{len(undated)} imported closed item(s) carry no date (a Resolved bullet has none); their evidence holds the bullet text"))
    versions = history_versions(store)
    if versions is None:
        out.append(("INFO", "history", "-", "not a git repo: the append-only audit against the git log is skipped here"))
        return
    now = {it.get("id"): it for it in store.closed}
    for sha, items in versions:
        if items is None:
            out.append(("FAIL", "history", "-", f"{HISTORY_FILE} at {sha} does not parse"))
            continue
        for iid, it in items.items():
            if iid not in now:
                out.append(("FAIL", "history", iid, f"was in {HISTORY_FILE} at {sha} and is gone: history is append-only"))
            elif now[iid] != it:
                out.append(("FAIL", "history", iid, f"changed since {sha}: history entries are never edited"))


def expected_keys(data, keys):
    """A file written before seals (format 1) lacks the seal key and nothing else."""
    return set(keys) - ({SEAL_KEY} if seal_state(data) == "legacy" else set())


def check_seal(store, out):
    """Both store files carry a seal over their content that the CLI rewrites on
    every write (PLAN-todo-tool.md §9, the gap his question found): a file changed
    around the CLI fails here, however well-formed. A file written before seals
    is a WARN until the next CLI write seals it, unless git's last commit of it, or
    a store file beside it, was sealed (store.load calls that "downgraded"): then
    the seal was removed by hand."""
    for name, state in store.seals.items():
        if state == "sealed":
            continue
        if state == "legacy":
            out.append(("WARN", "seal", "-", f"{name}: {SEAL_STATES[state]} (any `todo add`, `edit` or `done` here does it)"))
        else:
            out.append(("FAIL", "seal", "-", f"{name}: {SEAL_STATES[state]}. Restore it (git checkout -- {name}) and make the change with the CLI, or, having read the diff, `todo reseal --reason R`"))


def check_store(store, ws):
    out = []
    check_seal(store, out)
    if set(store.data) != expected_keys(store.data, STORE_KEYS):
        out.append(("FAIL", "schema", "-", f"todo.json keys {sorted(store.data)}, expected {STORE_KEYS}"))
    for it in store.items:
        check_item(it, "store", store, out)
    for it in store.closed:
        check_item(it, "history", store, out)
    check_waiting(store, out)
    check_ids(store, out)
    check_parents(store, ws, out)
    check_sizes(store, ws, out)
    check_blockers(store, ws, out)
    check_tags(store, ws, out)
    check_groups(store, ws, out)
    check_reports(store, ws, out)
    check_workspace(store, ws, out)
    check_render(store, out)
    check_history(store, out)
    check_records(store, out)
    check_detectors(store, out)
    return out


def summary(store, findings):
    """`todo check --json` for one store: what report() prints, as data. Every gate
    is named with its worst level, so a gate that found nothing reads ok, never absent."""
    gates = {}
    for gate in GATES:
        levels = {f[0] for f in findings if f[1] == gate}
        gates[gate] = "FAIL" if "FAIL" in levels else ("WARN" if "WARN" in levels else "ok")
    failed = sum(f[0] == "FAIL" for f in findings)
    return {"repo": store.repo, "dir": str(store.dir), "open_items": len(store.items), "closed_items": len(store.closed),
            "ok": failed == 0, "failed": failed, "warnings": sum(f[0] == "WARN" for f in findings), "gates": gates,
            "findings": [{"level": lv, "gate": g, "where": w, "message": m} for lv, g, w, m in findings]}


def report(store, findings):
    """Lines to print, and the exit code."""
    lines = []
    for gate in GATES:
        mine = [f for f in findings if f[1] == gate]
        bad = [f for f in mine if f[0] in ("FAIL", "WARN")]
        for level, _, where, msg in mine:
            lines.append(f"  {level:<5} {gate:<9} {where:<8} {msg}")
        if not bad:
            lines.append(f"  ok    {gate}")
    fails = sum(f[0] == "FAIL" for f in findings)
    warns = sum(f[0] == "WARN" for f in findings)
    lines.append(f"todo check {store.repo}: {len(store.items)} open, {len(store.closed)} closed; "
                 f"{fails} failed, {warns} warning(s)")
    return lines, (1 if fails else 0)
