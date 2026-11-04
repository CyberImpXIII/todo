"""The areas and projects tables (PLAN-todo-tool.md §11 step 1a, tl-720): kept by
the store at the scan root, written by area-add, project-add and project-edit,
each refusing an id neither table holds, and held by check's `records` gate to
the same rule (todolib/tables.py)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import Case, git_commit
from todolib import tables
from todolib.store import FORMAT, RECORDS_FILE, sealed
from todolib.vocab import VOCAB, VOCAB_PATH, Vocab

RAW = json.loads(VOCAB_PATH.read_text())


class Tables(Case):
    def setUp(self):
        super().setUp()
        self.todo("-C", self.ws, "init", "--prefix", "tl")
        self.r = self.repo("r", "rr")
        self.todo("-C", self.ws, "area-add", "devtools", "--name", "dev tools", "--doc", "the frameworks built here")
        self.todo("-C", self.ws, "area-add", "lifestyle", "--name", "lifestyle", "--doc", "tools for his own day")

    def records(self, d=None):
        return json.loads((Path(d or self.ws) / RECORDS_FILE).read_text())

    def raw(self, d=None):
        return (Path(d or self.ws) / RECORDS_FILE).read_bytes()

    def plant(self, d, data):
        """A records file as the CLI writes it (sealed, 0444), so the gate under test
        is `records`, not `seal`."""
        p = Path(d) / RECORDS_FILE
        if p.exists():
            os.chmod(p, 0o644)
        p.write_text(json.dumps(sealed(data), indent=2) + "\n")
        os.chmod(p, 0o444)

    def test_area_add_writes_the_root_store_from_any_repo(self):
        self.todo("-C", self.r, "area-add", "projects", "--name", "projects", "--doc", "things made for their own sake")
        self.assertEqual([a["id"] for a in self.records()["areas"]], ["devtools", "lifestyle", "projects"])
        self.assertFalse((self.r / RECORDS_FILE).exists(), "a repo's own store never holds the tables")
        doc = json.loads(self.todo("-C", self.r, "areas", "--json").stdout)
        self.assertEqual((doc["store"], len(doc["areas"])), ("ws", 3))
        self.assertEqual(doc["areas"][2], {"id": "projects", "name": "projects",
                                           "doc": "things made for their own sake", "added": "2026-10-04"})
        self.check(self.ws)
        self.check(self.r)

    def test_an_area_id_of_the_wrong_form_or_taken_is_refused(self):
        before = self.raw()
        for area in ("Dev", "1x", "a b", "devtools"):
            with self.subTest(area=area):
                self.todo("-C", self.ws, "area-add", area, "--name", "n", "--doc", "d", ok=False)
        self.todo("-C", self.ws, "area-add", "x", "--name", "two\nlines", "--doc", "d", ok=False)
        self.assertEqual(self.raw(), before, "a refused write writes nothing")

    def test_an_unknown_area_is_refused_at_the_write(self):
        before = self.raw()
        r = self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools", "nope", ok=False)
        self.assertIn("no such area", r.stderr)
        self.assertEqual(self.raw(), before)
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools")
        before = self.raw()
        self.todo("-C", self.ws, "project-edit", "pj-1", "--area", "nope", ok=False)
        self.assertEqual(self.raw(), before)
        self.todo("-C", self.ws, "project-edit", "pj-1", "--area", "devtools", "lifestyle")
        self.assertEqual(self.records()["projects"][0]["areas"], ["devtools", "lifestyle"])

    def test_an_unknown_project_id_is_refused_at_the_write(self):
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools")
        before = self.raw()
        for pid in ("pj-2", "pj-0", "tl-1"):
            with self.subTest(pid=pid):
                r = self.todo("-C", self.ws, "project-edit", pid, "--name", "x", ok=False)
                self.assertIn("no such project", r.stderr)
        self.assertEqual(self.raw(), before)
        self.todo("-C", self.ws, "project-edit", "pj-1", "--name", "the todo tool")
        self.assertEqual(self.records()["projects"][0]["name"], "the todo tool")

    def test_project_ids_count_up_and_each_list_given_replaces_the_rows(self):
        (self.ws / "PLAN-todo-tool.md").write_text("# plan\n")
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools", "--repo", "r", "--plan", "PLAN-todo-tool.md")
        self.todo("-C", self.ws, "project-add", "email", "--area", "lifestyle")
        p1, p2 = self.records()["projects"]
        self.assertEqual((p1["id"], p2["id"]), ("pj-1", "pj-2"))
        self.assertEqual(p1, {"id": "pj-1", "name": "todo", "areas": ["devtools"], "priority": None,
                              "plans": ["PLAN-todo-tool.md"], "repos": ["r"], "added": "2026-10-04"})
        self.todo("-C", self.ws, "project-edit", "pj-1", "--repo")
        self.assertEqual(self.records()["projects"][0]["repos"], [], "--repo with none clears it")
        self.assertEqual(self.records()["projects"][0]["plans"], ["PLAN-todo-tool.md"], "a list not given stays")
        self.todo("-C", self.ws, "project-edit", "pj-1", ok=False)
        self.check(self.ws)

    def test_a_repo_or_plan_that_does_not_resolve_is_refused(self):
        before = self.raw()
        for args in (["--repo", "rr"], ["--repo", "nowhere"], ["--plan", "PLAN-gone.md"], ["--plan", "notes.md"]):
            with self.subTest(args=args):
                self.todo("-C", self.ws, "project-add", "p", "--area", "devtools", *args, ok=False)
        self.assertEqual(self.raw(), before)
        self.todo("-C", self.ws, "project-add", "p", "--area", "devtools", "--repo", "r", "ws")

    def test_a_second_project_of_one_name_is_refused(self):
        self.todo("-C", self.ws, "project-add", "Todo", "--area", "devtools")
        self.todo("-C", self.ws, "project-add", "todo", "--area", "lifestyle", ok=False)

    def test_with_no_store_at_the_scan_root_a_write_is_refused(self):
        os.chmod(self.ws / "todo.json", 0o644)
        (self.ws / "todo.json").rename(self.tmp / "away.json")
        r = self.todo("-C", self.r, "area-add", "x", "--name", "n", "--doc", "d", ok=False)
        self.assertIn("no store at the scan root", r.stderr)

    def test_projects_prints_the_priority_it_holds_else_the_default(self):
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools")
        self.assertIn(f"priority {VOCAB.default_priority} (unset)", self.todo("-C", self.ws, "projects").stdout)
        data = self.records()
        data["projects"][0]["priority"] = {"value": "parked", "source": "his words", "by": "jacob", "date": "2026-10-04"}
        self.plant(self.ws, {k: v for k, v in data.items() if k != "seal"})
        out = self.todo("-C", self.ws, "projects").stdout
        self.assertIn("priority parked", out)
        self.assertNotIn("(unset)", out)
        self.check(self.ws)

    # -- check's records gate --------------------------------------------------

    def test_check_fails_a_row_naming_an_area_the_table_does_not_hold(self):
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools")
        data = {k: v for k, v in self.records().items() if k != "seal"}
        data["projects"][0]["areas"] = ["devtools", "gone"]
        self.plant(self.ws, data)
        self.assertFails(self.ws, "records", "the areas table does not hold")

    def test_check_fails_a_priority_outside_the_list(self):
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools")
        data = {k: v for k, v in self.records().items() if k != "seal"}
        data["projects"][0]["priority"] = {"value": "urgent", "source": "s", "by": "jacob", "date": "2026-10-04"}
        self.plant(self.ws, data)
        self.assertFails(self.ws, "records", "'urgent' is not one of")

    def test_check_fails_the_tables_outside_the_store_at_the_scan_root(self):
        self.plant(self.r, {"format": FORMAT, "repo": "r", "tables": [], "runs": {},
                            "areas": [{"id": "x", "name": "x", "doc": "x", "added": "2026-10-04"}]})
        self.assertFails(self.r, "records", "only the store at the scan root")

    def test_check_fails_a_plan_gone_and_a_write_elsewhere_still_goes(self):
        (self.ws / "PLAN-x.md").write_text("# x\n")
        self.todo("-C", self.ws, "project-add", "x", "--area", "devtools", "--plan", "PLAN-x.md")
        (self.ws / "PLAN-x.md").unlink()
        self.assertFails(self.ws, "records", "plan PLAN-x.md is no file")
        self.todo("-C", self.ws, "area-add", "projects", "--name", "p", "--doc", "d")

    # -- the prefix, rename-repo, the move to todo.db ---------------------------

    def test_the_project_prefix_is_no_stores(self):
        d = self.ws / "p"
        d.mkdir()
        r = self.todo("-C", d, "init", "--prefix", VOCAB.project_prefix, ok=False)
        self.assertIn("projects table", r.stderr)
        data = self.store(self.r)
        data["prefix"] = VOCAB.project_prefix
        self.write_json(self.r / "todo.json", {k: v for k, v in data.items() if k != "seal"})
        self.assertFails(self.r, "workspace", "projects table")

    def test_rename_repo_rewrites_a_projects_repos(self):
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools", "--repo", "r")
        self.todo("-C", self.r, "rename-repo", "r", "rnew", "--apply")
        self.assertEqual(self.records()["projects"][0]["repos"], ["rnew"])
        self.check(self.ws)

    def test_the_tables_round_trip_through_todo_db(self):
        git_commit(self.r)
        self.todo("-C", self.ws, "project-add", "todo", "--area", "devtools", "--repo", "r")
        doc = json.loads(self.todo("-C", self.ws, "migrate", "--dry-run", "--json").stdout)
        self.assertTrue(doc["ok"], doc)


class Vocabulary(unittest.TestCase):
    def bad(self, data):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(data, fh)
        try:
            with self.assertRaises(ValueError):
                Vocab(Path(fh.name))
        finally:
            Path(fh.name).unlink()

    def test_the_default_priority_is_one_of_the_list(self):
        self.assertIn(VOCAB.default_priority, VOCAB.priorities)
        self.bad(dict(RAW, priority=dict(RAW["priority"], default="soon")))
        self.bad(dict(RAW, priority=dict(RAW["priority"], values={})))

    def test_the_project_prefix_is_an_id_prefix(self):
        self.bad(dict(RAW, workspace_tables=dict(RAW["workspace_tables"], project_prefix="P-")))

    def test_priority_problem_takes_null_or_a_set_value_with_its_source(self):
        self.assertIsNone(tables.priority_problem(None))
        ok = {"value": "now", "source": "his words", "by": "jacob", "date": "2026-10-22"}
        self.assertIsNone(tables.priority_problem(ok))
        for bad in (dict(ok, value="soon"), dict(ok, source=""), {"value": "now"}, "now"):
            with self.subTest(bad=bad):
                self.assertIsNotNone(tables.priority_problem(bad))


if __name__ == "__main__":
    unittest.main()
