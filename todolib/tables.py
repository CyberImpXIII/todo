"""The workspace's areas and projects (PLAN-todo-tool.md §11, step 1a, tl-720).

Both are records, never names in code: they live in the records file
(todo-records.json, keys `areas` and `projects`) of the store at the scan root,
the workspace's own store, wherever a command runs from. An area is
{id, name, doc, added}; a project is {id: pj-N, name, areas, priority, plans,
repos, added}, its priority null until Jacob sets one (`todo priority`, tl-721)
and then {value, source, by, date}.

One reader for each rule: `findings` (`problems`, then `references`) is what
`todo check` reports (gate `records`) and what every write refuses before it
saves when the write made it, so a write cannot leave a table check would fail;
`resolve_areas` and `project` refuse an id neither table holds."""
import re

from .store import DATE_RE, TodoError
from .vocab import VOCAB

AREA_KEYS = ("id", "name", "doc", "added")
PROJECT_KEYS = ("id", "name", "areas", "priority", "plans", "repos", "added")
PRIORITY_KEYS = ("value", "source", "by", "date")
PLAN_FILE = re.compile(r"^PLAN-[\w.-]+\.md$")


def project_id_re():
    return re.compile(r"^%s-([1-9][0-9]*)$" % re.escape(VOCAB.project_prefix))


def home(ws):
    """The store at the scan root, which holds the tables, or a TodoError saying
    there is none."""
    root = ws.root.resolve()
    for s in ws.stores:
        if s.data and s.dir.resolve() == root:
            return s
    raise TodoError(f"no store at the scan root {root}: the areas and projects tables live in the "
                    f"workspace's own store (PLAN-todo-tool.md §11); `todo -C {root} init --prefix P` starts one")


def is_home(store, ws):
    return store.dir.resolve() == ws.root.resolve()


def _line(v):
    return isinstance(v, str) and v.strip() == v and bool(v) and "\n" not in v


def _ids(rows):
    return [r.get("id") for r in rows if isinstance(r, dict)]


def area_problem(a):
    """Why one area row is not what `todo area-add` writes, or None."""
    if not (isinstance(a, dict) and set(a) == set(AREA_KEYS)):
        return f"holds {sorted(a) if isinstance(a, dict) else type(a).__name__}, not {list(AREA_KEYS)}"
    if not (isinstance(a["id"], str) and VOCAB.area_id.match(a["id"])):
        return f"id {a['id']!r} is not of the form {VOCAB.area_id.pattern} (vocab.json workspace_tables.area_id)"
    for k in ("name", "doc"):
        if not _line(a[k]):
            return f"{k} is not one non-empty line"
    if not (isinstance(a["added"], str) and DATE_RE.match(a["added"])):
        return "added is not a YYYY-MM-DD date"
    return None


def priority_problem(p):
    """Why a project's priority is neither null nor {value, source, by, date}, or None."""
    if p is None:
        return None
    if not (isinstance(p, dict) and set(p) == set(PRIORITY_KEYS)):
        return f"priority is null or {{{', '.join(PRIORITY_KEYS)}}}"
    if p["value"] not in VOCAB.priorities:
        return f"priority {p['value']!r} is not one of {', '.join(VOCAB.priorities)} (vocab.json priority)"
    if not (_line(p["source"]) and _line(p["by"])):
        return "priority source and by are each one non-empty line (only Jacob sets one, with his words)"
    if not (isinstance(p["date"], str) and DATE_RE.match(p["date"])):
        return "priority date is not a YYYY-MM-DD date"
    return None


def project_problem(p, area_ids):
    """Why one project row is not what the CLI writes, or None. Its areas must be
    rows of the areas table (`area_ids`)."""
    if not (isinstance(p, dict) and set(p) == set(PROJECT_KEYS)):
        return f"holds {sorted(p) if isinstance(p, dict) else type(p).__name__}, not {list(PROJECT_KEYS)}"
    if not (isinstance(p["id"], str) and project_id_re().match(p["id"])):
        return f"id {p['id']!r} is not {VOCAB.project_prefix}-N"
    if not _line(p["name"]):
        return "name is not one non-empty line"
    for k in ("areas", "plans", "repos"):
        v = p[k]
        if not (isinstance(v, list) and all(isinstance(x, str) and x for x in v) and len(set(v)) == len(v)):
            return f"{k} is not a list of distinct names"
    if not p["areas"]:
        return "names no area: a project has one or more"
    unknown = [a for a in p["areas"] if a not in area_ids]
    if unknown:
        return f"names area(s) {unknown} the areas table does not hold"
    bad = [x for x in p["plans"] if not PLAN_FILE.match(x)]
    if bad:
        return f"plans {bad} are not PLAN-<name>.md files"
    why = priority_problem(p["priority"])
    if why:
        return why
    if not (isinstance(p["added"], str) and DATE_RE.match(p["added"])):
        return "added is not a YYYY-MM-DD date"
    return None


def problems(records):
    """[(where, why)] for the tables in a records document: each row's shape, ids
    and project names unique, every area a project names a row of the areas table.
    Absent tables read as empty."""
    out = []
    records = records if isinstance(records, dict) else {}
    areas = records.get("areas", [])
    projects = records.get("projects", [])
    for key, rows in (("areas", areas), ("projects", projects)):
        if not isinstance(rows, list):
            out.append(("-", f"{key} is not a list"))
    if out:
        return out
    seen = set()
    for a in areas:
        why = area_problem(a)
        where = str(a.get("id", "?")) if isinstance(a, dict) else "?"
        if why:
            out.append((where, "area " + why))
        elif a["id"] in seen:
            out.append((where, "two areas share this id"))
        seen.add(where)
    area_ids = set(_ids(areas))
    seen, names = set(), {}
    for p in projects:
        why = project_problem(p, area_ids)
        where = str(p.get("id", "?")) if isinstance(p, dict) else "?"
        if why:
            out.append((where, "project " + why))
            continue
        if p["id"] in seen:
            out.append((where, "two projects share this id"))
        seen.add(p["id"])
        other = names.setdefault(p["name"].casefold(), p["id"])
        if other != p["id"]:
            out.append((where, f"has the name of {other}: one row per project"))
    return out


def references(projects, ws, plans_root):
    """[(where, why)] for what a project names outside the tables: a repo that is no
    scanned store's key (the key `todo repos` prints, PLAN-todo-tool.md §11), a plan
    with no file in `plans_root`. Unjudged (None) while a scanned store could not be
    read: that store may hold the repo."""
    if ws.errors:
        return None
    keys = {s.repo for s in ws.stores if s.data}
    out = []
    for p in projects if isinstance(projects, list) else []:
        if not isinstance(p, dict):
            continue
        for r in p.get("repos") or []:
            if r not in keys:
                out.append((str(p.get("id")), f"repo {r!r} is no scanned store's key (todo repos lists them)"))
        for f in p.get("plans") or []:
            if not (plans_root / f).is_file():
                out.append((str(p.get("id")), f"plan {f} is no file in {plans_root}"))
    return out


def resolve_areas(store, given):
    """The area ids given, each a row of the areas table, or a TodoError naming the
    unknown ones."""
    known = _ids(store.areas)
    unknown = [a for a in given if a not in known]
    if unknown:
        raise TodoError(f"area(s) {unknown}: no such area (known: {', '.join(known) or 'none'}; "
                        "`todo area-add` adds one)")
    if len(set(given)) != len(given):
        raise TodoError(f"area(s) {given}: an area is named once")
    return list(given)


def project(store, pid):
    """The project row `pid`, or a TodoError: an id the projects table does not hold."""
    for p in store.projects:
        if isinstance(p, dict) and p.get("id") == pid:
            return p
    known = _ids(store.projects)
    raise TodoError(f"{pid}: no such project (known: {', '.join(known) or 'none'}; `todo projects` lists them)")


def next_project_id(store):
    rx = project_id_re()
    ns = [int(m.group(1)) for m in (rx.match(str(i)) for i in _ids(store.projects)) if m]
    return f"{VOCAB.project_prefix}-{max(ns, default=0) + 1}"


def findings(store, ws, plans_root):
    """What check's records gate says of the tables: problems, then references."""
    return problems(store.records) + (references(store.projects, ws, plans_root) or [])


def refuse_problems(store, ws, plans_root, before):
    """Before a write saves: a TodoError naming each finding of the tables that the
    write made (not in `before`, the findings it started from), so a write never
    leaves one check would fail, and a row gone bad elsewhere blocks no other write."""
    new = [f for f in findings(store, ws, plans_root) if f not in before]
    if new:
        raise TodoError("refused, nothing written: " + "; ".join(f"{w}: {why}" for w, why in new))
