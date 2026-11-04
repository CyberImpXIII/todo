"""Priority and areas, set and inherited (PLAN-todo-tool.md §11 step 1b, tl-721):
`todo priority` refuses a value without Jacob's words or outside the list; `todo
area` refuses an area the table does not hold; and an item reads as its project's
priority and areas -- the project found by its plan: tag first, then its repo --
unless it has its own (todolib/tables.py effective)."""
import json
import os
import unittest

from tests.helpers import Case
from todolib import tables, tags
from todolib.store import RECORDS_FILE, sealed
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
NOW, NEXT, LATER, PARKED = list(VOCAB.priorities)


def effective(out):
    """The three lines `todo show` ends with, as {label: text}."""
    keys = ("project", "effective priority", "effective areas")
    return {k: ln.split(": ", 1)[1] for ln in out.splitlines() for k in keys if ln.startswith(k + ": ")}


class Priority(Case):
    def setUp(self):
        super().setUp()
        self.todo("-C", self.ws, "init", "--prefix", "tl")
        self.r = self.repo("r", "rr")
        self.s = self.repo("s", "ss")
        for area in ("devtools", "lifestyle", "projects"):
            self.todo("-C", self.ws, "area-add", area, "--name", area, "--doc", "d")
        (self.ws / "PLAN-a.md").write_text("# a\n")
        self.todo("-C", self.ws, "project-add", "alpha", "--area", "devtools", "--plan", "PLAN-a.md")  # pj-1
        self.todo("-C", self.ws, "project-add", "beta", "--area", "lifestyle", "--repo", "r")        # pj-2
        self.todo("-C", self.ws, "priority", "pj-1", NOW, "--source", "Jacob: alpha first")
        self.todo("-C", self.ws, "priority", "pj-2", LATER, "--source", "Jacob: beta after")
        self.todo("-C", self.r, "add", "by repo", "--kind", NOTE)                                    # rr-1
        self.todo("-C", self.r, "add", "by plan", "--kind", NOTE, "--tags", "plan:PLAN-a.md§3")      # rr-2
        self.todo("-C", self.s, "add", "no project", "--kind", NOTE)                                 # ss-1

    def show(self, d, iid):
        return effective(self.todo("-C", d, "show", iid).stdout)

    def records(self):
        return json.loads((self.ws / RECORDS_FILE).read_text())

    # -- inheritance --------------------------------------------------------------

    def test_an_item_inherits_by_its_plan_tag_first_then_its_repo(self):
        self.assertEqual(self.show(self.r, "rr-1"), {"project": "pj-2 (by its repo r)",
                                                     "effective priority": f"{LATER} (from pj-2)",
                                                     "effective areas": "lifestyle (from pj-2)"})
        # rr-2 lives in r (pj-2's repo) too: its plan: tag is nearer, so pj-1 wins
        self.assertEqual(self.show(self.r, "rr-2"), {"project": "pj-1 (by its plan: tag)",
                                                     "effective priority": f"{NOW} (from pj-1)",
                                                     "effective areas": "devtools (from pj-1)"})
        self.assertEqual(self.show(self.s, "ss-1"), {"project": "none (no project names its plan or its repo s)",
                                                     "effective priority": f"{NEXT} (the default)",
                                                     "effective areas": "none"})

    def test_the_items_own_value_wins_and_clearing_it_inherits_again(self):
        self.todo("-C", self.r, "priority", "rr-2", PARKED, "--source", "Jacob: not this one")
        self.todo("-C", self.r, "area", "rr-2", "projects", "lifestyle")
        self.assertEqual(self.show(self.r, "rr-2"), {"project": "pj-1 (by its plan: tag)",
                                                     "effective priority": f"{PARKED} (its own)",
                                                     "effective areas": "projects, lifestyle (its own)"})
        item = self.store(self.r)["items"][1]
        self.assertEqual(item["priority"], {"value": PARKED, "source": "Jacob: not this one",
                                            "by": VOCAB.approval_by, "date": "2026-10-04"})
        self.assertEqual(item["tags"], ["plan:PLAN-a.md§3", "area:projects", "area:lifestyle"])
        self.todo("-C", self.r, "priority", "rr-2", "--clear")
        self.todo("-C", self.r, "area", "rr-2", "--clear")
        self.assertEqual(self.show(self.r, "rr-2")["effective priority"], f"{NOW} (from pj-1)")
        self.assertEqual(self.show(self.r, "rr-2")["effective areas"], "devtools (from pj-1)")
        self.assertEqual(self.store(self.r)["items"][1]["tags"], ["plan:PLAN-a.md§3"], "--clear keeps the other tags")
        self.check(self.r)
        self.check(self.ws)

    def test_the_projects_value_changes_what_its_items_read(self):
        """The input changes the output: the item reads whatever its project holds now."""
        self.todo("-C", self.ws, "priority", "pj-2", PARKED, "--source", "Jacob: park beta")
        self.todo("-C", self.ws, "area", "pj-2", "projects")
        self.assertEqual(self.show(self.r, "rr-1")["effective priority"], f"{PARKED} (from pj-2)")
        self.assertEqual(self.show(self.r, "rr-1")["effective areas"], "projects (from pj-2)")
        self.todo("-C", self.ws, "priority", "pj-2", "--clear")
        self.assertEqual(self.show(self.r, "rr-1")["effective priority"], f"{NEXT} (the default)")

    def test_an_items_repo_field_finds_its_project_before_its_stores_key(self):
        self.todo("-C", self.s, "add", "work in r", "--kind", NOTE, "--repo", "r")  # ss-2
        self.assertEqual(self.show(self.s, "ss-2")["project"], "pj-2 (by its repo r)")

    def test_two_projects_at_one_level_are_no_project_never_a_pick(self):
        self.todo("-C", self.ws, "project-add", "gamma", "--area", "projects", "--plan", "PLAN-a.md")
        got = self.show(self.r, "rr-2")
        self.assertIn("ambiguous", got["project"])
        self.assertEqual(got["effective priority"], f"{NEXT} (the default)")
        self.assertEqual(got["effective areas"], "none")

    def test_with_no_store_at_the_scan_root_the_effective_values_are_unknown(self):
        os.chmod(self.ws / "todo.json", 0o644)
        (self.ws / "todo.json").rename(self.tmp / "away.json")
        got = self.show(self.r, "rr-1")
        self.assertTrue(got["project"].startswith("unknown"), got)
        self.assertEqual((got["effective priority"], got["effective areas"]), ("unknown", "unknown"))

    # -- refusals -----------------------------------------------------------------

    def test_a_priority_without_source_or_outside_the_list_is_refused(self):
        item_before = (self.r / "todo.json").read_bytes()
        table_before = (self.ws / RECORDS_FILE).read_bytes()
        for target, d in (("rr-1", self.r), ("pj-1", self.ws)):
            for args, says in (([NOW], "--source"), ([NOW, "--source", ""], "--source"),
                               ([NOW, "--source", "two\nlines"], "--source"),
                               (["urgent", "--source", "s"], "one of"), ([NOW.upper(), "--source", "s"], "one of"),
                               ([NOW, "--source", "s", "--date", "2026-10-05"], "no later than today"),
                               ([], "VALUE"), ([NOW, "--clear"], "--clear takes")):
                with self.subTest(target=target, args=args):
                    r = self.todo("-C", d, "priority", target, *args, ok=False)
                    self.assertIn(says, r.stderr)
        self.assertEqual((self.r / "todo.json").read_bytes(), item_before, "a refused write writes nothing")
        self.assertEqual((self.ws / RECORDS_FILE).read_bytes(), table_before)
        r = self.todo("-C", self.ws, "priority", "pj-9", NOW, "--source", "s", ok=False)
        self.assertIn("no such project", r.stderr)
        self.todo("-C", self.r, "priority", "rr-1", "--clear", ok=False)  # nothing to clear

    def test_an_area_the_table_does_not_hold_is_refused(self):
        before = (self.r / "todo.json").read_bytes()
        for args in (["rr-1", "nope"], ["rr-1", "devtools", "devtools"], ["rr-1"], ["rr-1", "devtools", "--clear"]):
            with self.subTest(args=args):
                self.todo("-C", self.r, "area", *args, ok=False)
        r = self.todo("-C", self.r, "add", "x", "--kind", NOTE, "--tags", "area:nope", ok=False)
        self.assertIn("no such area", r.stderr)
        self.todo("-C", self.r, "edit", "rr-1", "--tags", "area:Dev", ok=False)
        self.assertEqual((self.r / "todo.json").read_bytes(), before)
        self.todo("-C", self.ws, "area", "pj-1", "nope", ok=False)
        self.todo("-C", self.ws, "area", "pj-1", "--clear", ok=False)  # a project has one or more
        self.todo("-C", self.r, "edit", "rr-1", "--tags", "area:devtools")
        self.assertEqual(self.show(self.r, "rr-1")["effective areas"], "devtools (its own)")

    # -- check --------------------------------------------------------------------

    def plant_item(self, **fields):
        data = {k: v for k, v in self.store(self.r).items() if k != "seal"}
        data["items"][0].update(fields)
        self.write_json(self.r / "todo.json", data)

    def test_check_fails_an_area_tag_the_table_does_not_hold(self):
        self.plant_item(tags=["area:gone"])
        self.assertFails(self.r, "tags", "the areas table does not hold gone")

    def test_check_fails_an_item_priority_not_set_by_jacob_or_outside_the_list(self):
        good = {"value": NOW, "source": "s", "by": VOCAB.approval_by, "date": "2026-10-04"}
        for bad, says in ((dict(good, by="model"), "only Jacob"), (dict(good, value="urgent"), "is not one of"),
                          (dict(good, source=""), "source")):
            with self.subTest(bad=bad):
                self.plant_item(priority=bad)
                self.assertFails(self.r, "schema", says)

    def test_check_fails_a_project_priority_not_set_by_jacob(self):
        data = {k: v for k, v in self.records().items() if k != "seal"}
        data["projects"][0]["priority"]["by"] = "model"
        p = self.ws / RECORDS_FILE
        os.chmod(p, 0o644)
        p.write_text(json.dumps(sealed(data), indent=2) + "\n")
        os.chmod(p, 0o444)
        self.assertFails(self.ws, "records", "only Jacob")


class Effective(unittest.TestCase):
    """tables.effective without the CLI: the rule the fixture above runs through."""
    P1 = {"id": "pj-1", "areas": ["a"], "plans": ["PLAN-a.md"], "repos": [],
          "priority": {"value": NOW, "source": "s", "by": VOCAB.approval_by, "date": "2026-10-04"}}
    P2 = {"id": "pj-2", "areas": ["b"], "plans": [], "repos": ["r"], "priority": None}

    def test_plan_first_then_repo_then_none(self):
        both = {"tags": ["plan:PLAN-a.md"], "repo": "r"}
        self.assertEqual(tables.effective(both, "x", [self.P1, self.P2])["project"], "pj-1")
        self.assertEqual(tables.effective({"repo": "r"}, "x", [self.P1, self.P2])["project"], "pj-2")
        self.assertEqual(tables.effective({}, "r", [self.P1, self.P2])["project"], "pj-2", "the store's key")
        none = tables.effective({}, "x", [self.P1, self.P2])
        self.assertEqual((none["project"], none["priority"], none["areas"]),
                         (None, {"value": NEXT, "from": None}, {"value": [], "from": None}))

    def test_two_projects_holding_the_repo_are_no_project(self):
        p3 = dict(self.P2, id="pj-3", areas=["c"])
        e = tables.effective({"repo": "r"}, "x", [self.P2, p3])
        self.assertEqual((e["project"], e["areas"]["value"]), (None, []))
        self.assertIn("ambiguous", e["via"])

    def test_an_area_tag_of_the_wrong_form_is_no_tag(self):
        """The form alone, as check judges it with no table to read."""
        self.assertIsNone(tags.problem("area:devtools", stored=True))
        for bad in ("area:Dev", "area:1x", "area:" + "a" * 25):
            with self.subTest(bad=bad):
                self.assertIsNotNone(tags.problem(bad, stored=True))

    def test_a_project_with_no_priority_reads_as_the_default_its_areas_still_inherited(self):
        e = tables.effective({"repo": "r"}, "x", [self.P2])
        self.assertEqual((e["priority"], e["areas"]), ({"value": NEXT, "from": None}, {"value": ["b"], "from": "pj-2"}))

    def test_an_unreadable_table_is_unknown_never_the_default(self):
        e = tables.effective({"repo": "r"}, "x", None)
        self.assertEqual((e["project"], e["priority"]["value"], e["areas"]["value"]), (None, None, None))
        own = tables.effective({"priority": self.P1["priority"], "tags": ["area:c"]}, "x", None)
        self.assertEqual((own["priority"], own["areas"]), ({"value": NOW, "from": "own"}, {"value": ["c"], "from": "own"}))


if __name__ == "__main__":
    unittest.main()
