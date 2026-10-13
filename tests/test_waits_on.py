"""waits_on (PLAN-todo-tool.md §10.2 step 2): what a waiting-jacob item waits on, a
declared value from vocab.json `waits_on`, set by add/edit/import and read by
`todo blockers`. Each rule has a passing and a failing case."""
import json
import tempfile
from pathlib import Path

from tests.helpers import ROOT, WAITS, Case
from todolib.vocab import VOCAB, Vocab

NOTE = VOCAB.role("default_kind")
JACOB = VOCAB.jacob_status
OPEN = VOCAB.role("default_status")
WITH_ARG = next(n for n, rx in VOCAB.waits_on_arg.items() if rx is not None and rx.match("intake"))
RAW = json.loads((ROOT / "vocab.json").read_text())


class Field(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")

    def test_a_waiting_item_needs_one_and_an_open_one_takes_none(self):
        err = self.todo("-C", self.a, "add", "w", "--kind", NOTE, "--status", JACOB, ok=False).stderr
        self.assertIn("needs --waits-on", err)
        self.todo("-C", self.a, "add", "w", "--kind", NOTE, "--status", JACOB, "--waits-on", WAITS)
        self.assertEqual(self.store(self.a)["items"][0]["waits_on"], WAITS)
        err = self.todo("-C", self.a, "add", "o", "--kind", NOTE, "--waits-on", WAITS, ok=False).stderr
        self.assertIn(f"waits_on is for a {JACOB} item", err)
        self.check(self.a)

    def test_only_a_declared_value_of_the_declared_form(self):
        bad = ["undeclared", f"{WAITS}:extra", WITH_ARG, f"{WITH_ARG}:Not An Arg"]
        for value in bad:
            with self.subTest(value=value):
                self.todo("-C", self.a, "add", "w", "--kind", NOTE, "--status", JACOB, "--waits-on", value, ok=False)
        self.assertEqual(self.store(self.a)["items"], [])
        self.todo("-C", self.a, "add", "w", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WITH_ARG}:intake")
        self.todo("-C", self.a, "add", "d", "--kind", NOTE, "--status", JACOB, "--waits-on", "decision:PLAN-x.md §3")
        self.assertEqual([it["waits_on"] for it in self.store(self.a)["items"]],
                         [f"{WITH_ARG}:intake", "decision:PLAN-x.md §3"])

    def test_the_value_changes_the_render_and_show(self):
        self.todo("-C", self.a, "add", "w", "--kind", NOTE, "--status", JACOB, "--waits-on", WAITS)
        self.assertIn(f"· waits on: {WAITS}", (self.a / "TODO.md").read_text())
        self.todo("-C", self.a, "edit", "aa-1", "--waits-on", f"{WITH_ARG}:intake")
        md = (self.a / "TODO.md").read_text()
        self.assertIn(f"· waits on: {WITH_ARG}:intake", md)
        self.assertNotIn(f"· waits on: {WAITS}\n", md)
        self.assertIn(f"{WITH_ARG}:intake", self.todo("-C", self.a, "show", "aa-1").stdout)

    def test_leaving_waiting_jacob_clears_it_or_is_refused(self):
        self.todo("-C", self.a, "add", "w", "--kind", NOTE, "--status", JACOB, "--waits-on", WAITS)
        err = self.todo("-C", self.a, "edit", "aa-1", "--status", OPEN, ok=False).stderr
        self.assertIn("clear it with --waits-on ''", err)
        self.todo("-C", self.a, "edit", "aa-1", "--status", OPEN, "--waits-on", "")
        self.assertIsNone(self.store(self.a)["items"][0]["waits_on"])
        err = self.todo("-C", self.a, "edit", "aa-1", "--status", JACOB, ok=False).stderr
        self.assertIn("needs --waits-on", err)
        self.todo("-C", self.a, "edit", "aa-1", "--status", JACOB, "--waits-on", WAITS)

    def plant_bare_waiting(self):
        """A waiting-jacob item written before waits_on existed: no key at all."""
        self.todo("-C", self.a, "add", "old", "--kind", NOTE, "--status", JACOB, "--waits-on", WAITS)
        data = self.store(self.a)
        del data["items"][0]["waits_on"]
        self.write_json(self.a / "todo.json", data)
        self.todo("-C", self.a, "render")

    def test_an_older_waiting_item_is_listed_not_failed_and_stays_editable(self):
        self.plant_bare_waiting()
        out = self.check(self.a).stdout
        self.assertIn(f"INFO  required  -        1 {JACOB} item(s) name no waits_on", out)
        self.assertIn("aa-1", out)
        self.todo("-C", self.a, "edit", "aa-1", "--append-evidence", "still waiting")
        err = self.todo("-C", self.a, "edit", "aa-1", "--waits-on", "undeclared", ok=False).stderr
        self.assertIn("is not one of", err)
        self.todo("-C", self.a, "edit", "aa-1", "--waits-on", WAITS)
        self.assertNotIn("name no waits_on", self.check(self.a).stdout)

    def test_check_fails_a_hand_written_bad_value_or_one_on_another_status(self):
        self.todo("-C", self.a, "add", "w", "--kind", NOTE, "--status", JACOB, "--waits-on", WAITS)
        data = self.store(self.a)
        data["items"][0]["waits_on"] = "undeclared"
        self.write_json(self.a / "todo.json", data)
        self.todo("-C", self.a, "render")
        self.assertFails(self.a, "vocab", "'undeclared' is not one of")
        data["items"][0].update(waits_on=WAITS, status=OPEN)
        self.write_json(self.a / "todo.json", data)
        self.todo("-C", self.a, "render")
        self.assertFails(self.a, "vocab", f"waits_on is for a {JACOB} item")


class Declared(Case):
    def load(self, raw):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(raw, fh)
        try:
            return Vocab(Path(fh.name))
        finally:
            Path(fh.name).unlink()

    def test_a_value_needs_a_name_without_a_colon_and_a_clears_pointer(self):
        self.load(RAW)
        for bad in ({"a:b": {"doc": "x", "argument": None, "clears": "c"}},
                    {"nothing": {"doc": "x", "argument": None, "clears": ""}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.load(dict(RAW, waits_on=dict(RAW["waits_on"], **bad)))

    def test_the_jacob_status_role_names_a_declared_status(self):
        self.assertIn(VOCAB.jacob_status, VOCAB.statuses)
        with self.assertRaises(ValueError):
            self.load(dict(RAW, roles=dict(RAW["roles"], jacob_status="undeclared")))

    def test_every_value_is_documented_and_the_argument_rule_is_read(self):
        """Every key of a waits_on value is consumed: doc by the README table, argument
        by waits_on_problem, clears by `todo blockers`."""
        for name, spec in VOCAB.waits_on.items():
            self.assertEqual(set(spec), {"doc", "argument", "clears"}, name)
        no_arg = self.load(dict(RAW, waits_on={WAITS: dict(RAW["waits_on"][WAITS], argument="^x$")}))
        self.assertIsNone(no_arg.waits_on_problem(f"{WAITS}:x"))
        self.assertIsNotNone(VOCAB.waits_on_problem(f"{WAITS}:x"))
