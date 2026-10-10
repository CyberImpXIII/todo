"""The todo CLI: the only way into a store. `todo --help` lists the commands;
README.md documents each one, and tests/test_docs.py holds the two equal."""
import argparse
import difflib
import json
import os
import sys
from pathlib import Path

from . import checks, deps, importer, plans
from . import tags as tagging
from .render import field_value, render_history, render_item, render_store, history_order
from .store import (HISTORY_RENDER_FILE, STORE_FILE, Store, TodoError, Workspace, add_days, commit_subject, head_commit,
                    id_number, never_scanned, new_item, scan_root, store_dir_for, today, write_atomic)
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
        raise TodoError(f"no {STORE_FILE} in {d}, and none under {root} (todo repos lists the stores a scan finds; "
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


def validate(item, where="store"):
    """Refuse an item `check` would fail: declared vocabulary, required fields."""
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
        if name in ("handoff", "approved", "dispatched", "plan_pins"):
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
        item = new_item(title=args.title, kind=args.kind, status=args.status or VOCAB.role("default_status"),
                        evidence=args.evidence, probe=args.probe, parent=args.parent,
                        repo=args.repo or store.repo, work=args.work, size=args.size, files=args.files,
                        done_when=args.done_when, retire=args.retire, added=today())
        if item["status"] == VOCAB.closed:
            raise TodoError("add makes open items; close one with todo done")
        validate(item)
        item["id"] = store.allocate()
        item["blocked_by"] = resolve_blockers(ws, item["id"], args.blocked_by)
        item["tags"] = resolve_tags(ws, args.tags)
        if args.pin_plan:
            item["plan_pins"] = pin_plans(ws, item, args)
        store.items.append(item)
        commit(store)
    print(f"added {item['id']}: {item['title']}")


EDITABLE = ["title", "kind", "status", "evidence", "probe", "parent", "blocked_by", "repo", "work", "size", "files",
            "done_when", "retire", "tags"]


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
        if not changes and not args.pin_plan:
            raise TodoError("nothing to change: name at least one field")
        if changes.get("status") == VOCAB.closed:
            raise TodoError("close an item with `todo done ID --resolution ...`")
        updated = dict(item)
        for f, v in changes.items():
            updated[f] = None if v in ("", []) else v
        validate(updated)
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
    print(f"edited {args.id}: {', '.join(changes)}")


def cmd_done(args):
    store = open_store(args)
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
        made = []
        for title in args.titles:
            child = new_item(**{f: parent.get(f) for f in copied}, title=title, status=VOCAB.role("default_status"),
                             parent=args.id, size=args.size, added=today(),
                             evidence=f"split from {args.id}: {parent['title']}")
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
        item["kind"] = VOCAB.role("report_kind")
        item["reported_to"] = {"repo": args.to, "date": (rt or {}).get("date") or today(), "their_id": their}
        validate(item)
        commit(store)
    finally:
        for lk in reversed(locks):
            lk.__exit__(None, None, None)
    if their:
        print(f"reported {args.id} to {args.to} as {their} ({owner.path}; commit it there)")
    elif hidden:
        print(f"reported {args.id} to {args.to}: a hidden folder, which the scan never enters, so this report "
              f"never pairs. Relay it to its owner by hand (your final report) and close {args.id} by its done_when.")
    else:
        print(f"reported {args.id} to {args.to}: no store for {args.to} in the scan, so no counterpart yet. "
              f"`todo check` lists it as unpaired; re-run this once {args.to} has a todo.json.")


def cmd_list(args):
    store = open_store(args)
    if args.status == VOCAB.closed:
        raise TodoError("closed items are in history: todo history")
    ws = workspace(args, store)
    scope = ws.stores if (args.all or args.repo) else [store]
    n = 0
    for s in scope:
        for it in s.items:
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
        plan = importer.plan_import(text, store, today())
        to_store = [it for it, dest in plan.new if dest == "store"]
        to_hist = [it for it, dest in plan.new if dest == "history"]
        print(f"import {src}: {len(to_store)} new open, {len(to_hist)} new closed, {len(plan.unchanged)} unchanged, "
              f"{plan.already} imported before, {len(plan.closed_seen)} already closed"
              + (f", {len(plan.missing)} missing from the file (kept: {', '.join(plan.missing)})" if plan.missing else ""))
        if plan.changed:
            raise TodoError(f"rendered item(s) edited by hand: {', '.join(plan.changed)}. Nothing imported. "
                            "`todo render --force` keeps the diff in todo.json; then apply it with todo edit.")
        if args.dry_run:
            for it, dest in plan.new:
                print(("  history " if dest == "history" else "  store   ") + f"{it['kind']:<9} {it['status']:<13} {it['title'][:TITLE_WIDTH]}")
            print("(dry run: nothing written)")
            return
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


def cmd_repos(args):
    store = open_store(args)
    ws = workspace(args, store)
    print(f"scan root: {ws.root}")
    for s in ws.stores:
        rel = os.path.relpath(s.dir, ws.root)
        print(f"  {s.repo:<20} {s.prefix:<6} {len(s.items):>4} open {len(s.closed):>5} closed  {rel}")
    for e in ws.errors:
        print(f"  UNREADABLE  {e}")


def size_refusal(it):
    """Why an item's size keeps it from being dispatched, or None (PLAN-small-tasks.md
    §2): unsized, it cannot be judged one checkpoint; too big, it is split first."""
    if it.get("size") is None:
        return f"no size (todo edit {it['id']} --size {'|'.join(VOCAB.sizes)})"
    if it["size"] not in VOCAB.ready_sizes:
        return f"size {it['size']}: split it first (todo split {it['id']} TITLE ... --size {'|'.join(VOCAB.ready_sizes)})"
    return None


def not_ready_reasons(ws, it):
    """Why `todo brief` would call this open item NOT READY, or []: one list, so
    brief and dispatchable never disagree on what ready means."""
    why = []
    missing = [f for f in ("repo", "work", "done_when") if not it.get(f)]
    if missing:
        why.append(f"missing {', '.join(missing)}")
    if it.get("status") != VOCAB.role("default_status"):
        why.append(f"status {it.get('status')}")
    blockers = deps.open_blockers(ws, it)
    if blockers:
        why.append(f"blocked by {', '.join(blockers)}")
    if size_refusal(it):
        why.append(size_refusal(it))
    return why


def ready_items(ws, repo=None, work=None, refused=None):
    """Dispatchable items. An item ready but for its size goes into `refused`
    (a list, when given) as (item, why), so `todo ready` names it rather than
    dropping it unseen."""
    for s in ws.stores:
        for it in s.items:
            if it.get("status") != VOCAB.role("default_status") or it.get("kind") == VOCAB.role("report_kind"):
                continue
            if not (it.get("repo") and it.get("work") and it.get("done_when")):
                continue
            if (repo and it["repo"] != repo) or (work and it["work"] != work):
                continue
            if deps.open_blockers(ws, it):
                continue
            why = size_refusal(it)
            if why:
                if refused is not None:
                    refused.append((it, why))
                continue
            yield it, s


def cmd_ready(args):
    store = open_store(args)
    n, refused = 0, []
    for it, _ in ready_items(workspace(args, store), args.repo, args.work, refused):
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
            if args.source is not None or args.date is not None:
                raise TodoError("--clear takes no --source or --date")
            if not item.get("approved"):
                raise TodoError(f"{args.id} carries no approval to clear")
            if item.get("dispatched"):
                raise TodoError(f"{args.id} was dispatched {item['dispatched'].get('date')}: "
                                f"clear that first (todo dispatch {args.id} --clear)")
            item["approved"] = None
            msg = f"cleared the approval of {args.id}"
        else:
            source = (args.source or "").strip()
            if not source or "\n" in source:
                raise TodoError("--source: one line saying where Jacob approved it (his words, or a pointer to them)")
            date = args.date or today()
            if not checks.DATE_RE.match(date) or date > today():
                raise TodoError(f"--date {date!r}: a YYYY-MM-DD no later than today ({today()})")
            item["approved"] = {"by": VOCAB.approval_by, "date": date, "source": source}
            msg = f"approved {args.id}: {field_value('approved', item['approved'])}"
        commit(store)
    print(msg)


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
        else:
            if not item.get("approved"):
                raise TodoError(f"{args.id} carries no approval: only Jacob's approved work is dispatched "
                                f"(todo approve {args.id} --source ...)")
            if item.get("dispatched"):
                raise TodoError(f"{args.id} was dispatched {item['dispatched'].get('date')} already "
                                f"(todo dispatch {args.id} --clear when it came back unfinished)")
            note = args.note.strip() if args.note else None
            if note and "\n" in note:
                raise TodoError("--note must be one line")
            item["dispatched"] = {"date": today(), "text": note or None}
            msg = f"dispatched {args.id} ({today()})"
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
    view = {"dispatchable": [], "held": [], "dispatched": [], "unapproved": 0, "unreadable": list(ws.errors)}
    for s in ws.stores:
        for it in s.items:
            if repo and it.get("repo") != repo:
                continue
            if it.get("kind") == VOCAB.role("report_kind"):
                continue  # its work lives in the owner's store, under the counterpart's id
            appr = it.get("approved")
            if appr is None:
                view["unapproved"] += 1
                continue
            gid = tagging.global_id(it["id"])
            if it.get("dispatched"):
                d = it["dispatched"]
                view["dispatched"].append({"id": gid, "date": d.get("date") if isinstance(d, dict) else None,
                                           "text": d.get("text") if isinstance(d, dict) else None})
                continue
            if not checks.approved_ok(appr):
                view["held"].append({"id": gid, "why": ["approved is malformed (todo check names it)"]})
                continue
            if it.get("size") == VOCAB.split_size and checks.children_of(ws, it["id"]):
                continue  # split: its children carry the approval and the work
            why = not_ready_reasons(ws, it)
            if why:
                view["held"].append({"id": gid, "why": why})
                continue
            view["dispatchable"].append({"id": gid, "repo": it["repo"], "work": it["work"], "size": it["size"],
                                         "title": it["title"], "approved": appr, "store": str(s.dir),
                                         "brief": f"todo brief {gid}",
                                         "mark": f"todo -C {s.dir} dispatch {it['id']}"})
    return view


def cmd_dispatchable(args):
    view = dispatch_view(read_workspace(args), args.repo)
    if args.json:
        print(json.dumps(view, indent=1, ensure_ascii=False))
    else:
        for r in view["dispatchable"]:
            print(f"{r['id']:<11} repo {r['repo']:<16} work {r['work']:<9} size {r['size']}  "
                  f"approved {r['approved']['date']}  {r['title'][:TITLE_WIDTH]}")
            print(f"{'':<11} brief: {r['brief']}   mark it handed out: {r['mark']}")
        if not view["dispatchable"]:
            print("(nothing dispatchable: an item needs Jacob's approval (todo approve), no dispatched mark, and "
                  "what todo brief needs: status open, repo, work, done_when, size "
                  f"{' or '.join(VOCAB.ready_sizes)}, every blocked_by id closed)")
        if view["held"]:
            print(f"approved, held back ({len(view['held'])}):")
            for h in view["held"]:
                print(f"  {h['id']:<11} {'; '.join(h['why'])}")
        if view["dispatched"]:
            print(f"approved, already dispatched ({len(view['dispatched'])}): "
                  + ", ".join(f"{d['id']} ({d['date']})" for d in view["dispatched"]))
        print(f"({view['unapproved']} open item(s) carry no approval)")
        for e in view["unreadable"]:
            print(f"UNREADABLE  {e}")
    if view["unreadable"]:
        print("todo: UNCHECKED: a store could not be read, so this list may be missing its items", file=sys.stderr)
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


def cmd_stale_plans(args):
    view = stale_plans_view(read_workspace(args), args)
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
    print("Approved: " + (field_value("approved", it["approved"]) if it.get("approved") else
                          f"no (todo approve {it['id']} --source ...)"))
    if it.get("dispatched"):
        print(f"Dispatched: {field_value('dispatched', it['dispatched'])}")
    print(handoff_line(it, work_dir(ws, s, it)))
    todo_bin = Path(sys.argv[0]).resolve()
    print(f"Hand off at each checkpoint: {todo_bin} -C {s.dir} edit {it['id']} --handoff \"done; next; how to verify\"")
    print(f"Close it: {todo_bin} -C {s.dir} done {it['id']} --resolution \"...\"")
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
    "repos": (cmd_repos, "every store the scan finds"),
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
    "stale-plans": (cmd_stale_plans, "open items whose plan section changed, is gone, or was never pinned"),
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
    p.add_argument("--repo")
    p.add_argument("--work", choices=list(VOCAB.works) + ([""] if editing else []))
    p.add_argument("--size", choices=list(VOCAB.sizes) + ([""] if editing else []),
                   help=f"the estimate; {VOCAB.split_size} is split before it is started (todo split)")
    p.add_argument("--files", nargs="*")
    p.add_argument("--done-when", dest="done_when")
    p.add_argument("--retire")
    p.add_argument("--tags", nargs="*", metavar="TAG",
                   help="plan:, origin:, trust: and ref: tags (the rest derive from the fields); no tags clears them")
    if editing:
        p.add_argument("--title")
        p.add_argument("--append-evidence", dest="append_evidence", metavar="E",
                       help="add E as a new line after the evidence, under the store's lock (not with --evidence)")
        p.add_argument("--handoff", metavar="NOTE",
                       help="at a checkpoint: 'done; next; how to verify', kept with today's date and the work "
                            "repo's commit; replaces the last one, \"\" clears it")


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
    ps["done"].add_argument("--resolution", required=True)
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
    ps["show"].add_argument("id")
    ps["render"].add_argument("--all", action="store_true")
    ps["render"].add_argument("--history", action="store_true")
    ps["render"].add_argument("--force", action="store_true")
    ps["tree"].add_argument("id", nargs="?")
    ps["check"].add_argument("--all", action="store_true")
    ps["import"].add_argument("file")
    ps["import"].add_argument("--dry-run", action="store_true")
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
    ps["dispatch"].add_argument("id")
    ps["dispatch"].add_argument("--note", help="one line, e.g. where the Dispatch line is; never who")
    ps["dispatch"].add_argument("--clear", action="store_true", help="it came back unfinished: list it again")
    ps["dispatchable"].add_argument("--repo", help="only items whose work lives in this repo")
    ps["dispatchable"].add_argument("--json", action="store_true")
    ps["stale-plans"].add_argument("--repo", help="only items whose work lives in this repo")
    ps["stale-plans"].add_argument("--json", action="store_true")
    for name in ("add", "edit", "stale-plans"):
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
    except TodoError as e:
        print(f"todo: {e}", file=sys.stderr)
        return 1
    return 0
