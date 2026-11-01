"""The names file handed to todo (PLAN-architecture.md §13.1 G4, ra-19.3): with it, a
report's target is a location's name, never a path, a store key or an old spelling;
without it, the scan judges as before. todo never looks for the file itself."""
import json
import unittest

from tests.helpers import Case

REPORT = "report"
NOTE = "note"


class NamesFile(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")
        self.names = self.ws / "names.json"
        self.names.write_text(json.dumps({"locations": [
            {"name": "a", "dir": "a", "store": "a", "remote": "owner/a", "agent": "a"},
            {"name": "b", "dir": "b", "store": "b", "remote": "owner/b-repo", "agent": "b"},
            {"name": "layer", "dir": ".layer", "store": "layer", "remote": None, "agent": "layer"},
            {"name": "wizard", "dir": "tools/wizard", "store": None, "remote": None, "agent": "wizard"}]}) + "\n")
        self.todo("-C", self.a, "add", "x", "--kind", REPORT, "--reported-to", "b")

    def env(self, **kw):
        base = {"TODO_NAMES": ""}
        base.update(kw)
        return base

    def test_without_a_file_the_scan_judges_as_before(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "b", env=self.env())
        self.assertEqual(self.store(self.a)["items"][0]["reported_to"]["their_id"], "bb-1")

    def test_a_known_name_pairs_and_a_path_or_old_key_is_refused_by_name(self):
        r = self.todo("-C", self.a, "--names", self.names, "report", "aa-1", "--to", "tools/wizard", ok=False, env=self.env())
        self.assertIn("'tools/wizard' is not a location's name", r.stderr)
        self.assertIn("the location is named 'wizard'", r.stderr)
        r = self.todo("-C", self.a, "--names", self.names, "report", "aa-1", "--to", "b-repo", ok=False, env=self.env())
        self.assertIn("the location is named 'b'", r.stderr)
        r = self.todo("-C", self.a, "--names", self.names, "report", "aa-1", "--to", "nobody", ok=False, env=self.env())
        self.assertIn("'nobody' is no location in", r.stderr)
        self.assertIsNone(self.store(self.a)["items"][0]["reported_to"]["their_id"])
        self.todo("-C", self.a, "--names", self.names, "report", "aa-1", "--to", "b", env=self.env())
        self.assertEqual(self.store(self.a)["items"][0]["reported_to"]["their_id"], "bb-1")

    def test_add_and_edit_reported_to_are_judged_the_same_way(self):
        r = self.todo("-C", self.a, "add", "y", "--kind", REPORT, "--reported-to", "tools/wizard", ok=False, env=self.env(TODO_NAMES=str(self.names)))
        self.assertIn("the location is named 'wizard'", r.stderr)
        self.todo("-C", self.a, "add", "y", "--kind", REPORT, "--reported-to", "wizard", env=self.env(TODO_NAMES=str(self.names)))
        r = self.todo("-C", self.a, "edit", "aa-2", "--reported-to", "nobody", ok=False, env=self.env(TODO_NAMES=str(self.names)))
        self.assertIn("'nobody' is no location in", r.stderr)

    def test_a_hidden_stores_name_is_a_valid_target_and_stays_unpaired_for_the_owner_to_pull(self):
        r = self.todo("-C", self.a, "--names", self.names, "report", "aa-1", "--to", "layer", ok=False, env=self.env())
        self.assertIn("already reported to b", r.stderr)
        self.todo("-C", self.a, "add", "z", "--kind", REPORT, "--reported-to", "layer", env=self.env(TODO_NAMES=str(self.names)))
        r = self.todo("-C", self.a, "--names", self.names, "report", "aa-2", "--to", "layer", env=self.env())
        self.assertIn("no store for layer in the scan", r.stdout)

    def test_a_file_that_cannot_be_read_refuses_rather_than_judging_without_it(self):
        r = self.todo("-C", self.a, "--names", self.ws / "missing.json", "report", "aa-1", "--to", "b", ok=False, env=self.env())
        self.assertIn("no such file", r.stderr)
        bad = self.ws / "bad.json"
        bad.write_text(json.dumps({"locations": [{"name": "a"}]}) + "\n")
        r = self.todo("-C", self.a, "--names", bad, "report", "aa-1", "--to", "b", ok=False, env=self.env())
        self.assertIn("location #0 is not", r.stderr)
        self.assertIsNone(self.store(self.a)["items"][0]["reported_to"]["their_id"])

    def test_check_keys_reads_fields_as_data_and_prose_as_quotation(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "b", env=self.env())   # paired, so the reports gate is quiet
        self.todo("-C", self.a, "add", "names the old key in prose: job-import-things was here", "--kind", NOTE, "--evidence", "see tools/wizard and b-repo", env=self.env())
        self.todo("-C", self.a, "add", "keyed by a path", "--kind", NOTE, "--repo", "tools/wizard", env=self.env())
        out = self.check(self.a, today="2026-11-01").stdout
        self.assertNotIn("keys", out.replace("  ok    keys", ""), "without a names file the gate judges nothing")
        r = self.todo("-C", self.a, "check", ok=False, env=self.env(TODO_NAMES=str(self.names)))
        self.assertIn("FAIL  keys      aa-3     repo (store): 'tools/wizard' is not a location's name", r.stdout)
        self.assertIn("the location is named 'wizard'", r.stdout)
        self.assertNotIn("aa-2", "\n".join(ln for ln in r.stdout.splitlines() if "keys" in ln), "prose is never read")
        self.assertEqual(sum(1 for ln in r.stdout.splitlines() if "FAIL  keys" in ln), 1)


if __name__ == "__main__":
    unittest.main()
