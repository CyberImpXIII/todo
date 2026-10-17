"""`todo check --json` (td-41; README): the gates as one document, for a reader that
must not parse the text. A planted fault is shown to change it, not only to parse."""
import json

from tests.helpers import Case
from todolib.checks import GATES
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")


class CheckJson(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "one", "--kind", NOTE)

    def doc(self, *extra, ok=True, d=None):
        r = self.todo("-C", d or self.a, *extra, "check", "--json", ok=ok)
        return json.loads(r.stdout)

    def test_a_clean_store_is_ok_with_every_gate_named(self):
        doc = self.doc()
        self.assertEqual((doc["ok"], doc["failed"]), (True, 0))
        [s] = doc["stores"]
        self.assertEqual((s["repo"], s["open_items"], s["closed_items"], s["ok"]), ("a", 1, 0, True))
        self.assertEqual(list(s["gates"]), GATES)
        self.assertNotIn("FAIL", s["gates"].values())

    def test_a_failing_item_changes_the_document_and_the_exit(self):
        data = self.store(self.a)
        data["items"][0]["kind"] = "undeclared-name"
        self.write_json(self.a / "todo.json", data)
        doc = self.doc(ok=False)  # exit 1, as the text form
        self.assertEqual((doc["ok"], doc["failed"] >= 1), (False, True))
        [s] = doc["stores"]
        self.assertEqual(s["gates"]["vocab"], "FAIL")
        hit = [f for f in s["findings"] if f["gate"] == "vocab" and f["level"] == "FAIL"]
        self.assertTrue(any("kind 'undeclared-name' is not declared" in f["message"] for f in hit), hit)
        self.assertEqual(hit[0]["where"], "aa-1")

    def test_the_counts_are_the_text_forms(self):
        data = self.store(self.a)
        data["items"][0]["kind"] = "undeclared-name"
        self.write_json(self.a / "todo.json", data)
        [s] = self.doc(ok=False)["stores"]
        last = self.check(self.a, ok=False).stdout.strip().splitlines()[-1]
        self.assertIn(f"{s['failed']} failed, {s['warnings']} warning(s)", last)

    def test_all_sums_every_store(self):
        b = self.repo("b", "bb")
        data = self.store(b)
        data["items"].append(dict(self.store(self.a)["items"][0], id="bb-1", kind="undeclared-name"))
        data["next"] = 2
        self.write_json(b / "todo.json", data)
        doc = json.loads(self.todo("-C", self.a, "--root", self.ws, "check", "--all", "--json", ok=False).stdout)
        self.assertEqual(sorted(s["repo"] for s in doc["stores"]), ["a", "b"])
        self.assertEqual(doc["failed"], sum(s["failed"] for s in doc["stores"]))
        self.assertFalse(doc["ok"])
        self.assertEqual([s["ok"] for s in sorted(doc["stores"], key=lambda s: s["repo"])], [True, False])
