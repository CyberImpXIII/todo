"""The todo CLI: the only way into a store. `todo --help` lists the commands;
README.md documents each one, and tests/test_docs.py holds the two equal."""
import argparse
import contextlib
import difflib
import json
import os
import sys
from pathlib import Path

from . import approval, checks, deps, importer, plans
from . import blockers as rootlib
from . import decisions as decide
from . import detect, repostatus
from .blockers import BRIEF_NEEDS, BRIEF_REFUSES_WITHOUT, is_split, size_refusal
from . import steps as stepping
from . import syncplans
from . import tags as tagging
from .render import field_value, render_history, render_item, render_store, history_order
from .store import (EXIT_NO_STORE, HISTORY_RENDER_FILE, STORE_FILE, NoStore, Store, TodoError, Workspace, add_days, commit_subject, head_commit,
                    file_report_bullet, id_number, never_scanned, new_item, scan_root, scan_stores, store_dir_for, today,
                    write_atomic)
from .vocab import VOCAB

HAND_EDIT_DIFF_MAX = 4000
# The import's first week of rendered == store runs as a counted warning (PLAN §8, decision 2).
IMPORT_GRACE_DAYS = 7
TITLE_WIDTH = 100


# -- shared plumbing ---------------------------------------------------------

def open_store(args):
    return Store(store_dir_for(Path.cwd(), args.C)).load()


def workspace(args, store):
    return Workspace(store, scan_root(store.dir, args.root))


def read_workspace(args):
    """The workspace a read by id or tag answers from (show, get, find, refs,
    brief, tree ID, history ID). They name their record, so they need no store of
    their own: with no -C and no todo.json found from the cwd (the git repo
    holding it, or a folder above), the stores scanned from the cwd answer --
    `--root` or TODO_ROOT, else the cwd itself when it is in no git repo (the
    workspace root), else as scan_root says. -C naming a folder with no store
    stays an error: an explicit store is never swapped for another."""
    d = store_dir_for(Path.cwd(), args.C)
    if args.C or Store(d).exists():
        store = Store(d).load()
        return workspace(args, store)
    root = scan_root(d, args.root)
    ws = Workspace(None, root)
    if not ws.stores:
        raise NoStore(f"no {STORE_FILE} in {d}, and none under {root} (todo repos lists the stores a scan finds; "
                        "-C DIR, --root DIR or TODO_ROOT points elsewhere)")
    return ws


def require_history(store):
    if store.history is None:
        raise TodoError(f"{store.history_path} is missing: restore it (git checkout -- {store.history_path.name}); "
                        "history is append-only and is never recreated empty")


def require_clean(store):
    """A mutation re-renders TODO.md, so it refuses to overwrite a hand edit; and it
    writes both files, so it refuses to recreate a missing history empty."""
    require_history(store)
    state = checks.render_state(store)
    if state == "hand-edited":
        raise TodoError(f"{store.render_path} was edited by hand. Recover it first: `todo import TODO.md` takes "
                        "new bullets in as items; `todo render --force` keeps the diff in todo.json and rewrites it.")
    if state == "hand-written" and (store.items or store.closed or store.render_path.read_text().strip()):
        raise TodoError(f"{store.render_path} is hand-written: `todo import TODO.md` turns it into items first.")


def write_render(store):
    write_atomic(store.render_path, render_store(store), readonly=True)


def commit(store):
    store.save()
    write_render(store)


def validate(item, where="store", require_waits=True, require_decision=False):
    """Refuse an item `check` would fail: declared vocabulary, required fields.
    `require_waits` False lets a waiting-jacob item written before waits_on existed
    be changed in other fields without naming one (check lists it); a new item, a
    status change or a waits_on change always needs it. `require_decision`: a
    decision must carry decisions.requires (a new one, or one whose kind or decision
    fields change); an older one is listed by check instead."""
    for f in checks.SINGLE_LINE:
        if isinstance(item.get(f), str) and "\n" in item[f]:
            raise TodoError(f"{f} must be one line")
    t = item.get("title")
    if not t or not t.strip() or "**" in t:
        raise TodoError("title must be one non-empty line without **")
    if item.get("evidence") and any(ln.startswith("· ") for ln in item["evidence"].split("\n")):
        raise TodoError("an evidence line may not start with '· ' (the render's field mark)")
    if item["kind"] not in VOCAB.kinds:
        raise TodoError(f"kind {item['kind']!r}: one of {', '.join(VOCAB.kinds)}")
    if item["status"] not in VOCAB.statuses:
        raise TodoError(f"status {item['status']!r}: one of {', '.join(VOCAB.statuses)}")
    if item.get("work") is not None and item["work"] not in VOCAB.works:
        raise TodoError(f"work {item['work']!r}: one of {', '.join(VOCAB.works)}")
    if item.get("size") is not None and item["size"] not in VOCAB.sizes:
        raise TodoError(f"size {item['size']!r}: one of {', '.join(VOCAB.sizes)}")
    missing = [f for f in VOCAB.required(item) if item.get(f) in (None, "", [])]
    if missing:
        flags = ", ".join("--" + f.replace("_", "-") for f in missing)
        raise TodoError(f"a {item['kind']} that is {item['status']} needs {flags}")
    why = checks.waits_on_problem(item, require_waits) or checks.research_problem(item.get("research"))
    if why:
        raise TodoError(why)
    bad = decide.field_problems(item) + detect.field_problems(item)
    if bad:
        raise TodoError("; ".join(bad))
    lacking = decide.missing(item) if require_decision and decide.is_decision(item) else []
    if require_decision and decide.is_decision(item) and item["status"] not in (decide.D["status"], VOCAB.closed):
        raise TodoError(f"a {item['kind']} is {decide.D['status']} until Jacob answers it: "
                        f"--status {decide.D['status']} (todo approve, todo done --as, todo answer close it)")
    if lacking:
        raise TodoError(f"a {item['kind']} needs {', '.join('--' + f.replace('_', '-') for f in lacking)} "
                        "(PLAN-todo-tool.md §10.3: what it hinges on, the plan section, the recommended answer)")


def resolve_pointer(ws, args, pointer):
    """Refuse a decision pointer the plans CLI cannot read: the table's FILE §n is
    what a Decisions table is checked by too, and one that resolves nowhere asks Jacob about nothing."""
    cli_path, why = plans.resolve_cli(args.plans_cli)
    if why:
        raise TodoError(f"--pointer {pointer}: cannot be read ({why})")
    state, value = plans.show(cli_path, plans_dir(args, ws), decide.pointer_ref(pointer))
    if state != plans.OK:
        raise TodoError(f"--pointer {pointer}: {value}")


def decision_args(args, item):
    """The decision fields given as flags, normalised: {field: value} ('' clears)."""
    out = {}
    if args.pointer is not None:
        out["pointer"] = decide.normal_pointer(args.pointer) if args.pointer.strip() else ""
        if out["pointer"] is None:
            raise TodoError(f"--pointer {args.pointer!r}: FILE §n, e.g. 'PLAN-x.md §3'")
    for f in ("hinges_on", "recommend"):
        if getattr(args, f) is not None:
            out[f] = getattr(args, f).strip()
    if args.option is not None:
        try:
            out["options"] = [decide.parse_option(o) for o in args.option if o.strip()]
        except ValueError as e:
            raise TodoError(str(e))
    return out


def work_dir(ws, store, item):
    """The folder of the repo an item's work lives in: this store's own when the
    item names its repo, else the scanned store's that does. None when no scanned
    store has that repo (or none is named): the checkpoint is then unknown, never
    guessed from another repo."""
    repo = item.get("repo")
    if not repo:
        return None
    if repo == store.repo:
        return store.dir
    other = ws.by_repo(repo)
    return other.dir if other else None


def resolve_parent(ws, parent):
    if parent and ws.find(parent)[0] is None:
        raise TodoError(f"parent {parent} resolves in no scanned store or history (todo repos lists them)")


def resolve_blockers(ws, item_id, blockers):
    """Refuse a blocked_by list `check` would fail: an id that resolves in no scanned
    store or history, or one that leads back to the item (a cycle; itself included).
    Returns the list without repeats, in the order given, or None for an empty one."""
    if not blockers:
        return None
    out = list(dict.fromkeys(blockers))
    for b in out:
        if ws.find(b)[0] is None:
            raise TodoError(f"blocked_by {b} resolves in no scanned store or history (todo repos lists them)")
    path = deps.cycle(ws, item_id, out)
    if path:
        raise TodoError(f"blocked_by would make a cycle: {' -> '.join(path)}")
    return out


def resolve_tags(ws, given):
    """Refuse a tag `check` would fail: one outside the vocabulary, one derived from
    a field (repo:, kind:, status:, todo.work:), or a ref:todo:<id> that resolves in
    no scanned store or history. A ref: to another service is kept unchecked (no
    registry answers for it yet). Returns the tags without repeats, or None."""
    if not given:
        return None
    out = list(dict.fromkeys(given))
    for t in out:
        why = tagging.problem(t, stored=True)
        if why:
            raise TodoError(f"tag {why}")
        target = tagging.ref_target(t)
        if target is not None and ws.find(target)[0] is None:
            raise TodoError(f"tag {t}: {target} resolves in no scanned store or history")
    return out


def plans_dir(args, ws):
    """Where a plan:PLAN-x.md tag's file lives: --plans-dir, else the scan root."""
    return Path(args.plans_dir) if args.plans_dir else ws.root


def pin_plans(ws, item, args):
    """The item's plan sections as they read today, one pin per plan:FILE§n tag
    (README "Plan pins"). Refused when the item has no such tag, or when a section
    cannot be read: a pin records a section as it is, never a guess."""
    sections = [r for r in plans.refs(item) if plans.split(r)[1] is not None]
    if not sections:
        raise TodoError(f"--pin-plan: the item has no {plans.namespace()}:PLAN-<name>.md§<n> tag "
                        "(a pin is of a section; --tags sets one)")
    cli_path, why = plans.resolve_cli(args.plans_cli)
    if why:
        raise TodoError(f"--pin-plan: {why}")
    out = []
    for ref in sections:
        state, value = plans.show(cli_path, plans_dir(args, ws), ref)
        if state != plans.OK:
            raise TodoError(f"--pin-plan {ref}: {value}")
        out.append({"plan": ref, "digest": value, "date": today()})
    return out


class Unchecked(TodoError):
    """Not this service's to judge (an id of another service, a prefix no scanned
    store holds): exit 3, never a pass and never a failure."""


def known_repo(ws, repo):
    """Refuse a --repo filter no scanned store knows, so a misspelt repo is an error,
    never "0 items" (exit 0). Known: each readable store's own repo, and every repo an
    open or closed item names. With a store unreadable, an unknown repo is Unchecked
    (exit 3): that store may hold it. One reader for every --repo filter."""
    if not repo:
        return
    known = {s.repo for s in ws.stores if s.data}
    for s in ws.stores:
        known.update(it.get("repo") for it in s.items)
        known.update(it.get("repo") for it in s.closed)
    known.discard(None)
    if repo in known:
        return
    names = ", ".join(sorted(known)) or "none"
    if ws.errors:
        raise Unchecked(f"--repo {repo!r}: no readable store knows it, and {len(ws.errors)} store(s) could not be "
                        f"read (known: {names})")
    raise TodoError(f"--repo {repo!r}: no scanned store or item names that repo (known: {names})")


def resolve_record(ws, text):
    """(item, where, store) for an id, `todo:td-3` or `td-3`. Unchecked for an id
    this scan cannot judge; TodoError for a malformed id or a dangling one."""
    local = tagging.local_id(text)
    if local == text and tagging.GLOBAL_RE.match(text) and not tagging.well_formed_local(text):
        raise Unchecked(f"{text} belongs to service {text.split(':', 1)[0]}, not {VOCAB.service}: ask that service")
    if not tagging.well_formed_local(local):
        raise TodoError(f"{text} is not an id (todo:<prefix>-<n>)")
    found = ws.find(local)
    if found[0] is None:
        if checks.outside_scan(ws, local):
            raise Unchecked(f"{text}: no scanned store has prefix {local.split('-')[0]} (the scan root is {ws.root})")
        raise TodoError(f"{text} is in no scanned store or history: a dangling id")
    return found


def record_json(it, where, s):
    return {"id": tagging.global_id(it["id"]), "closed": where == "history",
            "tags": tagging.all_tags(it, s.repo), "record": it}


def cmd_get(args):
    it, where, s = resolve_record(read_workspace(args), args.id)
    print(json.dumps(record_json(it, where, s), indent=1, ensure_ascii=False))


def print_records(found, as_json, empty):
    if as_json:
        print(json.dumps({"records": [{"id": tagging.global_id(it["id"]), "title": it.get("title"),
                                       "closed": where == "history", "tags": tagging.all_tags(it, s.repo)}
                                      for it, where, s in found]}, indent=1, ensure_ascii=False))
        return
    for it, where, s in found:
        print(f"{tagging.global_id(it['id'])}  {it.get('title')}" + ("  (closed)" if where == "history" else ""))
    if not found:
        print(empty)


def matching(ws, wanted, open_only=False):
    out = []
    for it, where, s in ws.everything():
        if open_only and where == "history":
            continue
        if set(wanted) <= set(tagging.all_tags(it, s.repo)):
            out.append((it, where, s))
    return out


def cmd_find(args):
    for t in args.tags:
        why = tagging.problem(t)
        if why:
            raise TodoError(f"tag {why}")
    print_records(matching(read_workspace(args), args.tags, args.open), args.json,
                  "(no record holds every tag named)")


def cmd_refs(args):
    ws = read_workspace(args)
    local = tagging.local_id(args.id)
    if tagging.well_formed_local(local):
        resolve_record(ws, args.id)  # a dangling todo id is a failure, an unscanned prefix unchecked
        target = tagging.global_id(local)
    elif tagging.GLOBAL_RE.match(args.id):
        target = args.id  # another service's id: the records here that point at it
    else:
        raise TodoError(f"{args.id} is not an id (<service>:<id>)")
    print_records(matching(ws, [f"ref:{target}"], args.open), args.json, f"(no record here refers to {target})")


def cmd_reseal(args):
    """Accept a store file changed around the CLI, after reading its diff: the one
    way to write over a broken seal, and recorded, so it is never silent."""
    if not args.reason.strip():
        raise TodoError("--reason: say what changed and why it is accepted")
    store = open_store(args)
    with store.lock():
        store.load()
        require_clean(store)
        broken = store.unsealed()
        if not broken:
            raise TodoError("nothing to reseal: every store file's seal matches its content")
        store.data.setdefault("hand_edits", []).append({"date": today(), "via": "reseal", "files": broken,
                                                        "reason": args.reason})
        store.save(reseal=True)
        write_render(store)
    print(f"resealed {', '.join(broken)}; recorded in todo.json hand_edits. `todo check` judges the content.")


def cmd_help(args):
    """The command list, one per line at one indent: what tools/checks reads to
    hold cli.json's verbs to what this CLI offers."""
    print("todo <command>   structured TODO items per repo; `todo <command> -h` for its flags\n")
    width = max(map(len, COMMANDS))
    for name, (_, text) in COMMANDS.items():
        print(f"  {name:<{width}} {text}")


def one_line(it):
    title = it.get("title") or ""
    if len(title) > TITLE_WIDTH:
        title = title[:TITLE_WIDTH - 1] + "…"
    return f"{it.get('id'):<8} {str(it.get('kind')):<9} {str(it.get('status')):<13} {title}"


def print_item(it, where, store, ws):
    print(f"{it['id']}  ({store.repo}, {'open, in todo.json' if where == 'store' else 'closed, in todo-history.json'})")
    for name in VOCAB.field_names():
        v = it.get(name)
        if v in (None, "", []):
            continue
        if name == "evidence":
            print("evidence:")
            for ln in v.split("\n"):
                print("  " + ln)
            continue
        if name in ("handoff", "approved", "dispatched", "plan_pins", "options", "jacob_words"):
            v = field_value(name, v)
        elif isinstance(v, dict):
            v = ", ".join(f"{k}={v[k]}" for k in v)
        elif isinstance(v, list):
            v = ", ".join(v)
        print(f"{name}: {v}")
    kids = [c["id"] for c, _, _ in ws.everything() if c.get("parent") == it["id"]]
    if kids:
        print(f"children: {', '.join(kids)}")


# -- commands ----------------------------------------------------------------

def cmd_init(args):
    d = store_dir_for(Path.cwd(), args.C)
    store = Store(d)
    store.init(args.prefix, args.repo or d.name)
    msg = f"initialised {store.path} (repo {store.repo}, ids {store.prefix}-N) and {store.history_path.name}"
    if store.render_path.exists():
        print(msg + f"; {store.render_path.name} exists: next, `todo import TODO.md`")
    else:
        write_render(store)
        print(msg + f"; rendered {store.render_path.name}")


def cmd_add(args):
    store = open_store(args)
    with store.lock():
        store.load()
        require_clean(store)
        ws = workspace(args, store)
        resolve_parent(ws, args.parent)
        if VOCAB.made_by.get(args.kind):
            raise TodoError(f"a {args.kind} item is made by {VOCAB.made_by[args.kind]}, never by hand")
        decision = args.kind == VOCAB.role("decision_kind")
        status = args.status or (decide.D["status"] if decision else VOCAB.role("default_status"))
        if decision and status != decide.D["status"]:
            raise TodoError(f"a {args.kind} is added {decide.D['status']}: it waits on Jacob's answer "
                            "(todo approve, todo done --as, todo answer close it)")
        waits_on = args.waits_on
        if decision and waits_on is None:
            waits_on = decide.D["waits_on"]
        item = new_item(title=args.title, kind=args.kind, status=status,
                        evidence=args.evidence, probe=args.probe, parent=args.parent,
                        repo=args.repo or store.repo, work=args.work, size=args.size, files=args.files,
                        research=args.research or None, done_when=args.done_when, done_check=args.done_check,
                        retire=args.retire, waits_on=waits_on, added=today())
        item.update({f: v or None for f, v in decision_args(args, item).items()})
        if item["status"] == VOCAB.closed:
            raise TodoError("add makes open items; close one with todo done")
        if args.reported_to:
            item["reported_to"] = reported_to_value(ws, store, item, args.reported_to)
        check_reported_kind(item)
        validate(item, require_decision=True)
        if item.get("pointer"):
            resolve_pointer(ws, args, item["pointer"])
        item["id"] = store.allocate()
        item["blocked_by"] = resolve_blockers(ws, item["id"], args.blocked_by)
        item["tags"] = resolve_tags(ws, args.tags)
        if args.pin_plan:
            item["plan_pins"] = pin_plans(ws, item, args)
        store.items.append(item)
        commit(store)
    print(f"added {item['id']}: {item['title']}")


EDITABLE = ["title", "kind", "status", "evidence", "probe", "parent", "blocked_by", "waits_on", "repo", "work", "size",
            "files", "research", "done_when", "done_check", "retire", "tags"]


def cmd_edit(args):
    store = open_store(args)
    with store.lock():
        store.load()
        require_clean(store)
        item, where = store.find(args.id)
        if where == "history":
            raise TodoError(f"{args.id} is closed; history entries are never edited (add a new item with --parent {args.id})")
        if item is None:
            raise TodoError(f"{args.id} is not in {store.path}")
        changes = {f: getattr(args, f) for f in EDITABLE if getattr(args, f) is not None}
        by = VOCAB.made_by.get(changes.get("kind")) or VOCAB.made_by.get(item["kind"])
        if "kind" in changes and changes["kind"] != item["kind"] and by:
            raise TodoError(f"--kind: a {changes['kind'] if VOCAB.made_by.get(changes['kind']) else item['kind']} "
                            f"item is made and kept by {by}; "
                            "no other kind becomes one or is made from one")
        if args.append_evidence is not None:
            # Appended here, under the store's lock, so a caller never reads,
            # changes and rewrites the evidence itself and drops an edit made
            # in between (td-19).
            if args.evidence is not None:
                raise TodoError("--evidence replaces the evidence and --append-evidence adds to it: give one")
            if not args.append_evidence.strip():
                raise TodoError("--append-evidence: nothing to add")
            old = item.get("evidence")
            changes["evidence"] = f"{old}\n{args.append_evidence}" if old else args.append_evidence
        if args.handoff is not None:
            if "\n" in args.handoff:
                raise TodoError("--handoff must be one line: done; next; how to verify")
            changes["handoff"] = ({"date": today(), "text": args.handoff.strip(),
                                   "commit": head_commit(work_dir(workspace(args, store), store, item))}
                                  if args.handoff.strip() else "")
        if args.reported_to is not None:
            changes["reported_to"] = reported_to_value(workspace(args, store), store, item, args.reported_to)
        changes.update(decision_args(args, item))
        if not changes and not args.pin_plan:
            raise TodoError("nothing to change: name at least one field")
        if changes.get("status") == VOCAB.closed:
            raise TodoError("close an item with `todo done ID --resolution ...`")
        updated = dict(item)
        for f, v in changes.items():
            updated[f] = None if v in ("", []) else v
        cleared = None
        if ("status" in changes and "waits_on" not in changes and updated.get("waits_on") is not None
                and updated.get("status") != VOCAB.jacob_status):
            # waits_on names what clears a waiting-jacob item; leaving that status
            # ends the wait, so the field goes with it, said aloud below.
            cleared, updated["waits_on"], changes["waits_on"] = updated["waits_on"], None, ""
        validate(updated, require_waits=bool({"status", "waits_on"} & set(changes)),
                 require_decision=bool({"kind", *decide.FIELDS} & set(changes)))
        if changes.get("pointer"):
            resolve_pointer(workspace(args, store), args, updated["pointer"])
        check_reported_kind(updated)
        if "parent" in changes:
            resolve_parent(workspace(args, store), updated["parent"])
        if "blocked_by" in changes:
            updated["blocked_by"] = resolve_blockers(workspace(args, store), args.id, updated["blocked_by"])
        if "tags" in changes:
            updated["tags"] = resolve_tags(workspace(args, store), updated["tags"])
        if args.pin_plan:
            updated["plan_pins"] = pin_plans(workspace(args, store), updated, args)
            changes["plan_pins"] = updated["plan_pins"]
        elif "tags" in changes and updated.get("plan_pins"):
            # A tag taken off takes its pin with it: stale-plans checks only the sections the item claims.
            kept = [p for p in updated["plan_pins"] if p.get("plan") in plans.refs(updated)]
            updated["plan_pins"] = kept or None
            changes["plan_pins"] = kept
        item.update(updated)
        commit(store)
    print(f"edited {args.id}: {', '.join(changes)}"
          + (f" (waits_on {cleared} cleared: it left {VOCAB.jacob_status})" if cleared else ""))


def check_reported_kind(item):
    """reported_to belongs to a report alone; add and edit both refuse it elsewhere."""
    if item.get("reported_to") is not None and item["kind"] != VOCAB.role("report_kind"):
        raise TodoError(f"reported_to is a {VOCAB.role('report_kind')}'s field and this item is a "
                        f"{item['kind']}: add --kind {VOCAB.role('report_kind')}, or clear it with --reported-to ''")


def reported_to_value(ws, store, item, value):
    """`edit --reported-to REPO[:THEIR_ID]`: the reported_to it sets, writing no other
    store (`todo report` writes the counterpart; this records one that exists, or an
    owner whose store does not). THEIR_ID is taken only when REPO's scanned store holds
    it with parent ID; with none given, a counterpart REPO already holds pairs (its
    parent says so). The date is kept while the repo is unchanged. "" clears it."""
    if not value.strip():
        return ""
    repo, _, their = value.strip().partition(":")
    if not repo or repo == store.repo:
        raise TodoError(f"--reported-to {value!r}: name another repo (REPO or REPO:THEIR_ID)")
    if item.get("id") is None:
        # todo add: no counterpart can name an id not made yet, and a lookup by a
        # null parent would pair any parentless item.
        if their:
            raise TodoError(f"--reported-to {value!r}: add takes REPO alone; pair a counterpart afterwards "
                            "with todo edit ID --reported-to REPO:THEIR_ID")
        return {"repo": repo, "date": today(), "their_id": None}
    hidden = never_scanned(repo)
    owner = None if hidden else ws.by_repo(repo)
    if their:
        if owner is None:
            raise TodoError(f"--reported-to {value!r}: {repo} has no scanned store"
                            + (" (a hidden folder, never scanned)" if hidden else "")
                            + f", so {their} cannot be confirmed: give {repo} alone")
        c, _ = owner.find(their)
        if c is None:
            raise TodoError(f"--reported-to {value!r}: {their} is in neither {repo}'s store nor its history")
        if c.get("parent") != item["id"]:
            raise TodoError(f"--reported-to {value!r}: {their}'s parent is {c.get('parent')}, not {item['id']}")
    elif owner is not None:
        prior = [c["id"] for c in owner.items + owner.closed if c.get("parent") == item["id"]]
        if len(prior) == 1:
            their = prior[0]
            print(f"{repo} holds {their} with parent {item['id']}: paired with it")
    old = item.get("reported_to") or {}
    date = old.get("date") if old.get("repo") == repo and old.get("date") else today()
    return {"repo": repo, "date": date, "their_id": their or None}


DECISION_RESOLUTION_ROLES = ("decision_accepted_resolution", "decision_option_resolution", "decision_rejected_resolution")


@contextlib.contextmanager
def locked_workspace(args, store):
    """Every scanned store locked (in path order, as todo report does) and reloaded:
    a command that may write items in several stores (a rejection, an answer) reads
    and writes them all under one hold. Yields the workspace."""
    ws = workspace(args, store)
    with contextlib.ExitStack() as stack:
        for s in sorted(ws.stores, key=lambda s: str(s.dir)):
            stack.enter_context(s.lock())
        for s in ws.stores:
            s.load()
        yield ws


def reject(ws, item, store, reason, date):
    """Close a decision as rejected; put every open item blocked by it, in any
    scanned store, back to waiting on that decision. Returns (closed item, [(dependent
    id, store)]); writes nothing (the caller commits every store touched)."""
    closed = decide.rejected(item, date)
    validate(closed, "history")
    moved = []
    for dep, s in decide.dependents(ws, item["id"]):
        changed = dict(dep, **decide.requeued(dep, item, reason, date))
        validate(changed)
        dep.update(changed)
        moved.append((dep["id"], s))
    store.history["items"].append(closed)
    store.items.remove(item)
    return closed, moved


def commit_all(stores):
    for s in sorted({s.dir: s for s in stores}.values(), key=lambda s: str(s.dir)):
        commit(s)


def cmd_reject(args):
    """`todo done ID --as rejected --reason R` (PLAN-todo-tool.md §10.3)."""
    reason = (args.reason or "").strip()
    if not reason or "\n" in reason:
        raise TodoError("--reason: one line saying why it was rejected (his words, or a pointer to them)")
    store = open_store(args)
    with locked_workspace(args, store) as ws:
        item = open_item(store, args.id)
        if not decide.is_decision(item):
            raise TodoError(f"{args.id} is a {item['kind']}: --as {args.as_} closes a {VOCAB.role('decision_kind')}; "
                            "say how it closed with --resolution")
        touched = {store.dir: store} | {s.dir: s for _, s in decide.dependents(ws, item["id"])}
        for s in touched.values():
            require_clean(s)
        _, moved = reject(ws, item, store, reason, today())
        commit_all(touched.values())
    print(f"closed {args.id} as {args.as_}, moved to {store.history_path.name}")
    for dep_id, s in moved:
        print(f"  {dep_id} ({s.repo}) waits on Jacob again: {s.find(dep_id)[0]['waits_on']}")


def cmd_done(args):
    if args.as_ is not None:
        return cmd_reject(args)
    if args.reason is not None:
        raise TodoError("--reason goes with --as; --resolution says how it closed")
    store = open_store(args)
    if args.resolution.strip() == VOCAB.role("detector_resolution"):
        raise TodoError(f"resolution {args.resolution!r} is set by todo detect only, when the detector no longer "
                        "reports the finding: say how this one closed")
    peek, _ = store.find(args.id)
    if peek is not None and detect.is_detector_item(peek) and peek.get("detector") is not None:
        # Its detector runs first, outside the lock (its command may itself call todo):
        # a stall closes by hand only once the cause is gone (PLAN-todo-tool.md §10.5).
        detectors, _ = detect.registered()
        held, why = detect.still_reported(peek, store.dir, scan_root(store.dir, args.root), detectors)
        if held:
            raise TodoError(f"{args.id} stays open: {why}")
    with store.lock():
        store.load()
        require_clean(store)
        item, where = store.find(args.id)
        in_store = [it for it in store.items if it["id"] == args.id]
        if where == "store" and any(h["id"] == args.id for h in store.closed):
            store.items.remove(in_store[0])  # an interrupted close: history has it already
            commit(store)
            print(f"finished an interrupted close of {args.id}")
            return
        if where == "history":
            raise TodoError(f"{args.id} is already closed ({item.get('done')}); ids are never reused")
        if item is None:
            raise TodoError(f"{args.id} is not in {store.path}" + ("" if store.owns(args.id) else
                            f" (its prefix is not {store.prefix}: close it in its own repo)"))
        if args.resolution.strip() == VOCAB.role("import_resolution"):
            raise TodoError(f"resolution {args.resolution!r} is set by todo import only, for a closed bullet "
                            "that carried none: say how this one closed")
        if args.resolution.strip() == VOCAB.role("step_resolution"):
            raise TodoError(f"resolution {args.resolution!r} is set by todo steps --run only, when the step's "
                            "done_check exits 0: run that, or say how this one closed")
        if args.resolution.strip() in [VOCAB.role(r) for r in DECISION_RESOLUTION_ROLES]:
            raise TodoError(f"resolution {args.resolution!r} closes a decision on Jacob's answer: todo approve ID "
                            f"[--option NAME], todo done ID --as {VOCAB.role('decision_rejected_resolution')} "
                            "--reason R, or todo answer")
        closed = dict(item, status=VOCAB.closed, done=today(), resolution=args.resolution)
        validate(closed, "history")
        store.history["items"].append(closed)
        store.items.remove(item)
        parent_note = close_finished_parent(args, store, item)
        commit(store)
    print(f"closed {args.id}, moved to {store.history_path.name}")
    if parent_note:
        print(parent_note)


def close_finished_parent(args, store, child):
    """A split item (size `ready: false`) closes when its last child does
    (PLAN-small-tasks.md §2.1): called with the child already moved to history,
    before the write. Children anywhere in the scan count; the parent must be in
    this store. Returns a line to print, or None."""
    pid = child.get("parent")
    parent = next((it for it in store.items if it["id"] == pid), None)
    if parent is None or parent.get("size") != VOCAB.split_size:
        return None
    ws = workspace(args, store)
    kids = checks.children_of(ws, pid)
    still_open = [k for s in ws.stores for it in s.items if (k := it["id"]) in kids and k != child["id"]]
    if still_open:
        return None
    done = dict(parent, status=VOCAB.closed, done=today(),
                resolution=f"closed with its last child, {child['id']}: every child of this split item is closed ({', '.join(kids)})")
    try:
        validate(done, "history")
    except TodoError as e:
        return f"{pid} has no open child left but stays open: {e}; close it with todo done {pid}"
    store.history["items"].append(done)
    store.items.remove(parent)
    return f"closed {pid} too: it was split, and {child['id']} was its last open child"


def cmd_split(args):
    """Break an item into children under `parent` (PLAN-small-tasks.md §2.1), each
    small enough for one checkpoint. A child copies the parent's kind, repo, work,
    files, blocked_by and tags, and any field its kind requires; its done_when is
    its own, set with todo edit. The parent becomes the split size, so `ready`
    never lists it, and it closes when its last child does."""
    store = open_store(args)
    with store.lock():
        store.load()
        require_clean(store)
        parent, where = store.find(args.id)
        if where == "history":
            raise TodoError(f"cannot split {args.id}: it is closed")
        if parent is None:
            raise TodoError(f"{args.id} is not in {store.path} (split an item in its own repo)")
        if parent.get("kind") == VOCAB.role("report_kind"):
            raise TodoError(f"{args.id} is a {parent['kind']}: its work lives in the owner's store; split it there")
        # A child is a piece of the approved whole, so it carries the approval; never
        # the dispatched mark, since each piece is handed out on its own. It carries the
        # plan pins with the plan tags: a piece of the whole was made from the same section.
        copied = ("kind", "repo", "work", "files", "blocked_by", "tags", "plan_pins", "approved", *VOCAB.required(parent))
        if VOCAB.made_by.get(parent.get("kind")):
            # a plan step or a stall stays one item, its command's own; its pieces are plain items under it
            copied = ("repo", "work", "files", "blocked_by", "tags", "plan_pins", "approved")
        made = []
        for title in args.titles:
            child = new_item(**{f: parent.get(f) for f in copied}, title=title, status=VOCAB.role("default_status"),
                             parent=args.id, size=args.size, added=today(),
                             evidence=f"split from {args.id}: {parent['title']}")
            child["kind"] = child["kind"] or VOCAB.role("default_kind")
            validate(child)
            child["id"] = store.allocate()
            store.items.append(child)
            made.append(child["id"])
        resized = parent.get("size") != VOCAB.split_size
        parent["size"] = VOCAB.split_size
        commit(store)
    print(f"split {args.id} into {', '.join(made)} (size {args.size})"
          + (f"; {args.id} is now size {VOCAB.split_size}" if resized else "")
          + ". Give each child its own done_when: todo edit ID --done-when ...")


def cmd_report(args):
    store = open_store(args)
    ws = workspace(args, store)
    if args.to == store.repo:
        raise TodoError("an item is reported to another repo, not to its own")
    hidden = never_scanned(args.to)
    owner = None if hidden else ws.by_repo(args.to)
    stores = sorted([s for s in (store, owner) if s], key=lambda s: str(s.dir))
    locks = [s.lock() for s in stores]
    for lk in locks:
        lk.__enter__()
    try:
        for s in stores:
            s.load()
            require_clean(s)
        item, where = store.find(args.id)
        if where != "store":
            raise TodoError(f"{args.id} is not an open item in {store.path}")
        by = VOCAB.made_by.get(item["kind"]) or VOCAB.made_by.get(args.kind)
        if by:
            raise TodoError(f"a {item['kind'] if VOCAB.made_by.get(item['kind']) else args.kind} item stays one ({by} keeps it) and none is made by "
                            f"hand: report a new item with --parent {args.id} instead")
        rt = item.get("reported_to")
        if rt and (rt.get("repo") != args.to or rt.get("their_id")):
            raise TodoError(f"{args.id} is already reported to {rt['repo']}" + (f" as {rt['their_id']}" if rt.get("their_id") else ""))
        their = None
        if owner:
            prior = [c for c in owner.items + owner.closed if c.get("parent") == args.id]
            if prior:
                their = prior[0]["id"]
                print(f"{args.to} already holds {their} for {args.id}; pairing with it, not reporting again")
            else:
                ckind = args.kind or (item["kind"] if item["kind"] != VOCAB.role("report_kind") else VOCAB.role("default_kind"))
                counterpart = new_item(title=item["title"], kind=ckind, status=VOCAB.role("default_status"),
                                       evidence=item.get("evidence"), probe=item.get("probe"), parent=args.id,
                                       repo=owner.repo, work=item.get("work"), files=item.get("files"),
                                       done_when=item.get("done_when"), retire=item.get("retire"), added=today())
                validate(counterpart)
                counterpart["id"] = owner.allocate()
                owner.items.append(counterpart)
                their = counterpart["id"]
                commit(owner)
        filed = None
        if not owner and not hidden:
            filed = file_without_store(ws, store, item, args.to)
            if filed and filed[1]:
                item["evidence"] = ((item.get("evidence") + "\n") if item.get("evidence") else "") + filed[2]
        item["kind"] = VOCAB.role("report_kind")
        item["reported_to"] = {"repo": args.to, "date": (rt or {}).get("date") or today(), "their_id": their}
        validate(item, require_waits=False)
        commit(store)
    finally:
        for lk in reversed(locks):
            lk.__exit__(None, None, None)
    if their:
        print(f"reported {args.id} to {args.to} as {their} ({owner.path}; commit it there)")
    elif hidden:
        print(f"reported {args.id} to {args.to}: a hidden folder, which the scan never enters, so this report "
              f"never pairs. Relay it to its owner by hand (your final report) and close {args.id} by its done_when.")
    elif filed:
        path, written, _ = filed
        print(f"reported {args.id} to {args.to}: it has no store, so "
              + (f"a bullet marked {tagging.global_id(args.id)} was added to {path}" if written else
                 f"{path} names {tagging.global_id(args.id)} already: nothing added")
              + f". Commit it there (it is {args.to}'s file); `todo check` lists the report as unpaired "
              f"until {args.to} has a todo.json, then re-run this to pair it.")
    else:
        print(f"reported {args.id} to {args.to}: no store for {args.to} in the scan, so no counterpart yet. "
              f"`todo check` lists it as unpaired; re-run this once {args.to} has a todo.json.")


def file_without_store(ws, store, item, repo):
    """A report to a git repo the scan finds with no store is filed in its
    hand-written TODO.md (PLAN-architecture.md §11 S4), never left only here.
    (path, written, evidence line), or None when no such repo is found, or more
    than one folder bears the name (then nothing is written: which is meant?)."""
    dirs = [d for d in scan_stores(ws.root, storeless=True) if d.name == repo and not (d / STORE_FILE).is_file()]
    if len(dirs) != 1:
        if len(dirs) > 1:
            print(f"{len(dirs)} repos are named {repo} ({', '.join(os.path.relpath(d, ws.root) for d in dirs)}): "
                  "none is written to")
        return None
    marker = tagging.global_id(item["id"])
    where = os.path.relpath(store.dir, ws.root)
    lines = [f"- {marker} from {store.repo} ({today()}): {item['title']}"]
    for label, value in (("evidence", item.get("evidence")), ("done when", item.get("done_when"))):
        for i, ln in enumerate(str(value or "").splitlines()):
            lines.append(f"  {label + ': ' if i == 0 else ''}{ln}".rstrip())
    lines.append(f"  (todo -C {where} show {item['id']}; filed here because {repo} has no todo store)")
    path, written = file_report_bullet(dirs[0], marker, lines)
    rel = os.path.relpath(path, ws.root)
    return path, written, f"filed {today()} in {rel} as a bullet marked {marker}: {repo} has no store (their_id stays null)"


def cmd_list(args):
    store = open_store(args)
    if args.status == VOCAB.closed:
        raise TodoError("closed items are in history: todo history")
    ws = workspace(args, store)
    known_repo(ws, args.repo)
    cited = None
    if args.cites is not None:
        cited = syncplans.citation(args.cites)
        if cited is None:
            raise TodoError(f"--cites {args.cites!r}: FILE §n or FILE, e.g. 'PLAN-x.md §3'")
    scope = ws.stores if (args.all or args.repo or cited) else [store]
    n = 0
    for s in scope:
        for it in s.items:
            if cited and not syncplans.cites(it, *cited):
                continue
            if args.kind and it.get("kind") != args.kind:
                continue
            if args.status and it.get("status") != args.status:
                continue
            if args.repo and it.get("repo") != args.repo:
                continue
            if args.mine and it.get("repo") != store.repo:
                continue
            if (args.ready or args.blocked) and bool(deps.open_blockers(ws, it)) != args.blocked:
                continue
            print(one_line(it))
            n += 1
    if n == 0:
        print("(no open items match)")


def cmd_show(args):
    ws = read_workspace(args)
    it, where, s = ws.find(args.id)
    if it is None:
        raise TodoError(f"{args.id} is in no scanned store or history")
    print_item(it, where, s, ws)


def cmd_render(args):
    store = open_store(args)
    ws = workspace(args, store) if args.all else None
    targets = ws.stores if args.all else [store]
    failed = 0
    for s in targets:
        try:
            with s.lock():
                s.load()
                if args.history:
                    write_atomic(s.dir / HISTORY_RENDER_FILE, render_history(s), readonly=True)
                    print(f"  rendered  {s.dir / HISTORY_RENDER_FILE}")
                    continue
                state = checks.render_state(s)
                hand = state in checks.HAND_STATES
                if hand and not args.force:
                    raise TodoError(f"{s.render_path} is {state}: `todo import TODO.md` first, or --force to keep the diff in todo.json and rewrite it")
                if hand:
                    require_history(s)
                    old = s.render_path.read_text().splitlines()
                    diff = "\n".join(difflib.unified_diff(render_store(s).splitlines(), old, "render", "TODO.md", lineterm=""))
                    s.data["hand_edits"].append({"date": today(), "via": "render --force",
                                                 "diff": diff[:HAND_EDIT_DIFF_MAX]})
                    s.save()
                write_render(s)
                print(f"  {state if state != 'clean' else 'unchanged':<10} {s.render_path}" + (" (diff kept in todo.json hand_edits)" if hand else ""))
        except TodoError as e:
            failed += 1
            print(f"  REFUSED   {e}")
    if failed:
        sys.exit(1)


def cmd_tree(args):
    if args.id:
        ws = read_workspace(args)
        store = ws.current
    else:
        store = open_store(args)
        ws = workspace(args, store)
    kids = {}
    for it, where, s in ws.everything():
        if it.get("parent"):
            kids.setdefault(it["parent"], []).append((it, where, s))

    def show(it, where, s, depth, seen):
        mark = "" if where == "store" else f" [closed {it.get('done') or ''}]".rstrip()
        print("  " * depth + one_line(it) + (f"  ({s.repo})" if s is not store else "") + mark)
        if it["id"] in seen:
            print("  " * (depth + 1) + "(loop)")
            return
        for c in sorted(kids.get(it["id"], []), key=lambda t: (t[2].repo, id_number(t[0]["id"]))):
            show(*c, depth + 1, seen | {it["id"]})

    if args.id:
        it, where, s = ws.find(args.id)
        if it is None:
            raise TodoError(f"{args.id} is in no scanned store or history")
        show(it, where, s, 0, set())
        return
    roots = [it for it in store.items if not it.get("parent") or ws.find(it["parent"])[0] is None]
    for it in roots:
        show(it, "store", store, 0, set())


def cmd_check(args):
    store = open_store(args)
    ws = workspace(args, store)
    targets = ws.stores if args.all else [store]
    code = 0
    for s in targets:
        lines, c = checks.report(s, checks.check_store(s, ws))
        print("\n".join(lines))
        code = max(code, c)
    sys.exit(code)


def cmd_import(args):
    store = open_store(args)
    src = Path(args.file)
    if not src.is_absolute() and args.C:
        src = store.dir / src  # like git -C: a relative FILE is read from the store's folder
    if not src.is_file():
        raise TodoError(f"{src} is not a file")
    with store.lock():
        store.load()
        require_history(store)
        text = src.read_text()
        ws = workspace(args, store)
        repos = {s.repo for s in ws.stores if s.data} | {d.name for d in scan_stores(ws.root, storeless=True)}
        if args.waits_on is not None:
            bad = VOCAB.waits_on_problem(args.waits_on)
            if bad:
                raise TodoError(f"--waits-on: {bad}")
        plan = importer.plan_import(text, store, today(), repos=repos, resolve_plan=plan_resolver(args, ws),
                                    waits_on=args.waits_on)
        to_store = [it for it, dest in plan.new if dest == "store"]
        to_hist = [it for it, dest in plan.new if dest == "history"]
        print(f"import {src}: {len(to_store)} new open, {len(to_hist)} new closed, {len(plan.unchanged)} unchanged, "
              f"{plan.already} imported before, {len(plan.closed_seen)} already closed"
              + (f", {len(plan.missing)} missing from the file (kept: {', '.join(plan.missing)})" if plan.missing else ""))
        if plan.changed:
            raise TodoError(f"rendered item(s) edited by hand: {', '.join(plan.changed)}. Nothing imported. "
                            "`todo render --force` keeps the diff in todo.json; then apply it with todo edit.")
        print_import_notes(plan)
        if args.dry_run:
            for it, dest in plan.new:
                print(("  history " if dest == "history" else "  store   ") + f"{it['kind']:<9} {it['status']:<13} {it['title'][:TITLE_WIDTH]}")
            print("(dry run: nothing written)")
            return
        if plan.unnamed_waits:
            raise TodoError(f"{len(plan.unnamed_waits)} {VOCAB.jacob_status} item(s) name no waits_on (listed above). "
                            f"Nothing imported. Give --waits-on ({VOCAB.waits_on_forms()}) for them, or name it in the text.")
        fresh = not store.items and not store.closed
        for it, _ in plan.new:
            it["id"] = store.allocate()
        store.items.extend(to_store)
        store.history["items"].extend(to_hist)
        if fresh and not plan.rendered:
            store.data["render_gate_from"] = add_days(today(), IMPORT_GRACE_DAYS)
        if plan.rendered and (plan.new or plan.missing):
            store.data["hand_edits"].append({"date": today(), "via": "import",
                                             "new": [it["id"] for it, _ in plan.new], "restored": plan.missing})
        commit(store)
    lacking = [it["id"] for it in to_store if any(it.get(f) in (None, "", []) for f in VOCAB.required(it))]
    print(f"wrote {len(plan.new)} item(s); rendered {store.render_path.name}. Review with todo list / todo check."
          + (f" {len(lacking)} lack a field their kind requires (todo check names them; fill with todo edit)" if lacking else ""))


def plan_resolver(args, ws):
    """For an import rule with `plan`: None when the PLAN section reads, else why not
    (the plans CLI, as --pin-plan reads it). No CLI: every such pointer is unresolved."""
    cli_path, why = plans.resolve_cli(getattr(args, "plans_cli", None))
    where = plans_dir(args, ws)

    def resolve(ref):
        if cli_path is None:
            return why
        state, value = plans.show(cli_path, where, ref)
        return None if state == plans.OK else value
    return resolve


def print_import_notes(plan):
    """What the import read as no item, and what a rule could not read: every one
    printed, so nothing is dropped unseen (vocab.json import)."""
    if plan.not_items:
        print(f"{len(plan.not_items)} block(s) not items (vocab.json import.skip):")
        for why, text in plan.not_items:
            print(f"  skipped  {why}: {text[:TITLE_WIDTH]}")
    if plan.listed:
        print(f"{len(plan.listed)} note(s) on what the text did not say:")
        for title, why in plan.listed:
            print(f"  listed   {title[:60]}: {why}")


def cmd_repos(args):
    if args.json and not args.status:
        raise TodoError("--json goes with --status")
    if args.status:
        # every git repo, with a store or not: it needs no store of its own
        d = store_dir_for(Path.cwd(), args.C)
        root = scan_root(d, args.root)
        rows = repostatus.status(root)
        if args.json:
            print(json.dumps({"root": str(root), "repos": rows}, indent=1, ensure_ascii=False))
        else:
            print(f"scan root: {root}")
            print("\n".join(repostatus.lines(rows)) or "  (no git repo found)")
        return
    store = open_store(args)
    ws = workspace(args, store)
    print(f"scan root: {ws.root}")
    for s in ws.stores:
        rel = os.path.relpath(s.dir, ws.root)
        print(f"  {s.repo:<20} {s.prefix:<6} {len(s.items):>4} open {len(s.closed):>5} closed  {rel}")
    for e in ws.errors:
        print(f"  UNREADABLE  {e}")


def not_ready_reasons(ws, it):
    """Why `todo brief` would call this open item NOT READY, or []: one list, so
    brief and dispatchable never disagree on what ready means."""
    why = []
    missing = [f for f in BRIEF_NEEDS if not it.get(f)]
    if missing:
        why.append(f"missing {', '.join(missing)}")
    if it.get("status") != VOCAB.role("default_status"):
        why.append(f"status {it.get('status')}")
    blockers = deps.open_blockers(ws, it)
    if blockers:
        why.append(f"blocked by {', '.join(blockers)}")
    if size_refusal(it):
        why.append(size_refusal(it))
    if stepping.is_step(it):
        why.append(f"a {VOCAB.role('step_kind')}: Jacob's own, closed by its done_check (todo steps --run)")
    return why


def ready_items(ws, repo=None, work=None, refused=None):
    """Dispatchable items. An item ready but for its size goes into `refused`
    (a list, when given) as (item, why), so `todo ready` names it rather than
    dropping it unseen."""
    for s in ws.stores:
        for it in s.items:
            if it.get("status") != VOCAB.role("default_status") or it.get("kind") == VOCAB.role("report_kind"):
                continue
            if stepping.is_step(it):
                continue  # Jacob's own: nobody is dispatched to it
            if not all(it.get(f) for f in BRIEF_NEEDS):
                continue
            if (repo and it["repo"] != repo) or (work and it["work"] != work):
                continue
            if deps.open_blockers(ws, it) or is_split(ws, it):
                continue  # a split item's children are listed instead
            why = size_refusal(it)
            if why:
                if refused is not None:
                    refused.append((it, why))
                continue
            yield it, s


def cmd_ready(args):
    store = open_store(args)
    n, refused = 0, []
    ws = workspace(args, store)
    known_repo(ws, args.repo)
    for it, _ in ready_items(ws, args.repo, args.work, refused):
        print(f"{it['id']:<8} {it['repo']:<20} {it['work']:<9} {it.get('size'):<2} {it['title'][:TITLE_WIDTH]}")
        n += 1
    if n == 0:
        print(f"(nothing ready: an open item needs repo, work and done_when set, size {' or '.join(VOCAB.ready_sizes)}, "
              "and every blocked_by id closed)")
    if refused:
        print(f"refused, ready but for their size ({len(refused)}):")
        for it, why in refused:
            print(f"  {it['id']:<8} {why}")


def open_item(store, item_id):
    """The open item `item_id` of this store, or a TodoError saying why not."""
    item, where = store.find(item_id)
    if where == "history":
        raise TodoError(f"{item_id} is closed ({item.get('done') or 'undated'}); history entries are never edited")
    if item is None:
        raise TodoError(f"{item_id} is not in {store.path}" + ("" if store.owns(item_id) else
                        f" (its prefix is not {store.prefix}: run this in its own repo, or -C it)"))
    return item


def cmd_approve(args):
    """Record Jacob's go-ahead on an item: who (vocab.json approval.by), the day,
    and where he gave it. Without one, `todo dispatchable` never lists the item and
    `todo dispatch` refuses it."""
    store = open_store(args)
    with store.lock():
        store.load()
        require_clean(store)
        item = open_item(store, args.id)
        if args.clear:
            if args.source is not None or args.date is not None or args.option is not None:
                raise TodoError("--clear takes no --source, --date or --option")
            if not item.get("approved"):
                raise TodoError(f"{args.id} carries no approval to clear")
            if item.get("dispatched"):
                raise TodoError(f"{args.id} was dispatched {item['dispatched'].get('date')}: "
                                f"clear that first (todo dispatch {args.id} --clear)")
            item["approved"] = None
            msg = f"cleared the approval of {args.id}"
        elif args.option is not None and not decide.is_decision(item):
            raise TodoError(f"--option chooses among a {VOCAB.role('decision_kind')}'s options, and {args.id} is a {item['kind']}")
        else:
            source = (args.source or "").strip()
            if not source or "\n" in source:
                raise TodoError("--source: one line saying where Jacob approved it (his words, or a pointer to them)")
            date = args.date or today()
            if not checks.DATE_RE.match(date) or date > today():
                raise TodoError(f"--date {date!r}: a YYYY-MM-DD no later than today ({today()})")
            item["approved"] = {"by": VOCAB.approval_by, "date": date, "source": source}
            msg = f"approved {args.id}: {field_value('approved', item['approved'])}"
            if decide.is_decision(item):
                # A decision's yes is its answer: it closes, and frees what it blocked (§10.3).
                names = decide.option_names(item)
                if args.option is not None and args.option not in names:
                    raise TodoError(f"--option {args.option!r}: {args.id}'s options are {', '.join(names) or 'none'}")
                # A plain yes to a decision recommending an option is a yes to that option.
                option = args.option or (item["recommend"] if item.get("recommend") in names else None)
                closed = decide.accepted(item, today(), item["approved"], option)
                validate(closed, "history")
                store.history["items"].append(closed)
                store.items.remove(item)
                msg += f"; closed {closed['resolution']}" + (f" ({option})" if option else "")
                freed = [d["id"] for d, _ in decide.dependents(workspace(args, store), args.id)]
                if freed:
                    msg += f"; no longer blocks {', '.join(freed)}"
        commit(store)
    print(msg)


def cmd_decisions(args):
    """The open decisions of every scanned store as a plan's Decisions table,
    numbered 1..n, the one freeing most items first (PLAN-todo-tool.md §10.3), and
    recorded in this store as a table `todo answer` reads (§10.3a, §10.3b). The
    same rows as an earlier table return that table's id; --from dt-N tables only
    the rows of dt-N still open, recording which rows each supersedes."""
    store = open_store(args)
    with store.lock():
        store.load()
        require_clean(store)
        ws = workspace(args, store)
        complete, incomplete, counts = decide.open_rows(ws)
        supersedes = []
        if args.from_:
            old = decide.find_table(store.tables, args.from_)
            if old is None:
                raise TodoError(f"--from {args.from_}: no such table in {store.records_path} "
                                f"({', '.join(t['id'] for t in store.tables) or 'none recorded'})")
            by_id = {it["id"]: (it, s) for it, s in complete}
            kept = [(r, by_id[r["item"]]) for r in old["rows"] if r["item"] in by_id]
            complete = [found for _, found in kept]
            supersedes = [{"n": n, "table": old["id"], "row": r["n"]} for n, (r, _) in enumerate(kept, 1)]
        rows = decide.record_rows(complete)
        table = next((t for t in store.tables if decide.same_rows(t["rows"], rows)), None) if rows else None
        new = table is None and bool(rows)
        if new:
            table = {"id": decide.next_table_id(store.tables), "date": today(), "rows": rows,
                     "supersedes": supersedes, "answers": []}
            store.ensure_records()["tables"].append(table)
            commit(store)
    listed = [{"id": tagging.global_id(it["id"]), "repo": s.repo, "missing": why} for it, s, why in incomplete]
    if args.json:
        out = {"table": table and table["id"], "date": table and table["date"], "new": new,
               "rows": [dict(r, id=tagging.global_id(r["item"]), frees=counts.get(r["item"], 0)) for r in rows],
               "supersedes": table["supersedes"] if table else [], "incomplete": listed,
               "unreadable": list(ws.errors)}
        print(json.dumps(out, indent=1, ensure_ascii=False))
    else:
        if table:
            for line in decide.table_lines(table):
                print(line)
            if not new:
                print(f"\n(the same rows as {table['id']} of {table['date']}: answers apply to it)")
        else:
            print("(no open decision to table" + (f" from {args.from_}: every row is closed or incomplete)" if args.from_ else
                                                  ": none is open and complete)"))
        n = decide.D["max_listed"]
        if listed:
            print(f"\n{len(listed)} open decision(s) not tabled, lacking a field: "
                  + "; ".join(f"{r['id']} ({', '.join(r['missing'])})" for r in listed[:n])
                  + (f"; +{len(listed) - n} more (--json lists them)" if len(listed) > n else "")
                  + " -- todo edit ID --pointer --hinges-on --recommend")
        for e in ws.errors:
            print(f"UNREADABLE  {e}")
    if ws.errors:
        print("todo: UNCHECKED: a store could not be read, so its decisions are missing here", file=sys.stderr)
        sys.exit(3)


def cmd_answer(args):
    """Jacob's reply to a decisions table (PLAN-todo-tool.md §10.3a): `1) yes 2) no
    3) b 4) <words>`, read against the table named (`dt-N:` leading the reply, or
    --table), else the latest. A yes approves and closes its decision, a no rejects
    it, an option's name chooses it; any other answer is kept as his words, its
    status unchanged. The reply is refused whole on a row the table does not have,
    a row named twice, or a row whose decision is already closed: nothing is applied
    in part. The answer is appended to the table's record, which never changes."""
    try:
        named, answers = decide.parse_reply(args.reply)
    except ValueError as e:
        raise TodoError(f"answer: {e}")
    if named and args.table and named != args.table:
        raise TodoError(f"answer: the reply names {named} and --table names {args.table}: give one")
    store = open_store(args)
    date = today()
    with locked_workspace(args, store) as ws:
        tid = named or args.table
        table = decide.find_table(store.tables, tid) if tid else decide.latest_table(store.tables)
        if table is None:
            raise TodoError(f"answer: {f'no table {tid}' if tid else 'no table recorded'} in {store.records_path} "
                            "(todo decisions makes one)")
        rows = {r["n"]: r for r in table["rows"]}
        plan, refused = [], []
        for n, text in answers:
            r = rows.get(n)
            if r is None:
                refused.append(f"row {n}: {table['id']} has rows 1..{len(rows)}")
                continue
            it, where, s = ws.find(r["item"])
            if it is None or where != "store":
                refused.append(f"row {n}: {r['item']} is " + ("closed already" if it else "in no scanned store"))
                continue
            plan.append((n, r, it, s, *decide.verdict(text, it), text))
        if refused:
            raise TodoError(f"answer refused, nothing applied ({table['id']}): " + "; ".join(refused))
        touched = {store.dir: store}
        for n, r, it, s, v, value, text in plan:
            touched[s.dir] = s
            if v == decide.NO:
                touched.update({d.dir: d for _, d in decide.dependents(ws, it["id"])})
        for s in touched.values():
            require_clean(s)
        done = []
        for n, r, it, s, v, value, text in plan:
            where = f"{table['id']} row {n}"
            if v in (decide.YES, decide.OPTION):
                appr = {"by": VOCAB.approval_by, "date": date, "source": f"answer {date} ({where})"}
                closed = decide.accepted(it, date, appr, value)
                validate(closed, "history")
                s.history["items"].append(closed)
                s.items.remove(it)
                line = f"{closed['resolution']}" + (f" ({value})" if value else "")
            elif v == decide.NO:
                _, moved = reject(ws, it, s, f"Jacob answered no, {where}", date)
                line = VOCAB.role("decision_rejected_resolution") + (
                    f"; waiting on Jacob again: {', '.join(d for d, _ in moved)}" if moved else "")
            else:
                words = (it.get("jacob_words") or []) + [{"date": date, "table": table["id"], "row": n, "text": text}]
                validate(dict(it, jacob_words=words))
                it["jacob_words"] = words
                line = "kept as his words; nothing applied (it stays " + it["status"] + ")"
            done.append({"n": n, "item": it["id"], "verdict": v, "option": value})
            print(f"  {n}) {tagging.global_id(it['id'])} ({s.repo}): {line}")
        table["answers"].append({"date": date, "reply": " ".join(args.reply.split()), "rows": done})
        store.ensure_records()
        commit_all(touched.values())
    print(f"answered {table['id']}: {len(done)} row(s)")


def cmd_dispatch(args):
    """Mark an approved item as handed to someone to do, so `todo dispatchable`
    leaves it out; --clear when it comes back unfinished. The note never names
    who: items name repos (README, Dispatch)."""
    store = open_store(args)
    with store.lock():
        store.load()
        require_clean(store)
        item = open_item(store, args.id)
        if args.clear:
            if args.note is not None:
                raise TodoError("--clear takes no --note")
            if not item.get("dispatched"):
                raise TodoError(f"{args.id} is not dispatched")
            item["dispatched"] = None
            msg = f"cleared the dispatch of {args.id}: todo dispatchable lists it again when it is ready"
            if approval.is_rule(item.get("approved")):
                item["approved"] = None  # judged afresh from here on (todolib/approval.py)
                msg += f"; its rule {VOCAB.approval_rule['id']} approval is judged afresh"
        else:
            if item.get("dispatched"):
                raise TodoError(f"{args.id} was dispatched {item['dispatched'].get('date')} already "
                                f"(todo dispatch {args.id} --clear when it came back unfinished)")
            if stepping.is_step(item):
                raise TodoError(f"{args.id} is a {VOCAB.role('step_kind')}: Jacob's own step, never dispatched; "
                                "todo steps --run closes it once its done_check passes")
            appr, by_rule = approval.effective(item, store.repo)
            if appr is None:
                raise TodoError(f"{args.id} carries no approval, and rule {VOCAB.approval_rule['id']} does not cover it "
                                f"({'; '.join(approval.rule_misses(item, store.repo))}): only approved work is "
                                f"dispatched (todo approve {args.id} --source ...)")
            note = args.note.strip() if args.note else None
            if note and "\n" in note:
                raise TodoError("--note must be one line")
            item["dispatched"] = {"date": today(), "text": note or None}
            msg = f"dispatched {args.id} ({today()})"
            if by_rule:
                item["approved"] = appr
                msg += f", approved by rule {VOCAB.approval_rule['id']}, not by Jacob"
            why = not_ready_reasons(workspace(args, store), item)
            if why:
                msg += f"; note: todo brief calls it NOT READY ({'; '.join(why)})"
        commit(store)
    print(msg)


def dispatch_view(ws, repo=None):
    """What can be dispatched now, across every scanned store: open items Jacob
    approved, not dispatched, and ready as `todo brief` judges it. Every approved
    open item is accounted for: listed, held (with why), or dispatched; the open
    items with no approval are counted, never silently dropped."""
    view = {"dispatchable": [], "by_rule": [], "held": [], "dispatched": [], "unapproved": 0,
            "unreadable": list(ws.errors)}
    for s in ws.stores:
        for it in s.items:
            if repo and it.get("repo") != repo:
                continue
            if it.get("kind") == VOCAB.role("report_kind"):
                continue  # its work lives in the owner's store, under the counterpart's id
            # Jacob's own yes, or rule TD-B1's (todolib/approval.py), never mistaken for his.
            appr, by_rule = approval.effective(it, s.repo)
            if appr is None:
                view["unapproved"] += 1
                continue
            gid = tagging.global_id(it["id"])
            if it.get("dispatched"):
                d = it["dispatched"]
                view["dispatched"].append({"id": gid, "date": d.get("date") if isinstance(d, dict) else None,
                                           "text": d.get("text") if isinstance(d, dict) else None, "by_rule": by_rule})
                continue
            if not checks.approved_ok(appr):
                view["held"].append({"id": gid, "why": ["approved is malformed (todo check names it)"], "by_rule": by_rule})
                continue
            if is_split(ws, it):
                continue  # split: its children carry the approval and the work
            why = not_ready_reasons(ws, it)
            if why:
                view["held"].append({"id": gid, "why": why, "by_rule": by_rule})
                continue
            view["by_rule" if by_rule else "dispatchable"].append(
                {"id": gid, "repo": it["repo"], "work": it["work"], "size": it["size"],
                 "title": it["title"], "approved": appr, "store": str(s.dir),
                 "brief": f"todo brief {gid}", "mark": f"todo -C {s.dir} dispatch {it['id']}"})
    return view


def cmd_dispatchable(args):
    ws = read_workspace(args)
    known_repo(ws, args.repo)
    view = dispatch_view(ws, args.repo)
    if args.json:
        print(json.dumps(view, indent=1, ensure_ascii=False))
    else:
        def row(r, approved):
            print(f"{r['id']:<11} repo {r['repo']:<16} work {r['work']:<9} size {r['size']}  "
                  f"{approved}  {r['title'][:TITLE_WIDTH]}")
            print(f"{'':<11} brief: {r['brief']}   mark it handed out: {r['mark']}")
        for r in view["dispatchable"]:
            row(r, f"approved {r['approved']['date']}")
        if view["by_rule"]:
            rule = VOCAB.approval_rule
            print(f"approved by rule {rule['id']}, not by Jacob ({len(view['by_rule'])}): {rule['source']}")
            for r in view["by_rule"]:
                row(r, f"rule {rule['id']}")
        if not view["dispatchable"] and not view["by_rule"]:
            # PLAN-todo-tool.md §10.2 step 3: what holds the rest, not a bare count.
            n = VOCAB.blocker_bounds["dispatchable_lines"]
            roots = rootlib.view(ws, args.repo)
            print(f"(nothing dispatchable; {roots['items']} open item(s) held under {len(roots['roots'])} root(s), "
                  f"the top {min(n, len(roots['roots']))} here, every one in todo blockers:)")
            for line in rootlib.lines(dict(roots, roots=roots["roots"][:n])):
                print(line)
        if view["held"]:
            print(f"approved, held back ({len(view['held'])}):")
            for h in view["held"]:
                rule = f" (rule {VOCAB.approval_rule['id']})" if h["by_rule"] else ""
                print(f"  {h['id']:<11} {'; '.join(h['why'])}{rule}")
        if view["dispatched"]:
            print(f"approved, already dispatched ({len(view['dispatched'])}): "
                  + ", ".join(f"{d['id']} ({d['date']}{', rule ' + VOCAB.approval_rule['id'] if d['by_rule'] else ''})"
                              for d in view["dispatched"]))
        if view['dispatchable'] or view['by_rule']:
            print(f"({view['unapproved']} open item(s) carry no approval)")
        for e in view["unreadable"]:
            print(f"UNREADABLE  {e}")
    if view["unreadable"]:
        print("todo: UNCHECKED: a store could not be read, so this list may be missing its items", file=sys.stderr)
        sys.exit(3)


def cmd_blockers(args):
    """Every open item that is not dispatchable, across every scanned store, grouped
    by its root and ranked by how many wait behind it (todolib/blockers.py)."""
    ws = read_workspace(args)
    known_repo(ws, args.repo)
    v = rootlib.view(ws, args.repo)
    if args.json:
        print(json.dumps(v, indent=1, ensure_ascii=False))
    else:
        print(f"todo blockers: {v['items']} open item(s) not dispatchable, under {len(v['roots'])} root(s)")
        for line in rootlib.lines(v):
            print(line)
        for e in v["unreadable"]:
            print(f"UNREADABLE  {e}")
    if v["unreadable"]:
        print("todo: UNCHECKED: a store could not be read, so its items are missing here", file=sys.stderr)
        sys.exit(3)


def stale_plans_view(ws, args):
    """The open items, across every scanned store, whose plan section is no longer
    what they were made from: `changed` (its text differs from the pin), `section
    gone` (the file or the section is no longer there), or `never pinned` (a plan:
    tag with no pin, so nothing says what the item was made from: never read as
    fresh). A section the plans CLI could not answer for is `unchecked`, never
    fresh and never gone."""
    view = {"stale": [], "fresh": 0, "unchecked": [], "unreadable": list(ws.errors)}
    cli_path, cli_why = plans.resolve_cli(args.plans_cli)
    where = plans_dir(args, ws)
    answers = {}  # one plans-show per section, however many items pin it
    for s in ws.stores:
        for it in s.items:
            if args.repo and it.get("repo") != args.repo:
                continue
            pins = {p.get("plan"): p for p in (it.get("plan_pins") or []) if isinstance(p, dict)}
            for ref in plans.refs(it):
                row = {"id": tagging.global_id(it["id"]), "repo": it.get("repo"), "plan": plans.shown(ref),
                       "title": it["title"], "last_matched": None}
                pin = pins.get(ref)
                if pin is None:
                    why = "the tag names no section" if plans.split(ref)[1] is None else "no --pin-plan recorded"
                    view["stale"].append(dict(row, state="never pinned", why=why))
                    continue
                row["last_matched"] = pin.get("date")
                if cli_why:
                    view["unchecked"].append(dict(row, why=cli_why))
                    continue
                if ref not in answers:
                    answers[ref] = plans.show(cli_path, where, ref)
                state, value = answers[ref]
                if state == plans.ERROR:
                    view["unchecked"].append(dict(row, why=value))
                elif state == plans.GONE:
                    view["stale"].append(dict(row, state="section gone", why=value))
                elif value != pin.get("digest"):
                    view["stale"].append(dict(row, state="changed", why=f"its text differs from the pin of {pin.get('date')}"))
                else:
                    view["fresh"] += 1
    return view


def close_passed(store, passed):
    """Under the store's lock, close each open step whose done_check exited 0 when
    run (passed: id -> the done_check that ran), with resolution
    roles.step_resolution, provided it is still open with that same done_check: one
    changed while its check ran is judged next run. Returns the ids closed; raises
    TodoError when the store refuses a write (its TODO.md hand-edited)."""
    closed = []
    with store.lock():
        store.load()
        require_clean(store)
        for it in list(store.items):
            check = passed.get(it["id"])
            if check is None or not stepping.is_step(it) or it.get("done_check") != check:
                continue
            done = dict(it, status=VOCAB.closed, done=today(), resolution=VOCAB.role("step_resolution"))
            validate(done, "history")
            store.history["items"].append(done)
            store.items.remove(it)
            closed.append(it["id"])
        if closed:
            commit(store)
    return closed


def cmd_steps(args):
    """Jacob's open steps in this store, numbered (PLAN-architecture.md §11 S7). With
    --run, each done_check runs first, outside the lock (a check may itself call
    todo); then close_passed closes each step whose check exited 0. A check that
    could not be judged is UNCHECKED (exit 3) once all the rest are reported and
    closed. --findings is the S7 detector's command instead (steps_findings)."""
    store = open_store(args)
    if args.findings:
        return steps_findings(args, store)
    rows = [{"n": n, "id": it["id"], "title": it["title"], "done_check": it.get("done_check"),
             "verdict": None, "detail": None} for n, it in enumerate(stepping.open_steps(store), 1)]
    closed = []
    if args.run:
        for r in rows:
            r["verdict"], r["detail"] = stepping.run_check(r["done_check"], store.dir)
        passed = {r["id"]: r["done_check"] for r in rows if r["verdict"] == stepping.DONE}
        if passed:
            closed = close_passed(store, passed)
    unjudged = [r for r in rows if args.run and r["verdict"] is None]
    if args.json:
        print(json.dumps({"steps": rows, "closed": closed}, indent=2))
    else:
        if not rows:
            print(f"(no open {VOCAB.role('step_kind')} in {store.path})")
        for r in rows:
            state = "" if not args.run else (" closed" if r["id"] in closed else
                                             f" {r['verdict'] or 'UNCHECKED'} ({r['detail']})")
            print(f"{r['n']:>2}. {r['id']:<8} {r['title'][:TITLE_WIDTH]}{state}")
            print(f"    done when: {r['done_check']}")
    if unjudged:
        raise Unchecked(f"{len(unjudged)} step(s) could not be judged: "
                        + "; ".join(f"{r['id']} {r['detail']}" for r in unjudged))


def steps_findings(args, store):
    """`todo steps --findings [--run]`, the S7 detector's command (PLAN-todo-tool.md
    §10.5): every open step in every scanned store whose done_check exits 0 is a
    finding in the detector form, one per step. With --run each such step is closed
    first (close_passed, store by store), so only one that could not be closed is
    reported, with why. A check not taken, or one that could not be judged, is no
    finding: `todo steps --run` names those. Prints the JSON list, nothing else."""
    found = []
    for s in sorted(workspace(args, store).stores, key=lambda s: s.repo):
        passed = {}
        for it in stepping.open_steps(s):
            verdict, _ = stepping.run_check(it.get("done_check"), s.dir)
            if verdict == stepping.DONE:
                passed[it["id"]] = it
        if not passed:
            continue
        closed, why = [], None
        if args.run:
            try:
                closed = close_passed(s, {k: it.get("done_check") for k, it in passed.items()})
            except TodoError as e:
                why = str(e)
        for sid, it in passed.items():
            if sid in closed:
                continue
            found.append({"repo": s.repo, "subject": f"{sid} is taken: its done_check passes", "count": 1,
                          "evidence": f"{it['title']}: `{it.get('done_check')}` exits 0"
                                      + (f"; not closed: {why}" if why else ""),
                          "clears_with": f"todo steps --run, in {s.repo}"})
    print(json.dumps(found, indent=1, ensure_ascii=False))


def cmd_stale_plans(args):
    ws = read_workspace(args)
    known_repo(ws, args.repo)
    view = stale_plans_view(ws, args)
    if args.json:
        print(json.dumps(view, indent=1, ensure_ascii=False))
    else:
        for r in view["stale"]:
            since = f"last matched {r['last_matched']}" if r["last_matched"] else "never matched"
            print(f"{r['id']:<11} repo {r['repo'] or '-':<16} {r['plan']:<28} {r['state']:<13} {since}  {r['title'][:TITLE_WIDTH]}")
        if not view["stale"]:
            print("(no open item's plan section has changed, gone, or gone unpinned)")
        print(f"({view['fresh']} pinned section(s) still match)")
        for r in view["unchecked"]:
            print(f"UNCHECKED  {r['id']} {r['plan']}: {r['why']}")
        for e in view["unreadable"]:
            print(f"UNREADABLE  {e}")
    if view["unchecked"] or view["unreadable"]:
        print("todo: UNCHECKED: a section or a store could not be read, so this list may be missing items",
              file=sys.stderr)
        sys.exit(3)


def sync_plans_plan(args, store, ws, cli_path, date):
    """(actions, notices, plans read, steps read) of one sync: writes nothing."""
    where = plans_dir(args, ws)
    if args.files:
        files = [Path(f) if Path(f).is_file() or not (where / f).is_file() else where / f for f in args.files]
    else:
        files = sorted(where.glob("PLAN-*.md"))
    steps_by_file, notices = {}, []
    for p in files:
        steps, why = syncplans.read_steps(cli_path, p)
        if why:
            notices.append(why + "; its items are left as they are")
        else:
            steps_by_file[p.name] = steps
    judged = set(steps_by_file)
    if not args.files:
        # A full run also judges the items of a plan file no longer there (all gone).
        judged |= {it["plan_step"]["file"] for s in ws.stores for it in s.items
                   if syncplans.is_step_item(it) and not syncplans.plan_step_problems(it)
                   and not (where / it["plan_step"]["file"]).is_file()}
    answers = {}  # one plans-show per section, however many steps it holds

    def pin(ref):
        if ref not in answers:
            answers[ref] = plans.show(cli_path, where, ref)
        return answers[ref]

    actions, more = syncplans.plan(ws, store, steps_by_file, judged, pin, date)
    return actions, notices + more, len(steps_by_file), sum(map(len, steps_by_file.values()))


def sync_plans_apply(actions, notices):
    """Write the actions that change a store, all-or-nothing per store: a store
    whose TODO.md is hand-edited (or history missing) keeps its changes back, said
    in a notice; an item the store would refuse is one notice, never a guess.
    Returns the actions written."""
    writes = [a for a in actions if a["store"] is not None and a["action"] in syncplans.WRITES]
    blocked = set()
    for s in {a["store"].dir: a["store"] for a in writes}.values():
        try:
            require_clean(s)
        except TodoError as e:
            blocked.add(s.dir)
            notices.append(f"{s.repo}: nothing written there ({e})")
    done = []
    for a in writes:
        s = a["store"]
        if s.dir in blocked:
            continue
        it, changes = a["item"], a["changes"]
        try:
            if a["action"] in (syncplans.NEW, syncplans.DECISION):
                validate(it, require_decision=a["action"] == syncplans.DECISION)
                it["id"] = s.allocate()
                s.items.append(it)
            else:
                updated = dict(it, **changes)
                validate(updated, require_waits=bool({"status", "waits_on"} & set(changes)))
                it.update(updated)
        except TodoError as e:
            notices.append(f"{a['plan'] or a['detail']}: not written ({e})")
            continue
        done.append(a)
    commit_all({a["store"] for a in done})
    return done


def cmd_sync_plans(args):
    """Plans generate their items (PLAN-services.md §3 G6, §4 step 6.3): see
    todolib/syncplans.py. Fails open: whatever stops it is one NOTICE line on
    stderr and exit 0, never a stopped turn."""
    date = today()
    try:
        store = open_store(args)
        cli_path, why = plans.resolve_cli(args.plans_cli)
        if why:
            raise TodoError(why)
        if args.dry_run:
            ws = workspace(args, store)
            actions, notices, n_plans, n_steps = sync_plans_plan(args, store, ws, cli_path, date)
        else:
            with locked_workspace(args, store) as ws:
                actions, notices, n_plans, n_steps = sync_plans_plan(args, store, ws, cli_path, date)
                written = {id(a) for a in sync_plans_apply(actions, notices)}
                actions = [a for a in actions if a["store"] is None or a["action"] not in syncplans.WRITES
                           or id(a) in written]
    except (TodoError, OSError) as e:
        print(f"todo sync-plans: NOTICE: {e}; nothing synced", file=sys.stderr)
        return
    notices += [f"a store could not be read: {e}" for e in ws.errors]
    rows = [{"action": a["action"], "id": a["item"] and a["item"].get("id") and tagging.global_id(a["item"]["id"]),
             "repo": a["store"].repo if a["store"] else None, "plan": a["plan"],
             "title": a["item"]["title"] if a["item"] else None, "detail": a["detail"], "quiet": a["quiet"]}
            for a in actions]
    counts = {k: sum(r["action"] == k for r in rows) for k in syncplans.ORDER}
    if args.json:
        print(json.dumps({"dry_run": args.dry_run, "plans": n_plans, "steps": n_steps, "actions": rows,
                          "notices": notices, "counts": counts}, indent=1, ensure_ascii=False))
    else:
        cap = syncplans.spec()["max_listed"]
        for kind in syncplans.ORDER:
            shown = [r for r in rows if r["action"] == kind and not r["quiet"]]
            for r in shown[:cap]:
                head = f"{r['id'] or '(new)'} ({r['repo']})" if r["repo"] else "-"
                print(f"{kind:<12} {head} {r['plan'] or ''}: " + (f"{r['title']} -- " if r["title"] else "") + r["detail"])
            if len(shown) > cap:
                print(f"{kind:<12} +{len(shown) - cap} more (--json lists them)")
        said = ", ".join(f"{k} {n}" for k, n in counts.items() if n) or "nothing to do"
        print(f"sync-plans: {n_plans} plan(s), {n_steps} step(s): {said}"
              + (" (dry run: nothing written)" if args.dry_run else ""))
    for n in notices:
        print(f"todo sync-plans: NOTICE: {n}", file=sys.stderr)


def detect_apply(actions, notices, date, here):
    """Write detect's actions, all-or-nothing per store as sync_plans_apply does: a
    store whose TODO.md is hand-edited keeps its changes back, said in a notice; an
    item the store would refuse is one notice, never a guess. A new item for such a
    store is filed here instead (it names its repo): the finding may be that very
    store's state. Returns those written."""
    blocked = set()
    for s in {a["store"].dir: a["store"] for a in actions}.values():
        try:
            require_clean(s)
        except TodoError as e:
            blocked.add(s.dir)
            notices.append(f"{s.repo}: nothing written there ({e})" + ("" if s.dir == here.dir else
                           "; a new finding for it is filed here"))
    done = []
    for a in actions:
        s, it = a["store"], a["item"]
        if s.dir in blocked and a["action"] == detect.NEW and here.dir not in blocked:
            s = a["store"] = here
        if s.dir in blocked:
            continue
        try:
            if a["action"] == detect.NEW:
                validate(it)
                it["id"] = s.allocate()
                s.items.append(it)
            elif a["action"] == detect.SEEN:
                updated = dict(it, **a["changes"])
                validate(updated, require_waits=False)
                it.update(updated)
            else:
                closed = dict(it, status=VOCAB.closed, done=date, resolution=VOCAB.role("detector_resolution"))
                validate(closed, "history")
                s.history["items"].append(closed)
                s.items.remove(it)
        except TodoError as e:
            notices.append(f"{a['detector']} {a['detail']}: not written ({e})")
            continue
        done.append(a)
    return done


def cmd_detect(args):
    """`todo detect [--id D] [--json]` (PLAN-todo-tool.md §10.5): run each detector,
    outside any lock, then reconcile its findings with the items under the lock of
    every scanned store (todolib/detect.py), and record each run in this store's
    records. Exit 1 when a detector failed (filed as a stall, its items unjudged)."""
    store = open_store(args)
    detectors, source = detect.registered()
    if source:
        print(f"todo detect: NOTICE: detectors read from {source} ({detect.LIST_ENV}), not vocab.json", file=sys.stderr)
    if args.id:
        detectors = [d for d in detectors if d["id"] == args.id]
        if not detectors:
            raise TodoError(f"--id {args.id}: no such detector; registered: "
                            + (", ".join(d["id"] for d in detect.registered()[0]) or "none"))
    root = scan_root(store.dir, args.root)
    at, date = detect.now(), today()
    results = [(det, *detect.run(det, store.dir, root, at)) for det in detectors]
    with locked_workspace(args, store) as ws:
        require_clean(store)  # the runs are recorded here, whatever else is written
        actions, notices = detect.plan(ws, store, results, date)
        done = detect_apply(actions, notices, date, store)
        runs = store.ensure_records().setdefault("runs", {})
        for det, _, rec in results:
            runs[det["id"]] = rec
        commit_all([store, *(a["store"] for a in done)])
    notices += [f"a store could not be read: {e}" for e in ws.errors]
    rows = [{"action": a["action"], "id": tagging.global_id(a["item"]["id"]), "repo": a["store"].repo,
             "detector": a["detector"], "title": a["item"]["title"], "detail": a["detail"]} for a in done]
    failed = [(det["id"], rec["why"]) for det, _, rec in results if not rec["ok"]]
    if args.json:
        print(json.dumps({"runs": {det["id"]: rec for det, _, rec in results}, "actions": rows, "notices": notices},
                         indent=1, ensure_ascii=False))
    else:
        for r in sorted(rows, key=lambda r: detect.ORDER.index(r["action"])):
            print(f"{r['action']:<8} {r['id']} ({r['repo']}) {r['title']}")
        counts = ", ".join(f"{k} {n}" for k in detect.ORDER if (n := sum(r["action"] == k for r in rows))) or "no change"
        print(f"detect: {len(results)} detector(s) run, {len(failed)} failed: {counts}")
    for n in notices:
        print(f"todo detect: NOTICE: {n}", file=sys.stderr)
    if failed:
        raise TodoError("; ".join(f"detector {d} failed: {why}" for d, why in failed)
                        + " (filed as a stall; its items stay as they were)")


def handoff_line(it, where):
    """The brief's resume point (PLAN-small-tasks.md §4.3): the last handoff and
    the commit it was written at, with that commit's subject read from the work
    repo, and a warning when the repo has moved on since the note was written."""
    h = it.get("handoff")
    if not h:
        return "Handoff: none yet (start from the top)"
    if not isinstance(h, dict):
        return f"Handoff: malformed ({h!r}; todo check names it): read it, then write a new one"
    sha = h.get("commit")
    if not sha:
        return f"Handoff ({h.get('date')}, no checkpoint commit recorded): {h.get('text')}"
    subject = commit_subject(where, sha)
    missing = f"(not found in {where})" if where else f"(repo {it.get('repo')} is in no scanned store)"
    line = f"Handoff ({h.get('date')}, at {sha} {subject or missing}): {h.get('text')}"
    now = head_commit(where)
    if subject and now and not (now.startswith(sha) or sha.startswith(now)):
        line += f"\n  HEAD is now {now} {commit_subject(where, now)}: commits after the handoff are not in its note"
    return line


def cmd_brief(args):
    ws = read_workspace(args)
    it, where, s = ws.find(args.id)
    if it is None:
        raise TodoError(f"{args.id} is in no scanned store or history")
    if where == "history":
        raise TodoError(f"{args.id} closed {it.get('done') or '(undated)'}: {it.get('resolution') or ''}")
    if not it.get(BRIEF_REFUSES_WITHOUT):
        # No brief at all, not one marked NOT READY: a brief is what a dispatch is held to,
        # and one without its done-when has no end (README "todo brief").
        raise TodoError(f"todo:{it['id']} has no {BRIEF_REFUSES_WITHOUT}: no brief is written without one "
                        f"(todo edit {it['id']} --done-when \"...\")")
    print(f"todo:{it['id']}  ({it.get('kind')}, {it.get('status')}; repo {it.get('repo')}, work {it.get('work')}, size {it.get('size')})")
    print(f"What: {it['title']}")
    if it.get("evidence"):
        print("Why (evidence):")
        for ln in it["evidence"].split("\n"):
            print("  " + ln)
    for label, f in (("Probe", "probe"), ("Retire when", "retire"), ("Files", "files"), ("Done when", "done_when")):
        if it.get(f):
            print(f"{label}: {', '.join(it[f]) if isinstance(it[f], list) else it[f]}")
    if it.get("parent"):
        p = ws.find(it["parent"])[0]
        print(f"Parent: {it['parent']} -- {p['title'] if p else '(unresolved)'}")
    blockers = deps.open_blockers(ws, it)
    if it.get("blocked_by"):
        print(f"Blocked by: {', '.join(it['blocked_by'])}" + (f" (still open: {', '.join(blockers)})" if blockers else " (all closed)"))
    appr, by_rule = approval.effective(it, s.repo)
    print("Approved: " + (f"by rule {VOCAB.approval_rule['id']}, not by Jacob: {appr['source']}" if by_rule else
                          field_value("approved", appr) if appr else
                          f"no (todo approve {it['id']} --source ...; rule {VOCAB.approval_rule['id']}: "
                          f"{'; '.join(approval.rule_misses(it, s.repo))})"))
    if it.get("dispatched"):
        print(f"Dispatched: {field_value('dispatched', it['dispatched'])}")
    print(handoff_line(it, work_dir(ws, s, it)))
    todo_bin = Path(sys.argv[0]).resolve()
    print(f"Hand off at each checkpoint: {todo_bin} -C {s.dir} edit {it['id']} --handoff \"done; next; how to verify\"")
    print(f"Close it: {todo_bin} -C {s.dir} done {it['id']} --resolution \"...\"")
    print(f"Iterate rule: {VOCAB.brief['iterate_rule']}")
    print(f"Stop rule: {VOCAB.brief['stop_rule']}")
    why = not_ready_reasons(ws, it)
    if why:
        print(f"NOT READY: {'; '.join(why)}")
        sys.exit(1)


def cmd_history(args):
    if args.id:
        ws = read_workspace(args)
        it, where, s = ws.find(args.id)
        if it is None or where != "history":
            raise TodoError(f"{args.id} is not in any scanned history" + (" (it is still open: todo show)" if it else ""))
        print_item(it, where, s, ws)
        return
    store = open_store(args)
    ws = workspace(args, store)
    s = ws.by_repo(args.repo) if args.repo else store
    if s is None:
        raise TodoError(f"no store for repo {args.repo!r} in the scan (todo repos lists them)")
    items = history_order(s.closed)
    filtered = bool(args.since or args.kind or args.grep)
    if args.since:
        items = [it for it in items if (it.get("done") or "") >= args.since]
    if args.kind:
        items = [it for it in items if it.get("kind") == args.kind]
    if args.grep:
        needle = args.grep.lower()
        items = [it for it in items if needle in " ".join(str(it.get(f) or "") for f in ("title", "evidence", "resolution", "probe")).lower()]
    if not filtered:
        items = items[:10]
    for it in items:
        print(f"{it['id']:<8} {it.get('done') or '(undated)':<10} {it.get('kind'):<9} {it['title'][:TITLE_WIDTH]}")
        if it.get("resolution"):
            print(f"{'':<8} -> {it['resolution'][:TITLE_WIDTH * 2]}")
    if not items:
        print("(no closed items match)")


# -- the parser --------------------------------------------------------------

COMMANDS = {
    "init": (cmd_init, "start a store here: todo.json, todo-history.json"),
    "add": (cmd_add, "add an open item"),
    "edit": (cmd_edit, "change fields of an open item"),
    "done": (cmd_done, "close an item: it moves to todo-history.json"),
    "report": (cmd_report, "mark an item reported; create its counterpart in the owner's store"),
    "list": (cmd_list, "open items, one line each"),
    "show": (cmd_show, "one item in full, open or closed, any repo"),
    "render": (cmd_render, "write TODO.md (or TODO-HISTORY.md) from the store"),
    "tree": (cmd_tree, "items and their children, across repos"),
    "check": (cmd_check, "every gate over this store"),
    "import": (cmd_import, "a hand-written or hand-edited TODO.md into items"),
    "repos": (cmd_repos, "every store the scan finds; --status: every git repo, its open items, last commit, uncommitted files"),
    "ready": (cmd_ready, "open items with repo, work and done_when set: dispatchable"),
    "brief": (cmd_brief, "an item as a dispatch brief"),
    "history": (cmd_history, "closed items, newest first"),
    "get": (cmd_get, "one record by id, as JSON, with its tags"),
    "find": (cmd_find, "the ids and titles of the records holding every tag named"),
    "refs": (cmd_refs, "the records whose ref: tag names this id"),
    "split": (cmd_split, "break an item into children, each one checkpoint; it closes with its last child"),
    "reseal": (cmd_reseal, "accept a store file changed around the CLI, recorded in hand_edits"),
    "approve": (cmd_approve, "record Jacob's approval of an item: the day and where he gave it"),
    "dispatch": (cmd_dispatch, "mark an approved item handed out (--clear when it comes back unfinished)"),
    "dispatchable": (cmd_dispatchable, "what can be dispatched now: approved, not dispatched, ready; every store"),
    "blockers": (cmd_blockers, "every open item not dispatchable, grouped by its root blocker, most items freed first; every store"),
    "stale-plans": (cmd_stale_plans, "open items whose plan section changed, is gone, or was never pinned"),
    "steps": (cmd_steps, "Jacob's open steps, numbered; --run closes each whose done_check exits 0"),
    "decisions": (cmd_decisions, "open decisions as a numbered table for Jacob, most items freed first; recorded as dt-N"),
    "answer": (cmd_answer, "apply Jacob's reply to a decisions table: 1) yes 2) no 3) <option>; other words kept"),
    "sync-plans": (cmd_sync_plans, "make and update the step items of each plan's steps; list stale, gone, unplaced; fails open"),
    "detect": (cmd_detect, "run the detectors: file, update and close their stall and lag items; record each run"),
    "help": (cmd_help, "this list of commands"),
}


def add_item_fields(p, editing):
    p.add_argument("--kind", choices=list(VOCAB.kinds), required=not editing)
    p.add_argument("--status", choices=list(VOCAB.statuses))
    p.add_argument("--evidence")
    p.add_argument("--probe")
    p.add_argument("--parent")
    p.add_argument("--blocked-by", dest="blocked_by", nargs="*", metavar="ID",
                   help="ids that must close first (any scanned repo); no ids clears it")
    p.add_argument("--waits-on", dest="waits_on", metavar="W",
                   help=f"what a {VOCAB.jacob_status} item waits on: {VOCAB.waits_on_forms()}"
                        + ("; \"\" clears it" if editing else ""))
    p.add_argument("--repo")
    p.add_argument("--work", choices=list(VOCAB.works) + ([""] if editing else []))
    p.add_argument("--size", choices=list(VOCAB.sizes) + ([""] if editing else []),
                   help=f"the estimate; {VOCAB.split_size} is split before it is started (todo split)")
    p.add_argument("--files", nargs="*")
    p.add_argument("--research", nargs="*", metavar="RS_ID",
                   help=f"the {VOCAB.research_service} service's question ids this item rests on "
                        f"(rs-3 or {VOCAB.research_service}:rs-3); required on a research item"
                        + ("; with no ids, clears them" if editing else ""))
    p.add_argument("--done-when", dest="done_when")
    p.add_argument("--done-check", dest="done_check", metavar="COMMAND",
                   help=f"a shell command that exits 0 once the step is taken; required on a {VOCAB.role('step_kind')} "
                        "(todo steps --run runs it in this store's folder)")
    p.add_argument("--retire")
    p.add_argument("--tags", nargs="*", metavar="TAG",
                   help="plan:, origin:, trust: and ref: tags (the rest derive from the fields); no tags clears them")
    dk = VOCAB.role("decision_kind")
    p.add_argument("--pointer", metavar="'FILE §n'",
                   help=f"a {dk}'s plan section, which must resolve (plans show)" + ("; \"\" clears it" if editing else ""))
    p.add_argument("--hinges-on", dest="hinges_on", metavar="TEXT", help=f"one line: what a {dk} hinges on")
    p.add_argument("--recommend", metavar="ANSWER",
                   help=f"a {dk}'s recommended answer: {' or '.join(VOCAB.decisions['verdicts'])}, or an option's name")
    p.add_argument("--option", action="append", metavar="NAME=TEXT",
                   help=f"one of a {dk}'s options; repeat for each" + ("; replaces them all, --option '' clears" if editing else ""))
    if not editing:
        p.add_argument("--reported-to", dest="reported_to", metavar="REPO",
                       help="a report's owner; writes no other store (todo report does). A counterpart "
                            "is paired later with todo edit ID --reported-to REPO:THEIR_ID")
    if editing:
        p.add_argument("--title")
        p.add_argument("--append-evidence", dest="append_evidence", metavar="E",
                       help="add E as a new line after the evidence, under the store's lock (not with --evidence)")
        p.add_argument("--handoff", metavar="NOTE",
                       help="at a checkpoint: 'done; next; how to verify', kept with today's date and the work "
                            "repo's commit; replaces the last one, \"\" clears it")
        p.add_argument("--reported-to", dest="reported_to", metavar="REPO[:THEIR_ID]",
                       help="a report's owner, and its counterpart there when it exists; writes no other store "
                            "(todo report does); THEIR_ID must be an item of REPO's store whose parent is ID")


def build_parser():
    ap = argparse.ArgumentParser(prog="todo", description="Structured TODO items per repo; TODO.md is rendered from todo.json.")
    ap.add_argument("-C", metavar="DIR", help="the repo whose store to use (default: the git repo holding the cwd)")
    ap.add_argument("--root", metavar="DIR", help="where to scan for other repos' stores")
    sub = ap.add_subparsers(dest="command", metavar="command")
    ps = {name: sub.add_parser(name, help=help_) for name, (_, help_) in COMMANDS.items()}
    ps["init"].add_argument("--prefix", required=True)
    ps["init"].add_argument("--repo")
    ps["add"].add_argument("title")
    add_item_fields(ps["add"], editing=False)
    ps["edit"].add_argument("id")
    add_item_fields(ps["edit"], editing=True)
    ps["done"].add_argument("id")
    how = ps["done"].add_mutually_exclusive_group(required=True)
    how.add_argument("--resolution")
    how.add_argument("--as", dest="as_", choices=[VOCAB.role("decision_rejected_resolution")],
                     help=f"a {VOCAB.role('decision_kind')} Jacob said no to: close it and put every item it "
                          "blocks back to waiting on him (with --reason)")
    ps["done"].add_argument("--reason", help="with --as: one line, why (his words, or a pointer to them)")
    ps["report"].add_argument("id")
    ps["report"].add_argument("--to", required=True)
    ps["report"].add_argument("--kind", choices=list(VOCAB.kinds), help="the counterpart's kind (default: the item's)")
    ps["list"].add_argument("--kind", choices=list(VOCAB.kinds))
    ps["list"].add_argument("--status", choices=list(VOCAB.statuses))
    ps["list"].add_argument("--repo")
    ps["list"].add_argument("--mine", action="store_true")
    ps["list"].add_argument("--all", action="store_true")
    split = ps["list"].add_mutually_exclusive_group()
    split.add_argument("--ready", action="store_true", help="only items whose blocked_by ids are all closed (or none)")
    split.add_argument("--blocked", action="store_true", help="only items with a blocked_by id still open")
    ps["list"].add_argument("--cites", metavar="'FILE §n'",
                            help="only items citing that plan section or one inside it (a plan: tag, a step's "
                                 "plan_step, a decision's pointer), in every scanned store; FILE alone cites any")
    ps["show"].add_argument("id")
    ps["render"].add_argument("--all", action="store_true")
    ps["render"].add_argument("--history", action="store_true")
    ps["render"].add_argument("--force", action="store_true")
    ps["tree"].add_argument("id", nargs="?")
    ps["check"].add_argument("--all", action="store_true")
    ps["import"].add_argument("file")
    ps["import"].add_argument("--dry-run", action="store_true")
    ps["import"].add_argument("--waits-on", dest="waits_on", metavar="VALUE",
                              help="the waits_on of each waiting-jacob item whose text names none")
    ps["ready"].add_argument("--repo")
    ps["ready"].add_argument("--work", choices=list(VOCAB.works))
    ps["brief"].add_argument("id")
    ps["history"].add_argument("id", nargs="?")
    ps["history"].add_argument("--since")
    ps["history"].add_argument("--repo")
    ps["history"].add_argument("--kind", choices=list(VOCAB.kinds))
    ps["history"].add_argument("--grep")
    ps["reseal"].add_argument("--reason", required=True)
    ps["split"].add_argument("id")
    ps["split"].add_argument("titles", nargs="+", metavar="TITLE", help="one child per title")
    ps["split"].add_argument("--size", choices=VOCAB.ready_sizes, required=True, help="every child's size")
    ps["get"].add_argument("id")
    ps["find"].add_argument("tags", nargs="+", metavar="TAG")
    ps["refs"].add_argument("id")
    for name in ("find", "refs"):
        ps[name].add_argument("--open", action="store_true", help="open items only, not history")
        ps[name].add_argument("--json", action="store_true")
    ps["approve"].add_argument("id")
    ps["approve"].add_argument("--source", help="one line: where Jacob approved it (his words, or a pointer to them)")
    ps["approve"].add_argument("--date", help="the day he approved it, YYYY-MM-DD (default today)")
    ps["approve"].add_argument("--clear", action="store_true", help="remove the approval (refused while dispatched)")
    ps["approve"].add_argument("--option", metavar="NAME",
                               help=f"a {VOCAB.role('decision_kind')}: the option Jacob chose (it closes on it)")
    ps["decisions"].add_argument("--from", dest="from_", metavar="TABLE",
                                 help="table only the rows of this earlier table still open, recording what each supersedes")
    ps["decisions"].add_argument("--json", action="store_true")
    ps["answer"].add_argument("reply", help="his reply, e.g. '1) yes 2) no 3) b 4) not yet, ask after the move'")
    ps["answer"].add_argument("--table", metavar="TABLE", help="the table it answers (default: the latest; or lead the reply with 'dt-N:')")
    ps["dispatch"].add_argument("id")
    ps["dispatch"].add_argument("--note", help="one line, e.g. where the Dispatch line is; never who")
    ps["dispatch"].add_argument("--clear", action="store_true", help="it came back unfinished: list it again")
    ps["dispatchable"].add_argument("--repo", help="only items whose work lives in this repo")
    ps["dispatchable"].add_argument("--json", action="store_true")
    ps["blockers"].add_argument("--repo", help="only items whose work lives in this repo")
    ps["blockers"].add_argument("--json", action="store_true", help="every root and every id, unbounded")
    ps["stale-plans"].add_argument("--repo", help="only items whose work lives in this repo")
    ps["stale-plans"].add_argument("--json", action="store_true")
    ps["steps"].add_argument("--run", action="store_true",
                             help="run each step's done_check here; close the steps whose check exits 0")
    ps["steps"].add_argument("--json", action="store_true")
    ps["steps"].add_argument("--findings", action="store_true",
                             help="the S7 detector: every scanned store's steps whose done_check passes, as detector "
                                  "findings (JSON); with --run, closes them first and reports only those it could not")
    ps["detect"].add_argument("--id", metavar="D", help="run this detector alone (its items alone are judged)")
    ps["detect"].add_argument("--json", action="store_true")
    ps["repos"].add_argument("--status", action="store_true",
                             help="every git repo under the root, with a store or not: open items, last commit, uncommitted files")
    ps["repos"].add_argument("--json", action="store_true", help="with --status")
    ps["sync-plans"].add_argument("files", nargs="*", metavar="FILE",
                                  help="the plans to read (default: every PLAN-*.md in --plans-dir, which also "
                                       "judges the items of a plan file no longer there)")
    ps["sync-plans"].add_argument("--dry-run", dest="dry_run", action="store_true", help="say what it would do; write nothing")
    ps["sync-plans"].add_argument("--json", action="store_true", help="every action, uncapped")
    for name in ("add", "edit", "stale-plans", "import", "sync-plans"):
        ps[name].add_argument("--plans-dir", dest="plans_dir", metavar="DIR",
                              help="where the PLAN-*.md files are (default: the scan root)")
        ps[name].add_argument("--plans-cli", dest="plans_cli", metavar="PATH",
                              help="the setup tool whose `plans show` reads a section (default: setup/setup "
                                   "in the first folder above this tool holding one)")
    for name in ("add", "edit"):
        ps[name].add_argument("--pin-plan", dest="pin_plan", action="store_true",
                              help="record each plan:FILE§n tag's section as it reads today (todo stale-plans)")
    return ap


def normalise_ids(args):
    """Every id argument takes `todo:td-3` as well as `td-3` (PLAN-services.md §3).
    get and refs keep theirs: they also answer for another service's id."""
    if args.command not in ("get", "refs") and getattr(args, "id", None):
        args.id = tagging.local_id(args.id)
    if getattr(args, "parent", None):
        args.parent = tagging.local_id(args.parent)
    if getattr(args, "blocked_by", None):
        args.blocked_by = [tagging.local_id(b) for b in args.blocked_by]
    if vars(args).get("research"):
        # research:rs-3 is rs-3 there; stored bare, as blocked_by stores todo ids
        head = VOCAB.research_service + ":"
        args.research = [r[len(head):] if r.startswith(head) else r for r in args.research]


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.command:
        ap.print_help()
        return 0
    try:
        normalise_ids(args)
        COMMANDS[args.command][0](args)
    except Unchecked as e:
        print(f"todo: UNCHECKED: {e}", file=sys.stderr)
        return 3
    except NoStore as e:
        print(f"todo: {e}", file=sys.stderr)
        return EXIT_NO_STORE
    except TodoError as e:
        print(f"todo: {e}", file=sys.stderr)
        return 1
    return 0
