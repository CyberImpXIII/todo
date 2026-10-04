"""The todo CLI: the only way into a store. `todo --help` lists the commands;
README.md documents each one, and tests/test_docs.py holds the two equal."""
import argparse
import difflib
import os
import sys
from pathlib import Path

from . import checks, importer
from .render import render_history, render_item, render_store, history_order
from .store import (HISTORY_RENDER_FILE, Store, TodoError, Workspace, add_days, id_number,
                    never_scanned, new_item, scan_root, store_dir_for, today, write_atomic)
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
    missing = [f for f in VOCAB.required(item) if item.get(f) in (None, "", [])]
    if missing:
        flags = ", ".join("--" + f.replace("_", "-") for f in missing)
        raise TodoError(f"a {item['kind']} that is {item['status']} needs {flags}")


def resolve_parent(ws, parent):
    if parent and ws.find(parent)[0] is None:
        raise TodoError(f"parent {parent} resolves in no scanned store or history (todo repos lists them)")


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
        if isinstance(v, dict):
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
                        repo=args.repo or store.repo, work=args.work, files=args.files,
                        done_when=args.done_when, retire=args.retire, added=today())
        if item["status"] == VOCAB.closed:
            raise TodoError("add makes open items; close one with todo done")
        validate(item)
        item["id"] = store.allocate()
        store.items.append(item)
        commit(store)
    print(f"added {item['id']}: {item['title']}")


EDITABLE = ["title", "kind", "status", "evidence", "probe", "parent", "repo", "work", "files",
            "done_when", "retire"]


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
        if not changes:
            raise TodoError("nothing to change: name at least one field")
        if changes.get("status") == VOCAB.closed:
            raise TodoError("close an item with `todo done ID --resolution ...`")
        updated = dict(item)
        for f, v in changes.items():
            updated[f] = None if v in ("", []) else v
        validate(updated)
        if "parent" in changes:
            resolve_parent(workspace(args, store), updated["parent"])
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
        closed = dict(item, status=VOCAB.closed, done=today(), resolution=args.resolution)
        validate(closed, "history")
        store.history["items"].append(closed)
        store.items.remove(item)
        commit(store)
    print(f"closed {args.id}, moved to {store.history_path.name}")


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
            print(one_line(it))
            n += 1
    if n == 0:
        print("(no open items match)")


def cmd_show(args):
    store = open_store(args)
    ws = workspace(args, store)
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
                if state in ("hand-edited", "hand-written") and not args.force:
                    raise TodoError(f"{s.render_path} is {state}: `todo import TODO.md` first, or --force to keep the diff in todo.json and rewrite it")
                if state in ("hand-edited", "hand-written"):
                    require_history(s)
                    old = s.render_path.read_text().splitlines()
                    diff = "\n".join(difflib.unified_diff(render_store(s).splitlines(), old, "render", "TODO.md", lineterm=""))
                    s.data["hand_edits"].append({"date": today(), "via": "render --force",
                                                 "diff": diff[:HAND_EDIT_DIFF_MAX]})
                    s.save()
                write_render(s)
                print(f"  {state if state != 'clean' else 'unchanged':<10} {s.render_path}" + (" (diff kept in todo.json hand_edits)" if args.force and state != "clean" else ""))
        except TodoError as e:
            failed += 1
            print(f"  REFUSED   {e}")
    if failed:
        sys.exit(1)


def cmd_tree(args):
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


def ready_items(ws, repo=None, work=None):
    for s in ws.stores:
        for it in s.items:
            if it.get("status") != VOCAB.role("default_status") or it.get("kind") == VOCAB.role("report_kind"):
                continue
            if not (it.get("repo") and it.get("work") and it.get("done_when")):
                continue
            if (repo and it["repo"] != repo) or (work and it["work"] != work):
                continue
            yield it, s


def cmd_ready(args):
    store = open_store(args)
    n = 0
    for it, _ in ready_items(workspace(args, store), args.repo, args.work):
        print(f"{it['id']:<8} {it['repo']:<20} {it['work']:<9} {it['title'][:TITLE_WIDTH]}")
        n += 1
    if n == 0:
        print("(nothing ready: an open item needs repo, work and done_when set)")


def cmd_brief(args):
    store = open_store(args)
    ws = workspace(args, store)
    it, where, s = ws.find(args.id)
    if it is None:
        raise TodoError(f"{args.id} is in no scanned store or history")
    if where == "history":
        raise TodoError(f"{args.id} closed {it.get('done') or '(undated)'}: {it.get('resolution') or ''}")
    missing = [f for f in ("repo", "work", "done_when") if not it.get(f)]
    print(f"todo:{it['id']}  ({it.get('kind')}, {it.get('status')}; repo {it.get('repo')}, work {it.get('work')})")
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
    todo_bin = Path(sys.argv[0]).resolve()
    print(f"Close it: {todo_bin} -C {s.dir} done {it['id']} --resolution \"...\"")
    if missing or it.get("status") != VOCAB.role("default_status"):
        why = (f"missing {', '.join(missing)}" if missing else "") + \
              (f"{'; ' if missing else ''}status {it.get('status')}" if it.get("status") != VOCAB.role("default_status") else "")
        print(f"NOT READY: {why}")
        sys.exit(1)


def cmd_history(args):
    store = open_store(args)
    ws = workspace(args, store)
    if args.id:
        it, where, s = ws.find(args.id)
        if it is None or where != "history":
            raise TodoError(f"{args.id} is not in any scanned history" + (" (it is still open: todo show)" if it else ""))
        print_item(it, where, s, ws)
        return
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
}


def add_item_fields(p, editing):
    p.add_argument("--kind", choices=list(VOCAB.kinds), required=not editing)
    p.add_argument("--status", choices=list(VOCAB.statuses))
    p.add_argument("--evidence")
    p.add_argument("--probe")
    p.add_argument("--parent")
    p.add_argument("--repo")
    p.add_argument("--work", choices=list(VOCAB.works) + ([""] if editing else []))
    p.add_argument("--files", nargs="*")
    p.add_argument("--done-when", dest="done_when")
    p.add_argument("--retire")
    if editing:
        p.add_argument("--title")


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
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.command:
        ap.print_help()
        return 0
    try:
        COMMANDS[args.command][0](args)
    except TodoError as e:
        print(f"todo: {e}", file=sys.stderr)
        return 1
    return 0
