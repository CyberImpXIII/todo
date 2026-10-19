"""The store on todo.db (PLAN-todo-tool.md §10.6, PLAN-services.md §4 step 10.1):
`todo migrate` moves a store only while no reader names the JSON files and git
ignores todo.db; every write then rewrites the four committed exports, sealed and
0444; a fresh clone's todo.db is made from them; `todo check` fails an export
edited by hand, one todo.db does not match, and a todo.db git would track; a
move cut off midway is refused, then finished; history stays append-only; and
every module of the CLI imports on its own (the CLI other sessions run from this
checkout must import at every commit)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, Case, git_commit
from todolib import migrate
from todolib.store import (DB_FILE, EXPORT_FILES, HISTORY_FILE, RECORDS_FILE, STORE_FILE, Store, TodoError, dump,
                           sealed, write_atomic)

JSON_FILES = (STORE_FILE, HISTORY_FILE, RECORDS_FILE)
IGNORE = f"{DB_FILE}\n{DB_FILE}-*\n"


def mode(path):
    return os.stat(path).st_mode & 0o777


class OnDb(Case):
    def a_store(self, name="a", prefix="aa", ignore=True):
        d = self.repo(name, prefix)
        if ignore:
            (d / ".gitignore").write_text(IGNORE)
        self.todo("-C", d, "add", "first", "--kind", "bug", "--evidence", "ran x, saw y")
        self.todo("-C", d, "add", "second ü", "--kind", "bug", "--evidence", "ran x, saw z")
        self.todo("-C", d, "done", f"{prefix}-1", "--resolution", "fixed")
        table = {"id": "dt-1", "date": "2026-10-04", "supersedes": [], "answers": [],
                 "rows": [{"n": 1, "item": f"{prefix}-2", "repo": name, "status": "open", "cells": ["a", "b", "ü"]}]}
        records = sealed({"format": 2, "repo": name, "tables": [table], "runs": {}})
        write_atomic(d / RECORDS_FILE, dump(records), readonly=True)
        git_commit(d, "the store on JSON")
        return d

    def moved(self, name="a", prefix="aa"):
        d = self.a_store(name, prefix)
        self.todo("-C", d, "migrate")
        return d

    def snapshot(self):
        return {str(p.relative_to(self.ws)): (p.read_bytes(), mode(p))
                for p in sorted(self.ws.rglob("*")) if p.is_file() and ".git" not in p.parts}

    def exports(self, d):
        return {f: (d / f).read_bytes() for f in EXPORT_FILES.values()}

    def views(self, d):
        """What a reader of the store sees, through the CLI."""
        return (self.todo("-C", d, "list").stdout, self.todo("-C", d, "history").stdout,
                self.todo("-C", d, "show", "aa-1").stdout.replace(EXPORT_FILES["history"], "HISTORY"))

    def hand_write(self, path, text):
        os.chmod(path, 0o644)
        path.write_text(text)
        os.chmod(path, 0o444)


class Move(OnDb):
    def test_migrate_moves_the_store_record_for_record_and_the_json_goes(self):
        d = self.a_store()
        before = Store(d).load()
        want = migrate.documents(before)
        r = self.todo("-C", d, "migrate")
        self.assertIn(f"moved a to {DB_FILE}: 1 open, 1 closed", r.stdout)
        self.assertEqual([f for f in JSON_FILES if (d / f).exists()], [], "the JSON files go")
        self.assertTrue((d / DB_FILE).is_file())
        self.assertEqual({f: mode(d / f) for f in EXPORT_FILES.values()}, {f: 0o444 for f in EXPORT_FILES.values()})
        after = Store(d).load()
        self.assertEqual((after.backing, after.unsealed()), ("db", []))
        self.assertEqual(migrate.differences(want, migrate.documents(after)), [])
        self.assertIn("second ü", self.todo("-C", d, "list").stdout)
        self.assertIn(f"closed, in {EXPORT_FILES['history']}", self.todo("-C", d, "show", "aa-1").stdout)
        out = self.check(d).stdout
        self.assertTrue([ln for ln in out.splitlines() if ln.split()[:2] == ["ok", "seal"]], out)

    def test_a_write_rewrites_the_exports_sealed_and_read_only(self):
        d = self.moved()
        old = self.exports(d)
        self.todo("-C", d, "add", "third", "--kind", "bug", "--evidence", "e")
        self.todo("-C", d, "done", "aa-2", "--resolution", "done on todo.db")
        new = self.exports(d)
        self.assertNotEqual(old[EXPORT_FILES["items"]], new[EXPORT_FILES["items"]])
        self.assertIn(b"third", new[EXPORT_FILES["items"]])
        self.assertIn(b"done on todo.db", new[EXPORT_FILES["history"]])
        self.assertTrue(new[EXPORT_FILES["history"]].split(b"\n", 1)[1].startswith(
            old[EXPORT_FILES["history"]].split(b"\n", 1)[1]), "history is appended to")
        self.assertEqual({mode(d / f) for f in EXPORT_FILES.values()}, {0o444})
        self.check(d)

    def test_refused_while_a_reader_names_the_json_files(self):
        d = self.a_store()
        (d / "tool.sh").write_text("#!/bin/sh\njq . todo.json\n")
        before = self.snapshot()
        r = self.todo("-C", d, "migrate", ok=False)
        self.assertIn("not moved: 1 lines in 1 files outside this tool name", r.stderr)
        self.assertEqual(self.snapshot(), before, "a refused move changes nothing")

    def test_refused_while_git_would_track_todo_db(self):
        d = self.a_store(ignore=False)
        before = self.snapshot()
        r = self.todo("-C", d, "migrate", ok=False)
        self.assertIn(f"git would track {DB_FILE}", r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_all_is_a_dry_run_only(self):
        d = self.a_store()
        r = self.todo("-C", d, "migrate", "--all", ok=False)
        self.assertIn("--all goes with --dry-run", r.stderr)
        self.assertTrue((d / STORE_FILE).is_file())

    def test_a_cut_off_move_is_refused_then_finished(self):
        """Cut off after todo.db is in place and before the JSON files go: both
        are there. No command reads either, and `todo migrate` finishes it."""
        d = self.moved()
        subprocess.run(["git", "checkout", "--", *JSON_FILES], cwd=d, check=True, capture_output=True)
        self.assertEqual(Store(d).backend(), "both")
        r = self.todo("-C", d, "list", ok=False)
        self.assertIn("did not finish", r.stderr)
        self.todo("-C", d, "add", "lost?", "--kind", "bug", "--evidence", "e", ok=False)
        self.todo("-C", d, "migrate")
        self.assertEqual([f for f in JSON_FILES if (d / f).exists()], [])
        self.assertIn("second ü", self.todo("-C", d, "list").stdout)
        self.check(d)

    def test_the_dry_run_says_a_moved_store_is_already_on_todo_db(self):
        d = self.moved()
        doc = json.loads(self.todo("-C", d, "migrate", "--dry-run", "--json").stdout)
        self.assertTrue(doc["ok"], doc)
        self.assertTrue(doc["repos"][0].get("on_db"), doc)


class FreshClone(OnDb):
    def test_the_exports_alone_give_back_every_record(self):
        """A clone has the exports and no todo.db: the next command makes it."""
        d = self.moved()
        views, exports = self.views(d), self.exports(d)
        for p in d.glob(DB_FILE + "*"):
            p.unlink()
        self.assertEqual(self.views(d), views)
        self.assertTrue((d / DB_FILE).is_file())
        self.assertEqual(self.exports(d), exports, "reading writes no export")
        self.assertEqual([p.name for p in d.iterdir() if ".tmp-" in p.name], [], "no temp database is left")

    def test_export_writes_them_again_byte_for_byte(self):
        """cli.json's regen: `todo export` gives back the committed exports."""
        d = self.moved()
        exports = self.exports(d)
        for f in exports:
            os.chmod(d / f, 0o644)
            (d / f).unlink()
        (d / DB_FILE).touch()  # todo.db stays: a missing export is not a fresh clone
        r = self.todo("-C", d, "export")
        self.assertIn("put back", r.stdout)
        self.assertEqual(self.exports(d), exports)
        self.assertEqual({mode(d / f) for f in exports}, {0o444})

    def test_export_refuses_an_edited_export(self):
        d = self.moved()
        path = d / EXPORT_FILES["items"]
        self.hand_write(path, path.read_text().replace("second", "hand"))
        r = self.todo("-C", d, "export", ok=False)
        self.assertIn("edited by hand", r.stderr)
        self.assertIn("hand", path.read_text(), "the edit is left for its author to see")


class Gates(OnDb):
    def test_check_fails_an_export_edited_by_hand_and_writes_refuse(self):
        d = self.moved()
        path = d / EXPORT_FILES["items"]
        self.hand_write(path, path.read_text().replace("second", "hand"))
        self.assertFails(d, "seal", f"{EXPORT_FILES['items']}: its lines do not match its seal")
        r = self.todo("-C", d, "add", "x", "--kind", "bug", "--evidence", "e", ok=False)
        self.assertIn("edited by hand", r.stderr)

    def test_check_fails_an_export_todo_db_does_not_match(self):
        """A sealed export from another state of todo.db (a pull, a checkout)."""
        d = self.moved()
        old = (d / EXPORT_FILES["items"]).read_text()
        self.todo("-C", d, "add", "third", "--kind", "bug", "--evidence", "e")
        self.hand_write(d / EXPORT_FILES["items"], old)
        self.assertFails(d, "seal", f"{EXPORT_FILES['items']}: sealed, but not what {DB_FILE} holds")
        self.todo("-C", d, "add", "fourth", "--kind", "bug", "--evidence", "e", ok=False)
        self.assertEqual((d / EXPORT_FILES["items"]).read_text(), old, "a stale export is never written over")

    def test_check_fails_a_writable_or_missing_export(self):
        d = self.moved()
        os.chmod(d / EXPORT_FILES["meta"], 0o644)
        self.assertFails(d, "seal", f"{EXPORT_FILES['meta']}: writable")
        os.chmod(d / EXPORT_FILES["meta"], 0o444)
        os.chmod(d / EXPORT_FILES["records"], 0o644)
        (d / EXPORT_FILES["records"]).unlink()
        self.assertFails(d, "seal", f"{EXPORT_FILES['records']}: missing")

    def test_check_fails_a_todo_db_git_would_track(self):
        d = self.moved()
        (d / ".gitignore").write_text("")
        self.assertFails(d, "seal", f"{DB_FILE} is not gitignored")

    def test_check_audits_history_across_the_move(self):
        """The append-only audit reads the history export's git log too."""
        d = self.moved()
        git_commit(d, "moved to todo.db")
        self.check(d)
        path = d / EXPORT_FILES["history"]
        with migrate.open_db(d / DB_FILE) as db:
            db.conn.execute("DROP TRIGGER history_no_delete")
            db.conn.execute("DELETE FROM history")
            db.write_exports(d, migrate.EXPORTS, migrate.PRODUCER)
        self.assertNotIn(b"aa-1", path.read_bytes())
        self.assertFails(d, "history", f"was in {EXPORT_FILES['history']} at")


class AppendOnly(unittest.TestCase):
    def test_a_write_that_changes_or_drops_history_is_refused_whole(self):
        tmp = Path(tempfile.mkdtemp(prefix="todo-db-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        docs = {STORE_FILE: {"format": 2, "repo": "a", "prefix": "aa", "next": 3, "items": [{"id": "aa-2", "title": "t"}]},
                HISTORY_FILE: {"format": 2, "repo": "a", "items": [{"id": "aa-1", "title": "closed"}]}}
        with migrate.open_db(tmp / DB_FILE) as db:
            migrate.store_documents(db, docs, tmp)
            exports = {f: (tmp / f).read_bytes() for f in EXPORT_FILES.values()}
            for change in (lambda d: d[HISTORY_FILE]["items"][0].update(title="rewritten"),
                           lambda d: d[HISTORY_FILE]["items"].clear()):
                with self.subTest(change=change):
                    bad = json.loads(json.dumps(docs))
                    change(bad)
                    bad[STORE_FILE]["items"].append({"id": "aa-3", "title": "new"})
                    with self.assertRaisesRegex(TodoError, "history is append-only"):
                        migrate.store_documents(db, bad, tmp)
                    self.assertEqual(migrate.differences(docs, migrate.rebuild(db)), [], "nothing of it was written")
                    self.assertEqual({f: (tmp / f).read_bytes() for f in EXPORT_FILES.values()}, exports)


class Importable(unittest.TestCase):
    """Other sessions run the CLI from this checkout while it changes: each module
    must import on its own, in a fresh interpreter, at every commit (an import of a
    name another module had not yet defined broke every `todo` call once)."""

    def test_every_module_imports_alone(self):
        names = sorted(p.stem for p in (ROOT / "todolib").glob("*.py") if p.stem != "__init__")
        self.assertIn("store", names)
        failed = {}
        for name in names:
            r = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
                                f"import todolib.{name}"], capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0:
                failed[name] = r.stderr.strip().splitlines()[-1:]
        self.assertEqual(failed, {})

    def test_the_cli_starts(self):
        r = subprocess.run([str(ROOT / "todo"), "help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("migrate", r.stdout)


if __name__ == "__main__":
    unittest.main()
