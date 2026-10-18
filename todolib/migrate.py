"""`todo migrate` (PLAN-todo-tool.md §10.6, PLAN-services.md §4 step 10.1): the
move of a repo's store from its JSON files to `todo.db`, one SQLite file.

Today only the dry run exists. For one loaded store, `dry_run` imports its three
JSON files into a `todo.db` in a throwaway folder, writes the four static exports
beside it, imports those exports into a second, fresh `todo.db` (what a fresh
clone does), and rebuilds the JSON files' content from each database. Both
rebuilds must equal the files as loaded, record for record, or the repo is
reported "not", with the first difference. Nothing is written in the repo.

The real conversion waits on two things, and `todo migrate` without --dry-run
refuses until then: the store reading todo.db (store.py reads the JSON files
only), and no reader outside this tool naming the JSON files by path
(`readers.scan`, `todo migrate --readers`).

The schema, version 1: one table per file's records, and `meta` for each file's
header keys:
- `items`, the open items (todo.json `items`), in file order (`seq`);
- `history`, the closed items (todo-history.json `items`), append-only in the
  schema itself: a trigger refuses UPDATE and DELETE;
- `records`, todo-records.json's `tables` (in order) and `runs` (by detector);
- `meta`, every other key of each file except its seal, in file order.
"""
import tempfile
from pathlib import Path

from .sqlstore import Db, ExportSpec, StoreError, canonical
from .store import HISTORY_FILE, RECORDS_FILE, SEAL_KEY, STORE_FILE, TodoError

DB_FILE = "todo.db"
PRODUCER = "todo migrate"
ITEMS_KEY = "items"
TABLES_KEY = "tables"
RUNS_KEY = "runs"
# The keys of each file whose values are rows of a table, not header keys.
BODY_KEYS = {STORE_FILE: [ITEMS_KEY], HISTORY_FILE: [ITEMS_KEY], RECORDS_FILE: [TABLES_KEY, RUNS_KEY]}
FILES = [STORE_FILE, HISTORY_FILE, RECORDS_FILE]
_FILE_IN = ", ".join(f"'{f}'" for f in FILES)

MIGRATIONS = [
    [
        "CREATE TABLE meta (file TEXT NOT NULL CHECK (file IN (" + _FILE_IN + ")), seq INTEGER NOT NULL, "
        "key TEXT NOT NULL, value TEXT NOT NULL CHECK (json_valid(value)), PRIMARY KEY (file, key), UNIQUE (file, seq))",
        "CREATE TABLE items (id TEXT PRIMARY KEY, seq INTEGER NOT NULL UNIQUE, "
        "body TEXT NOT NULL CHECK (json_valid(body) AND json_extract(body, '$.id') IS id))",
        "CREATE TABLE history (seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, "
        "body TEXT NOT NULL CHECK (json_valid(body) AND json_extract(body, '$.id') IS id))",
        "CREATE TRIGGER history_no_update BEFORE UPDATE ON history "
        "BEGIN SELECT RAISE(ABORT, 'history is append-only: no UPDATE'); END",
        "CREATE TRIGGER history_no_delete BEFORE DELETE ON history "
        "BEGIN SELECT RAISE(ABORT, 'history is append-only: no DELETE'); END",
        "CREATE TABLE records (section TEXT NOT NULL CHECK (section IN ('" + TABLES_KEY + "', '" + RUNS_KEY + "')), "
        "seq INTEGER NOT NULL, key TEXT, body TEXT NOT NULL CHECK (json_valid(body)), PRIMARY KEY (section, seq), "
        "UNIQUE (section, key))",
    ],
]

EXPORTS = [
    ExportSpec("meta", "todo.meta.jsonl", ["file", "seq"], ["value"]),
    ExportSpec("items", "todo.items.jsonl", ["seq"], ["body"]),
    ExportSpec("history", "todo.history.jsonl", ["seq"], ["body"]),
    ExportSpec("records", "todo.records.jsonl", ["section", "seq"], ["body"]),
]
SPEC = {s.table: s for s in EXPORTS}


def open_db(path):
    return Db(path, MIGRATIONS)


def documents(store):
    """{file: its content as loaded, seal left out} for each file the store has."""
    docs = {STORE_FILE: store.data, HISTORY_FILE: store.history, RECORDS_FILE: store.records}
    return {f: {k: v for k, v in d.items() if k != SEAL_KEY} for f, d in docs.items() if d is not None}


def import_documents(db, docs):
    """The files' content into an empty db, in one transaction."""
    meta, items, history, records = [], [], [], []
    for file, doc in docs.items():
        if not isinstance(doc, dict):
            raise TodoError(f"{file}: not a JSON object")
        for n, (k, v) in enumerate((k, v) for k, v in doc.items() if k not in BODY_KEYS[file]):
            meta.append({"file": file, "seq": n, "key": k, "value": v})
    for n, it in enumerate(docs[STORE_FILE].get(ITEMS_KEY, [])):
        items.append({"id": it.get("id"), "seq": n, "body": it})
    for n, it in enumerate(docs.get(HISTORY_FILE, {}).get(ITEMS_KEY, [])):
        history.append({"id": it.get("id"), "seq": n, "body": it})
    rec = docs.get(RECORDS_FILE, {})
    for n, t in enumerate(rec.get(TABLES_KEY, [])):
        records.append({"section": TABLES_KEY, "seq": n, "key": None, "body": t})
    for n, (k, v) in enumerate(rec.get(RUNS_KEY, {}).items()):
        records.append({"section": RUNS_KEY, "seq": n, "key": k, "body": v})
    with db.transaction():
        for table, rows in (("meta", meta), ("items", items), ("history", history), ("records", records)):
            db.insert(SPEC[table], rows)


def rebuild(db):
    """The files' content back out of a db: {file: content, seal left out}. A
    file is present when it has a header key or a row."""
    docs = {}
    for r in db.rows(SPEC["meta"]):
        docs.setdefault(r["file"], {})[r["key"]] = r["value"]
    items = [r["body"] for r in db.rows(SPEC["items"])]
    history = [r["body"] for r in db.rows(SPEC["history"])]
    recs = db.rows(SPEC["records"])
    if STORE_FILE in docs or items:
        docs.setdefault(STORE_FILE, {})[ITEMS_KEY] = items
    if HISTORY_FILE in docs or history:
        docs.setdefault(HISTORY_FILE, {})[ITEMS_KEY] = history
    if RECORDS_FILE in docs or recs:
        r = docs.setdefault(RECORDS_FILE, {})
        r[TABLES_KEY] = [x["body"] for x in recs if x["section"] == TABLES_KEY]
        r[RUNS_KEY] = {x["key"]: x["body"] for x in recs if x["section"] == RUNS_KEY}
    return docs


def differences(want, got):
    """Record for record, the first few ways got differs from want; [] when equal.
    Values compare canonically (key order aside), as the seal does."""
    out = []
    for file in sorted(set(want) | set(got)):
        a, b = want.get(file), got.get(file)
        if a is None or b is None:
            out.append(f"{file}: {'missing' if b is None else 'not in the JSON'} after the round trip")
            continue
        for key in sorted(set(a) | set(b)):
            va, vb = a.get(key), b.get(key)
            if isinstance(va, list) and isinstance(vb, list):
                if len(va) != len(vb):
                    out.append(f"{file} {key}: {len(va)} records, {len(vb)} after the round trip")
                for n, (x, y) in enumerate(zip(va, vb)):
                    if canonical(x) != canonical(y):
                        ident = x.get("id") if isinstance(x, dict) else None
                        out.append(f"{file} {key}[{n}]{' ' + ident if ident else ''}: differs after the round trip")
            elif key not in a or key not in b or canonical(va) != canonical(vb):
                out.append(f"{file} {key}: differs after the round trip")
    return out[:5]


def counts(docs):
    rec = docs.get(RECORDS_FILE, {})
    return {"open_items": len(docs[STORE_FILE].get(ITEMS_KEY, [])),
            "closed_items": len(docs.get(HISTORY_FILE, {}).get(ITEMS_KEY, [])),
            TABLES_KEY: len(rec.get(TABLES_KEY, [])), RUNS_KEY: len(rec.get(RUNS_KEY, {}))}


def dry_run(store):
    """One loaded store's dry run: {repo, dir, ok, why, counts, exports}. Writes
    only inside a throwaway folder, removed before it returns."""
    out = {"repo": store.repo, "dir": str(store.dir), "ok": False, "why": None, "counts": None, "exports": None}
    if store.history is None:
        out["why"] = f"no {HISTORY_FILE}: a store without its history is never migrated"
        return out
    unsealed = store.unsealed()
    if unsealed:
        out["why"] = (f"{', '.join(unsealed)} changed around the CLI (seal): migrating would carry a hand edit "
                      "into todo.db; restore it or `todo reseal` first")
        return out
    want = documents(store)
    out["counts"] = counts(want)
    try:
        with tempfile.TemporaryDirectory(prefix="todo-migrate-") as tmp:
            first, fresh = Path(tmp) / "first", Path(tmp) / "fresh"
            first.mkdir()
            fresh.mkdir()
            with open_db(first / DB_FILE) as db:
                import_documents(db, want)
                problems = differences(want, rebuild(db))
                if problems:
                    out["why"] = "todo.db does not hold the JSON: " + "; ".join(problems)
                    return out
                out["exports"] = db.write_exports(first, EXPORTS, PRODUCER)
                problems = db.verify_exports(first, EXPORTS, PRODUCER)
                if problems:
                    out["why"] = "the exports do not stand: " + "; ".join(problems)
                    return out
            with open_db(fresh / DB_FILE) as db:
                db.import_exports(first, EXPORTS)
                problems = differences(want, rebuild(db))
                if problems:
                    out["why"] = "a todo.db made from the exports does not hold the JSON: " + "; ".join(problems)
                    return out
    except (StoreError, TodoError) as e:
        out["why"] = str(e)
        return out
    except Exception as e:  # a constraint the JSON breaks: the database refused it
        out["why"] = f"todo.db refused the JSON: {type(e).__name__}: {e}"
        return out
    out["ok"] = True
    return out


def line(r):
    if not r["ok"]:
        return f"  NOT   {r['repo']:<20} {r['why']}"
    c = r["counts"]
    size = sum(r["exports"].values())
    return (f"  ok    {r['repo']:<20} {c['open_items']} open, {c['closed_items']} closed, {c[TABLES_KEY]} tables, "
            f"{c[RUNS_KEY]} runs: into {DB_FILE} and {len(r['exports'])} exports ({size} bytes), and back, record for record")
