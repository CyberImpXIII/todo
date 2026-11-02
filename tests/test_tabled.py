"""A tabled location (external audit ra-26.1): its record in the names file carries
`tabled: "<date>: <why>"`; with the file handed, ready, dispatchable and blockers
leave its items out and say so, and sync-plans makes no item for it. Without the
file nothing changes."""
import json
import unittest

from tests.helpers import Case
from todolib import plans

NOTE = "note"
READY = ["--work", "code", "--done-when", "dw", "--size", "S"]
WHY = "2026-10-30: set aside until its constraint is settled"


class Tabled(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.names = self.ws / "names.json"
        self.names.write_text(json.dumps({"locations": [
            {"name": "a", "dir": "a", "store": "a", "remote": None, "agent": "a"},
            {"name": "zeta", "dir": "tools/zeta", "store": None, "remote": None, "agent": "zeta", "tabled": WHY}]}) + "\n")
        self.todo("-C", self.a, "add", "zeta, ready and approved", "--kind", NOTE, "--repo", "zeta", *READY)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "s")
        self.todo("-C", self.a, "add", "zeta, held by its fields", "--kind", NOTE, "--repo", "zeta")
        self.todo("-C", self.a, "add", "a's own, ready and approved", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "approve", "aa-3", "--source", "s")

    def env(self, handed=True):
        return {"TODO_NAMES": str(self.names) if handed else ""}

    def view(self, verb, handed=True):
        return json.loads(self.todo("-C", self.a, "--root", self.ws, verb, "--json", env=self.env(handed)).stdout)

    def test_ready_and_dispatchable_leave_a_tabled_locations_items_out_and_say_so(self):
        ready = self.view("ready")
        self.assertEqual([r["local_id"] for r in ready["ready"]], ["aa-3"])
        self.assertEqual(ready["tabled_out"], [{"repo": "zeta", "why": WHY, "count": 1}])
        disp = self.view("dispatchable")
        self.assertEqual([r["id"] for r in disp["dispatchable"]], ["todo:aa-3"])
        self.assertEqual(disp["tabled_out"], [{"repo": "zeta", "why": WHY, "count": 2}])
        text = self.todo("-C", self.a, "--root", self.ws, "dispatchable", env=self.env()).stdout
        self.assertIn(f"2 item(s) of tabled location(s) left out: zeta ({WHY})", text)
        self.assertIn(f"1 item(s) of tabled location(s) left out: zeta ({WHY})",
                      self.todo("-C", self.a, "--root", self.ws, "ready", env=self.env()).stdout)

    def test_blockers_leave_a_tabled_locations_items_out(self):
        v = self.view("blockers")
        self.assertNotIn("aa-2", json.dumps(v["roots"]))
        self.assertEqual(v["tabled_out"], [{"repo": "zeta", "why": WHY, "count": 2}])
        text = self.todo("-C", self.a, "--root", self.ws, "blockers", env=self.env()).stdout
        self.assertIn(f"2 item(s) of tabled location(s) left out: zeta ({WHY})", text)

    def test_without_the_names_file_nothing_changes(self):
        ready = self.view("ready", handed=False)
        self.assertEqual(sorted(r["local_id"] for r in ready["ready"]), ["aa-1", "aa-3"])
        self.assertEqual(ready["tabled_out"], [])
        disp = self.view("dispatchable", handed=False)
        self.assertEqual(sorted(r["id"] for r in disp["dispatchable"]), ["todo:aa-1", "todo:aa-3"])
        self.assertIn("aa-2", json.dumps(self.view("blockers", handed=False)["roots"]))

    def test_sync_plans_makes_no_item_for_a_tabled_store_and_says_so(self):
        cli, why = plans.resolve_cli(None)
        if why:
            self.skipTest(f"sync-plans reads plans through the setup tool: {why}")
        tabled = self.ws / "names-a.json"
        tabled.write_text(json.dumps({"locations": [
            {"name": "a", "dir": "a", "store": "a", "remote": None, "agent": "a", "tabled": WHY}]}) + "\n")
        (self.ws / "PLAN-x.md").write_text("# X\n\n## 1. First\n\none\n\n## 2. Steps\n\n1. `a`: **Build the thing.**\n")
        before = len(self.store(self.a)["items"])
        out = json.loads(self.todo("-C", self.a, "--root", self.ws, "sync-plans", "--json", env={"TODO_NAMES": str(tabled)}).stdout)
        self.assertEqual(len(self.store(self.a)["items"]), before)
        self.assertTrue(any(n.startswith(f"a: tabled ({WHY}); no item made for") for n in out.get("notices", [])), out.get("notices"))


if __name__ == "__main__":
    unittest.main()
