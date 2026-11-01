"""The write log (ELABORATION-2.4-2.6.md §2.3 parts 1 and 3): every CLI write that
changes a file appends {at, verb, ids, by, why, seal_before, seal_after} to
todo-writes.jsonl; `todo check` holds todo.json's seal to the newest row's, and the
CLI refuses to write over a todo.json replaced around it (INCIDENTS.md I-3: a stash
brought back sealed files nobody could tell apart) until `todo reseal` accepts it."""
import json
import os
import shutil

from tests.helpers import Case

NOTE = "note"


class WriteLog(Case):
    def rows(self, d):
        p = d / "todo-writes.jsonl"
        return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []

    def env(self, **kw):
        base = {"CLAUDECODE": "", "TODO_BY": "", "TODO_WHY": ""}
        base.update(kw)
        return base

    def test_a_write_is_logged_with_who_why_and_the_seals(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "--why", "first note", "add", "one", "--kind", NOTE, env=self.env())
        self.todo("-C", a, "--by", "reviewer", "edit", "aa-1", "--title", "one, edited", env=self.env())
        rows = self.rows(a)
        self.assertEqual([(r["verb"], r["ids"], r["by"], r["why"]) for r in rows][-2:],
                         [("add", ["aa-1"], "jacob", "first note"), ("edit", ["aa-1"], "reviewer", None)])
        self.assertEqual(rows[-1]["seal_before"], rows[-2]["seal_after"])
        self.assertEqual(rows[-1]["seal_after"], self.store(a)["seal"])
        self.assertEqual(os.stat(a / "todo-writes.jsonl").st_mode & 0o777, 0o444)
        self.check(a)

    def test_the_actor_from_the_environment_and_inside_a_session(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE, env=self.env(TODO_BY="detect-run", TODO_WHY="S7 found it"))
        self.todo("-C", a, "add", "two", "--kind", NOTE, env=self.env(CLAUDECODE="1"))
        self.assertEqual([(r["by"], r["why"]) for r in self.rows(a)][-2:],
                         [("detect-run", "S7 found it"), ("unattributed", None)])
        r = self.todo("-C", a, "--by", "two\nlines", "add", "three", "--kind", NOTE, ok=False, env=self.env())
        self.assertIn("--by: one non-empty line", r.stderr)

    def test_a_command_that_changes_nothing_logs_nothing(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE, env=self.env())
        n = len(self.rows(a))
        self.todo("-C", a, "list", env=self.env())
        self.todo("-C", a, "check", env=self.env())
        self.assertEqual(len(self.rows(a)), n)

    def test_a_store_replaced_around_the_cli_is_red_refused_and_reseal_accepts_it(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE, env=self.env())
        old = self.tmp / "old.json"
        shutil.copy(a / "todo.json", old)                       # a sealed version, as a stash keeps it
        self.todo("-C", a, "add", "two", "--kind", NOTE, env=self.env())
        os.chmod(a / "todo.json", 0o644)
        shutil.copy(old, a / "todo.json")                       # set back around the CLI: its seal still matches
        os.chmod(a / "todo.json", 0o444)
        out = self.assertFails(a, "writes", "is not the one its last logged write left")
        self.assertIn("todo reseal --reason R", out)
        r = self.todo("-C", a, "add", "three", "--kind", NOTE, ok=False, env=self.env())
        self.assertIn("replaced around the CLI", r.stderr)
        self.todo("-C", a, "reseal", "--reason", "the older version is the right one", env=self.env())
        self.assertEqual(self.rows(a)[-1]["verb"], "reseal")
        self.assertEqual(self.store(a)["hand_edits"][-1]["via"], "reseal")
        self.check(a)
        self.todo("-C", a, "add", "three", "--kind", NOTE, env=self.env())

    def test_a_torn_log_row_is_red(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE, env=self.env())
        p = a / "todo-writes.jsonl"
        os.chmod(p, 0o644)
        p.write_text(p.read_text() + '{"at": "x"\n')
        self.assertFails(a, "writes", "does not parse")
