"""Detectors (PLAN-todo-tool.md §10.5, approved by Jacob 2026-10-12): a stall becomes
an item without anyone finding it.

A detector is data (vocab.json `detectors.list`): a command printing a JSON list of
findings, one per repo and cause, each {repo, subject, count, evidence, clears_with}.
`todo detect [--id D]` runs each command outside any lock, then reconciles under
the lock of every scanned store:

- a new finding adds one item of the detector's kind, keyed
  detector:<id>:<repo>:<subject> (the item's `detector` field and its repo);
- a finding seen again updates that item's count, evidence and last-seen day, and
  never adds a second;
- a finding gone closes the item with resolution roles.detector_resolution.

A run that fails (exit not 0, a timeout, output that is not a findings list, more
than `cap` findings) judges none of its items: it files one stall under the
reserved id `failed_id`, "detector D failed", with its stderr digest, which the
detector's next good run from the same store closes. Every run is recorded in the
store's records (`runs`), and `todo check` fails a detector gone silent there.

todo reads no roster: findings name repos, never agents."""
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

from .store import DATE_RE, TodoError, new_item
from .vocab import VOCAB

TODO = Path(__file__).resolve().parent.parent / "todo"
FINDING_KEYS = tuple("repo subject count evidence clears_with".split())
FIELDS = tuple("id subject count clears_with seen".split())  # what an item's detector field holds
RUN_KEYS = tuple("at exit ok findings why".split())  # one run, as records.runs holds it
LIST_ENV = "TODO_DETECTORS"  # a file holding the list in place of vocab.json's: fixtures and trial runs, said on every use
NOW_ENV = "TODO_NOW"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
NAME = re.compile(r"^[^\s:]+$")  # a repo in a key: no colon, no space

NEW, SEEN, CLEARED = "new", "seen", "cleared"
ORDER = (NEW, SEEN, CLEARED)


def spec():
    return VOCAB.detectors


def registered():
    """(detectors, source): vocab.json's list and None, or the list in the file
    TODO_DETECTORS names and that path. Either way every detector is checked."""
    path = os.environ.get(LIST_ENV)
    if not path:
        return spec()["list"], None
    try:
        lst = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise TodoError(f"{LIST_ENV}={path}: {e}")
    why = VOCAB.detector_list_problem(lst, spec()["failed_id"])
    if why:
        raise TodoError(f"{LIST_ENV}={path}: {why}")
    return lst, path


def now():
    """The time of a run, UTC to the second: TODO_NOW, else midnight of TODO_TODAY
    (a pinned day), else the clock."""
    forced = os.environ.get(NOW_ENV)
    if forced:
        if parse_time(forced) is None:
            raise TodoError(f"{NOW_ENV}={forced!r} is not YYYY-MM-DDTHH:MM:SSZ")
        return forced
    day = os.environ.get("TODO_TODAY")
    if day and DATE_RE.match(day):
        return day + "T00:00:00Z"
    return datetime.datetime.now(datetime.timezone.utc).strftime(TIME_FORMAT)


def parse_time(text):
    try:
        return datetime.datetime.strptime(str(text), TIME_FORMAT)
    except ValueError:
        return None


# -- one item ------------------------------------------------------------------

def is_detector_item(it):
    return it.get("kind") in VOCAB.detector_kinds


def key(det_id, repo, subject):
    return f"detector:{det_id}:{repo}:{subject}"


def key_of(it):
    d = it["detector"]
    return key(d["id"], it.get("repo"), d["subject"])


def field_problems(it):
    """Why an item's detector field is wrong for it, as phrases (check runs this)."""
    d = it.get("detector")
    if not is_detector_item(it):
        return [f"detector is set on a {it.get('kind')}: only a {', '.join(VOCAB.detector_kinds)} holds one"] \
            if d is not None else []
    if d is None:
        return []  # the `required` gate names it
    if not (isinstance(d, dict) and set(d) == set(FIELDS)):
        return [f"detector must be {{{', '.join(FIELDS)}}}"]
    out = [f"detector.{k} is not a non-empty one-line string" for k in ("id", "subject", "clears_with")
           if not (isinstance(d[k], str) and d[k].strip() and "\n" not in d[k])]
    if not (isinstance(d["count"], int) and not isinstance(d["count"], bool) and d["count"] >= 1):
        out.append("detector.count is not a whole number of at least 1")
    if not (isinstance(d["seen"], str) and DATE_RE.match(d["seen"])):
        out.append("detector.seen is not YYYY-MM-DD")
    if not (isinstance(it.get("repo"), str) and NAME.match(it["repo"])):
        out.append("a detector item names its repo (the finding's), with no colon or space")
    return out


# -- one run ---------------------------------------------------------------------

def finding_problem(f):
    """Why one finding is not {repo, subject, count, evidence, clears_with}, or None."""
    if not (isinstance(f, dict) and set(f) == set(FINDING_KEYS)):
        return f"is not exactly {{{', '.join(FINDING_KEYS)}}}"
    if not (isinstance(f["repo"], str) and NAME.match(f["repo"])):
        return f"repo {f['repo']!r} is not a repo name (no colon, no space)"
    for k in ("subject", "clears_with"):
        if not (isinstance(f[k], str) and f[k].strip() and "\n" not in f[k]):
            return f"{k} is not a non-empty one-line string"
    if not (isinstance(f["count"], int) and not isinstance(f["count"], bool) and f["count"] >= 1):
        return "count is not a whole number of at least 1 (a finding is rolled up, with its count)"
    if not isinstance(f["evidence"], str):
        return "evidence is not a string"
    return None


def parse(stdout):
    """(findings, None) from a command's output, or (None, why it is not a findings list)."""
    try:
        found = json.loads(stdout)
    except ValueError as e:
        return None, f"printed no JSON ({e})"
    if not isinstance(found, list):
        return None, "printed JSON that is not a list of findings"
    if len(found) > spec()["cap"]:
        return None, (f"printed {len(found)} findings, over the cap of {spec()['cap']}: roll them up, "
                      "one per repo and cause, with a count")
    seen = set()
    for n, f in enumerate(found, 1):
        why = finding_problem(f)
        if why:
            return None, f"finding {n} {why}"
        if (f["repo"], f["subject"]) in seen:
            return None, f"finding {n} repeats repo {f['repo']} and subject {f['subject']!r}"
        seen.add((f["repo"], f["subject"]))
    return found, None


def digest(stderr):
    """The last lines of a failing command's stderr, one line, for its stall item."""
    lines = [ln.strip()[:200] for ln in (stderr or "").splitlines() if ln.strip()]
    return " | ".join(lines[-spec()["digest_lines"]:]) or "(no stderr)"


def command_of(det, store_dir, root):
    subs = {"{todo}": str(TODO), "{store}": str(store_dir), "{root}": str(root)}
    out = []
    for a in det["command"]:
        for slot, value in subs.items():
            a = a.replace(slot, value)
        out.append(a)
    return out


def run(det, store_dir, root, at):
    """(findings or None, run record). Never raises: a failure is in the record's
    `why`, and findings is None then."""
    argv = command_of(det, store_dir, root)
    rec = {"at": at, "exit": None, "ok": False, "findings": None, "why": None}
    try:
        r = subprocess.run(argv, cwd=store_dir, capture_output=True, text=True, timeout=spec()["timeout_s"])
    except subprocess.TimeoutExpired:
        rec["why"] = f"timed out after {spec()['timeout_s']}s"
        return None, rec
    except OSError as e:
        rec["why"] = f"could not start {argv[0]}: {e}"
        return None, rec
    rec["exit"] = r.returncode
    if r.returncode != 0:
        rec["why"] = f"exited {r.returncode}: {digest(r.stderr)}"
        return None, rec
    found, why = parse(r.stdout)
    if why:
        rec["why"] = why + f"; stderr: {digest(r.stderr)}"
        return None, rec
    rec.update(ok=True, findings=len(found))
    return found, rec


def run_problem(rec):
    """Why a records.runs entry is malformed, or None (check runs this)."""
    if not (isinstance(rec, dict) and set(rec) == set(RUN_KEYS)):
        return f"is not exactly {{{', '.join(RUN_KEYS)}}}"
    if parse_time(rec["at"]) is None:
        return "at is not YYYY-MM-DDTHH:MM:SSZ"
    if not isinstance(rec["ok"], bool) or rec["ok"] != (rec["why"] is None):
        return "ok is true exactly when there is no why"
    return None


def silent(runs, detectors, at):
    """[(detector id, why)] of the detectors not run within stale_factor times their
    cadence before `at`: none at all in a store where none has run (detect is run
    from the stores that host it)."""
    if not runs:
        return []
    when = parse_time(at)
    out = []
    for det in detectors:
        rec = runs.get(det["id"])
        limit = datetime.timedelta(hours=det["cadence_hours"] * spec()["stale_factor"])
        last = parse_time(rec.get("at")) if isinstance(rec, dict) else None
        if last is None:
            out.append((det["id"], "has never run here, while other detectors have"))
        elif when - last > limit:
            out.append((det["id"], f"last ran {rec['at']}, more than {spec()['stale_factor']} x its cadence "
                                   f"({det['cadence_hours']}h) ago"))
    return out


# -- the plan of one detect -------------------------------------------------------

def cut(text):
    n = spec()["evidence_max"]
    text = str(text or "")
    return text if len(text) <= n else text[:n].rstrip() + " ..."


def title_of(det_id, f):
    t = f"{det_id}: {f['subject']}" + (f" ({f['count']})" if f["count"] > 1 else "")
    t = " ".join(t.replace("**", "").split())
    return t if len(t) <= 120 else t[:117].rstrip() + "..."


def failed_finding(det, here, why):
    return {"repo": here.repo, "subject": f"detector {det['id']} failed", "count": 1, "evidence": why,
            "clears_with": f"make {det['id']}'s command run clean, then todo detect --id {det['id']}"}


def _act(action, store, item, det_id, detail, changes=None):
    return {"action": action, "store": store, "item": item, "detector": det_id, "detail": detail,
            "changes": changes or {}}


def reconcile(det, findings, judged, open_by_key, ws, here, date):
    """The actions that make the items of detector `det` match its findings. An
    open item of it whose key is not found is closed only when `judged` holds its
    key (None: every key of this detector is judged)."""
    actions, found = [], set()
    for f in findings:
        k = key(det["id"], f["repo"], f["subject"])
        found.add(k)
        hit = open_by_key.get(k)
        field = {"id": det["id"], "subject": f["subject"], "count": f["count"], "clears_with": f["clears_with"],
                 "seen": date}
        if hit is None:
            target = ws.by_repo(f["repo"]) or here
            status = VOCAB.jacob_status if det["waits_on"] else VOCAB.role("default_status")
            it = new_item(title=title_of(det["id"], f), kind=det["kind"], status=status, evidence=cut(f["evidence"]),
                          repo=f["repo"], waits_on=det["waits_on"], added=date)
            it["detector"] = field
            actions.append(_act(NEW, target, it, det["id"], f"{f['repo']}: {f['subject']}"))
            continue
        s, it = hit
        changes = {}
        if it["detector"] != field:
            changes["detector"] = field
        for name, value in (("title", title_of(det["id"], f)), ("evidence", cut(f["evidence"]))):
            if it.get(name) != value:
                changes[name] = value
        if changes:
            actions.append(_act(SEEN, s, it, det["id"], f"count {f['count']}", changes))
    for k, (s, it) in sorted(open_by_key.items()):
        if it["detector"]["id"] != det["id"] or k in found or (judged is not None and k not in judged):
            continue
        actions.append(_act(CLEARED, s, it, det["id"], f"{it.get('repo')}: {it['detector']['subject']} no longer found"))
    return actions


def plan(ws, here, results, date):
    """(actions, notices) for the detectors run: results is [(det, findings or None,
    record)]. Writes nothing."""
    notices = []
    open_by_key = {}
    for s in ws.stores:
        for it in s.items:
            if not is_detector_item(it) or field_problems(it):
                continue
            k = key_of(it)
            if k in open_by_key:
                notices.append(f"{k} is held by two open items; {it['id']} is left alone (todo check names it)")
                continue
            open_by_key[k] = (s, it)
    actions, failures = [], []
    for det, findings, rec in results:
        if findings is None:
            failures.append(failed_finding(det, here, rec["why"]))
            continue
        actions += reconcile(det, findings, None, open_by_key, ws, here, date)
    meta = {"id": spec()["failed_id"], "kind": VOCAB.role("stall_kind"), "waits_on": None}
    judged = {key(meta["id"], here.repo, f"detector {det['id']} failed") for det, _, _ in results}
    actions += reconcile(meta, failures, judged, open_by_key, ws, here, date)
    return actions, notices


def still_reported(it, store_dir, root, detectors):
    """For `todo done` on a detector item: (True, why) when its detector, run now,
    still reports the finding or cannot be run; (False, None) when it does not."""
    d = it["detector"]
    if d["id"] == spec()["failed_id"]:
        target = d["subject"].split()[1] if len(d["subject"].split()) == 3 else None
        det = next((x for x in detectors if x["id"] == target), None)
        if det is None:
            return False, None  # that detector is no longer registered: nothing left to fail
        found, rec = run(det, store_dir, root, now())
        return (True, f"detector {det['id']} still fails ({rec['why']})") if found is None else (False, None)
    det = next((x for x in detectors if x["id"] == d["id"]), None)
    if det is None:
        return False, None
    found, rec = run(det, store_dir, root, now())
    if found is None:
        return True, f"detector {det['id']} could not be run to confirm the cause is gone ({rec['why']})"
    if any(f["repo"] == it.get("repo") and f["subject"] == d["subject"] for f in found):
        return True, f"detector {det['id']} still reports it; it clears with: {d['clears_with']}"
    return False, None
