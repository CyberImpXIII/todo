"""The move to todo.db (PLAN-todo-tool.md §10.6): the store helper (todolib/sqlstore.py),
todo's schema and its exports (todolib/migrate.py), the readers inventory
(todolib/readers.py), and `todo migrate`, which today only dry-runs."""
import json
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, Case
from todolib import migrate, sqlstore
from todolib.store import HISTORY_FILE, RECORDS_FILE, STORE_FILE, Store, dump, sealed, write_atomic

PEOPLE = [["CREATE TABLE person (id INTEGER PRIMARY KEY, name TEXT NOT NULL, tags TEXT)"],
          ["CREATE TABLE pet (id INTEGER PRIMARY KEY, owner INTEGER NOT NULL REFERENCES person (id))"]]
PERSON = sqlstore.ExportSpec("person", "person.jsonl", ["name"], ["tags"])


class TmpDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="todo-sql-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        for p in self.tmp.rglob("*"):
            if p.is_file():
                os.chmod(p, 0o644)
        self._tmp.cleanup()


class Helper(TmpDir):
    """The generic store helper: WAL, foreign keys, user_version, transactions, exports."""

    def db(self, migrations=PEOPLE, name="s.db"):
        return sqlstore.Db(self.tmp / name, migrations)

    def test_opens_with_wal_and_foreign_keys_on(self):
        with self.db() as db:
            self.assertEqual(db.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(db.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                with db.transaction():
                    db.conn.execute("INSERT INTO pet (id, owner) VALUES (1, 99)")

    def test_user_version_steps_one_migration_at_a_time_and_a_failed_one_rolls_back(self):
        with self.db(PEOPLE[:1]) as db:
            self.assertEqual(db.version, 1)
        broken = PEOPLE + [["CREATE TABLE vet (id INTEGER PRIMARY KEY)", "CREATE TABLE nonsense ("]]
        with self.assertRaises(sqlite3.OperationalError):
            self.db(broken)
        with self.db(PEOPLE) as db:
            self.assertEqual(db.version, 2, "the second migration stands, the failed third does not")
            tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertEqual(tables, {"person", "pet"}, "nothing of the failed migration is left")

    def test_a_store_newer_than_the_code_is_refused(self):
        self.db().close()
        with self.assertRaisesRegex(sqlstore.StoreError, "newer than this code"):
            self.db(PEOPLE[:1])

    def test_a_write_that_fails_rolls_back(self):
        with self.db() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                with db.transaction():
                    db.insert(PERSON, [{"id": 1, "name": "a", "tags": None}])
                    db.insert(PERSON, [{"id": 1, "name": "b", "tags": None}])
            self.assertEqual(db.rows(PERSON), [])

    def test_the_export_is_sorted_deterministic_headed_and_read_only(self):
        with self.db() as db:
            with db.transaction():
                db.insert(PERSON, [{"id": 1, "name": "c", "tags": {"z": 1, "a": [2]}},
                                   {"id": 2, "name": "a", "tags": None}, {"id": 3, "name": "b", "tags": ["x"]}])
            text = db.export(PERSON, "the producer")
            self.assertEqual(text, db.export(PERSON, "the producer"), "the same rows give the same bytes")
            header, *lines = text.splitlines()
            self.assertEqual([json.loads(ln)["id"] for ln in lines], [2, 3, 1], "sorted by the key, not by rowid")
            self.assertEqual(lines[2], '{"id":1,"name":"c","tags":{"a":[2],"z":1}}', "keys sorted, JSON shown as JSON")
            head = json.loads(header)
            self.assertEqual({k: head[k] for k in ("export", "producer", "store", "user_version", "rows")},
                             {"export": "person", "producer": "the producer", "store": "s.db", "user_version": 2, "rows": 3})
            sizes = db.write_exports(self.tmp, [PERSON], "the producer")
            self.assertEqual(sizes, {"person.jsonl": len(text.encode())})
            self.assertEqual((self.tmp / "person.jsonl").stat().st_mode & 0o777, 0o444)
            self.assertEqual(db.verify_exports(self.tmp, [PERSON], "the producer"), [])

    def test_an_edited_export_is_refused_and_listed(self):
        with self.db() as db:
            with db.transaction():
                db.insert(PERSON, [{"id": 1, "name": "a", "tags": None}])
            db.write_exports(self.tmp, [PERSON], "p")
        path = self.tmp / "person.jsonl"
        os.chmod(path, 0o644)
        path.write_text(path.read_text().replace('"a"', '"z"'))
        with self.db(name="fresh.db") as fresh:
            with self.assertRaisesRegex(sqlstore.StoreError, "edited by hand"):
                fresh.import_exports(self.tmp, [PERSON])
            self.assertEqual(fresh.rows(PERSON), [])
        with self.db() as db:
            problems = db.verify_exports(self.tmp, [PERSON], "p")
        self.assertEqual(problems, ["person.jsonl: writable (mode 0644); an export sits at 0444",
                                    "person.jsonl: its seal does not match its lines: edited by hand"])

    def test_an_export_behind_the_store_is_listed(self):
        with self.db() as db:
            db.write_exports(self.tmp, [PERSON], "p")
            with db.transaction():
                db.insert(PERSON, [{"id": 1, "name": "a", "tags": None}])
            self.assertEqual(db.verify_exports(self.tmp, [PERSON], "p"), ["person.jsonl: differs from the store s.db"])

    def test_the_helper_holds_nothing_of_this_tool(self):
        """Setup lifts it as the shared helper (PLAN-services.md §3 ST6): it imports
        nothing from this package and names none of this tool's files."""
        src = (ROOT / "todolib" / "sqlstore.py").read_text()
        self.assertNotRegex(src, r"(?m)^\s*(from \.|import todolib|from todolib)")
        for word in ("todo", STORE_FILE, HISTORY_FILE, RECORDS_FILE, "VOCAB"):
            self.assertNotIn(word, src)

    def test_only_the_helper_opens_a_database(self):
        hits = [f.name for f in sorted((ROOT / "todolib").glob("*.py"))
                if f.name != "sqlstore.py" and re.search(r"\bsqlite3\b", f.read_text())]
        self.assertEqual(hits, [])


class Schema(TmpDir):
    def test_history_refuses_update_and_delete(self):
        with migrate.open_db(self.tmp / migrate.DB_FILE) as db:
            with db.transaction():
                db.insert(migrate.SPEC["history"], [{"seq": 0, "id": "a-1", "body": {"id": "a-1", "title": "t"}}])
            for statement in ("UPDATE history SET body = '{\"id\": \"a-1\"}'", "DELETE FROM history"):
                with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                    with db.transaction():
                        db.conn.execute(statement)
            self.assertEqual([r["body"]["title"] for r in db.rows(migrate.SPEC["history"])], ["t"])

    def test_the_schema_refuses_an_item_filed_under_another_id(self):
        with migrate.open_db(self.tmp / migrate.DB_FILE) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                with db.transaction():
                    db.insert(migrate.SPEC["items"], [{"seq": 0, "id": "a-1", "body": {"id": "a-2"}}])

    def test_differences_names_the_record(self):
        want = {STORE_FILE: {"repo": "a", "items": [{"id": "a-1", "title": "x"}, {"id": "a-2", "title": "y"}]}}
        got = {STORE_FILE: {"repo": "a", "items": [{"id": "a-1", "title": "x"}, {"id": "a-2", "title": "Y"}]}}
        self.assertEqual(migrate.differences(want, want), [])
        self.assertEqual(migrate.differences(want, got), [f"{STORE_FILE} items[1] a-2: differs after the round trip"])
        self.assertEqual(migrate.differences(want, {}), [f"{STORE_FILE}: missing after the round trip"])


class Migrate(Case):
    def a_store(self, name="a", prefix="aa"):
        d = self.repo(name, prefix)
        self.todo("-C", d, "add", "first", "--kind", "bug", "--evidence", "ran x, saw y")
        self.todo("-C", d, "add", "second ü", "--kind", "bug", "--evidence", "ran x, saw z")
        self.todo("-C", d, "done", f"{prefix}-1", "--resolution", "fixed")
        records = sealed({"format": 2, "repo": name, "tables": [{"id": "dt-1", "rows": [{"n": 1}]}],
                          "runs": {"S7": {"ok": True, "at": "2026-10-04T00:00"}}})
        write_atomic(d / RECORDS_FILE, dump(records), readonly=True)
        return d

    def snapshot(self):
        return {str(p.relative_to(self.ws)): (p.read_bytes(), p.stat().st_mode)
                for p in sorted(self.ws.rglob("*")) if p.is_file()}

    def test_the_exports_alone_give_back_every_record(self):
        """A fresh clone has only the exports: a todo.db made from them, with the
        first one removed, holds the JSON files record for record."""
        d = self.a_store()
        store = Store(d).load()
        want = migrate.documents(store)
        self.assertEqual(sorted(want), sorted([STORE_FILE, HISTORY_FILE, RECORDS_FILE]))
        out = self.tmp / "out"
        out.mkdir()
        with migrate.open_db(out / migrate.DB_FILE) as db:
            migrate.import_documents(db, want)
            db.write_exports(out, migrate.EXPORTS, migrate.PRODUCER)
        for p in out.glob(migrate.DB_FILE + "*"):
            p.unlink()
        with migrate.open_db(out / migrate.DB_FILE) as db:
            db.import_exports(out, migrate.EXPORTS)
            got = migrate.rebuild(db)
            self.assertEqual(db.verify_exports(out, migrate.EXPORTS, migrate.PRODUCER), [])
        self.assertEqual(migrate.differences(want, got), [])
        self.assertEqual([it["title"] for it in got[STORE_FILE]["items"]], ["second ü"])
        self.assertEqual([it["id"] for it in got[HISTORY_FILE]["items"]], ["aa-1"])
        self.assertEqual(got[RECORDS_FILE]["runs"], {"S7": {"ok": True, "at": "2026-10-04T00:00"}})

    def test_the_dry_run_says_per_repo_and_writes_nothing(self):
        self.a_store("a", "aa")
        b = self.repo("b", "bb")
        self.todo("-C", b, "add", "an item", "--kind", "bug", "--evidence", "e")
        os.chmod(b / STORE_FILE, 0o644)
        (b / STORE_FILE).write_text((b / STORE_FILE).read_text().replace("an item", "a hand edit"))
        tmpdir = self.tmp / "throwaway"
        tmpdir.mkdir()
        before = self.snapshot()
        r = self.todo("-C", self.ws / "a", "migrate", "--dry-run", "--all", ok=False, env={"TMPDIR": str(tmpdir)})
        self.assertEqual(r.returncode, 1, r.stderr)
        rows = {ln.split()[1]: ln for ln in r.stdout.splitlines() if ln.startswith("  ")}
        self.assertTrue(rows["a"].startswith("  ok "), r.stdout)
        self.assertIn("1 open, 1 closed, 1 tables, 1 runs", rows["a"])
        self.assertTrue(rows["b"].startswith("  NOT "), r.stdout)
        self.assertIn("changed around the CLI (seal)", rows["b"])
        self.assertIn("dry run: 1 of 2 stores would not migrate", r.stderr)
        self.assertEqual(self.snapshot(), before, "a dry run writes nothing in any repo")
        self.assertEqual(list(tmpdir.iterdir()), [], "the throwaway todo.db is removed")
        one = self.todo("-C", self.ws / "a", "migrate", "--dry-run", "--json").stdout
        doc = json.loads(one)
        self.assertEqual((doc["ok"], [x["repo"] for x in doc["repos"]]), (True, ["a"]))
        self.assertEqual(sorted(doc["repos"][0]["exports"]), sorted(s.file for s in migrate.EXPORTS))

    def test_readers_lists_code_not_prose_hidden_folders_or_the_store(self):
        d = self.a_store()
        (d / "tool.sh").write_text("#!/bin/sh\njq . todo.json\n")
        (d / "notes.md").write_text("todo.json is the store\n")
        (d / "other.json.txt").write_text("mytodo.json is not it\n")
        (self.ws / ".hidden").mkdir()
        (self.ws / ".hidden" / "x.sh").write_text("cat todo-history.json\n")
        doc = json.loads(self.todo("-C", d, "migrate", "--readers", "--json").stdout)
        self.assertEqual([(h["path"], h["line"], h["text"]) for h in doc["hits"]], [("a/tool.sh", 2, "jq . todo.json")])
        out = self.todo("-C", d, "migrate", "--readers").stdout
        self.assertIn("1 lines in 1 files outside this tool name", out)


if __name__ == "__main__":
    unittest.main()
