"""`todo blockers` (PLAN-todo-tool.md §10.2 step 1, its gates): each root kind has a
passing and a failing fixture, a chain ends at its end, a cycle is reported and never
looped on, the count a root frees is the ids it lists, the declared kinds are the
implemented ones, and `dispatchable` and `blockers` split the open items between them."""
import json
from unittest import mock

from tests.helpers import Case
from todolib import blockers
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
JACOB = VOCAB.jacob_status
WORK = next(iter(VOCAB.works))
READY = ["--work", WORK, "--done-when", "dw", "--size", VOCAB.ready_sizes[0]]
WIZARD = next(n for n, rx in VOCAB.waits_on_arg.items() if rx is not None and rx.match("intake"))


class Roots(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")

    def view(self, d=None):
        return json.loads(self.todo("-C", d or self.a, "blockers", "--json").stdout)

    def root_of(self, v, item_id):
        hits = [g for g in v["roots"] if item_id in g["ids"]]
        self.assertLessEqual(len(hits), 1, f"{item_id} under more than one root: {hits}")
        return hits[0] if hits else None

    # jacob
    def test_jacob_a_waits_on_groups_and_names_what_clears_it(self):
        self.todo("-C", self.a, "add", "q1", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WIZARD}:intake")
        self.todo("-C", self.a, "add", "q2", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WIZARD}:intake")
        self.todo("-C", self.a, "add", "q3", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WIZARD}:other")
        v = self.view()
        g = self.root_of(v, "aa-1")
        self.assertEqual((g["kind"], g["ids"]), ("jacob", ["aa-1", "aa-2"]))
        self.assertEqual(g["clears"], VOCAB.waits_on[WIZARD]["clears"].format(arg="intake"))
        self.assertEqual(self.root_of(v, "aa-3")["clears"], VOCAB.waits_on[WIZARD]["clears"].format(arg="other"))
        self.assertEqual(v["roots"][0]["ids"], ["aa-1", "aa-2"])  # most freed first

    def test_jacob_an_item_ready_but_unapproved_waits_on_his_yes_and_an_approved_one_is_not_held(self):
        self.todo("-C", self.a, "add", "job", "--kind", NOTE, *READY)
        g = self.root_of(self.view(), "aa-1")
        self.assertEqual((g["kind"], g["what"]), ("jacob", f"waits on {VOCAB.role('approval_waits_on')}"))
        self.assertIn("todo approve", g["clears"])
        self.todo("-C", self.a, "approve", "aa-1", "--source", "s")
        self.assertIsNone(self.root_of(self.view(), "aa-1"))

    def test_jacob_an_older_item_naming_nothing_is_grouped_as_such(self):
        self.todo("-C", self.a, "add", "old", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WIZARD}:intake")
        data = self.store(self.a)
        del data["items"][0]["waits_on"]
        self.write_json(self.a / "todo.json", data)
        g = self.root_of(self.view(), "aa-1")
        self.assertEqual(g["what"], f"{JACOB}, naming no waits_on")

    # item
    def test_item_a_chain_is_followed_to_its_end(self):
        self.todo("-C", self.a, "add", "end", "--kind", NOTE)
        self.todo("-C", self.a, "add", "middle", "--kind", NOTE, *READY, "--blocked-by", "aa-1")
        self.todo("-C", self.a, "add", "start", "--kind", NOTE, *READY, "--blocked-by", "aa-2")
        v = self.view()
        g = self.root_of(v, "aa-3")
        self.assertEqual((g["kind"], g["ids"]), ("item", ["aa-2", "aa-3"]))
        self.assertEqual(g["what"], "open item aa-1")
        self.assertNotEqual(self.root_of(v, "aa-1")["kind"], "item")
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "r")
        v = self.view()
        self.assertEqual(self.root_of(v, "aa-3")["what"], "open item aa-2")
        self.assertEqual(self.root_of(v, "aa-2")["kind"], "jacob")  # freed of its chain: only his yes left

    def test_item_a_cycle_is_reported_never_looped_on(self):
        self.todo("-C", self.a, "add", "one", "--kind", NOTE)
        self.todo("-C", self.a, "add", "two", "--kind", NOTE, "--blocked-by", "aa-1")
        data = self.store(self.a)
        data["items"][0]["blocked_by"] = ["aa-2"]  # the CLI refuses a cycle; a hand edit makes one
        self.write_json(self.a / "todo.json", data)
        v = self.view()  # returns: a loop would hang here, and the test runner times out
        g = self.root_of(v, "aa-1")
        self.assertIn("cycle", g["what"])
        self.assertEqual(sorted(g["ids"]), ["aa-1", "aa-2"])

    def test_item_an_id_no_store_holds_is_a_root_of_its_own(self):
        self.todo("-C", self.a, "add", "one", "--kind", NOTE, *READY)
        data = self.store(self.a)
        data["items"][0]["blocked_by"] = ["zz-9"]
        self.write_json(self.a / "todo.json", data)
        g = self.root_of(self.view(), "aa-1")
        self.assertEqual(g["kind"], "item")
        self.assertIn("zz-9, in no scanned store", g["what"])

    # owner
    def test_owner_a_report_waits_on_its_counterpart_and_names_it(self):
        b = self.repo("b", "bb")
        self.todo("-C", self.a, "add", "theirs", "--kind", NOTE)
        self.todo("-C", self.a, "add", "mine", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "report", "aa-1", "--to", "b")
        v = self.view()
        g = self.root_of(v, "aa-1")
        self.assertEqual((g["kind"], g["what"]), ("owner", "reported to b"))
        self.assertIn("aa-1->bb-1", g["clears"])
        self.assertNotEqual(self.root_of(v, "aa-2")["kind"], "owner")
        self.assertEqual(self.root_of(self.view(b), "bb-1")["kind"], "field")  # the counterpart is b's to triage

    # field
    def test_field_what_brief_lacks_is_the_stores_owner_to_triage(self):
        self.todo("-C", self.a, "add", "bare", "--kind", NOTE, "--work", WORK)
        self.todo("-C", self.a, "add", "full", "--kind", NOTE, *READY)
        v = self.view()
        g = self.root_of(v, "aa-1")
        self.assertEqual(g["kind"], "field")
        self.assertIn("done_when (1)", g["what"])
        self.assertIn("size (1)", g["what"])
        self.assertNotIn("work (", g["what"])
        self.assertNotEqual(self.root_of(v, "aa-2")["kind"], "field")

    def test_field_a_blocked_status_naming_no_blocker(self):
        self.todo("-C", self.a, "add", "stuck", "--kind", NOTE, *READY, "--status", "blocked")
        self.assertIn("status blocked without blocked_by (1)", self.root_of(self.view(), "aa-1")["what"])


class Counts(Case):
    def test_the_count_a_root_frees_is_the_ids_it_lists_and_the_text_agrees(self):
        a = self.repo("a", "aa")
        for i in range(7):
            self.todo("-C", a, "add", f"q{i}", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WIZARD}:intake")
        self.todo("-C", a, "add", "bare", "--kind", NOTE)
        v = json.loads(self.todo("-C", a, "blockers", "--json").stdout)
        for g in v["roots"]:
            self.assertEqual(g["count"], len(g["ids"]))
        self.assertEqual(v["items"], 8)
        self.assertEqual(v["items"], sum(g["count"] for g in v["roots"]))
        out = self.todo("-C", a, "blockers").stdout
        n = VOCAB.blocker_bounds["max_ids"]
        self.assertIn(f"   7 jacob  waits on {WIZARD}:intake", out)
        self.assertIn(", ".join(f"aa-{i}" for i in range(1, n + 1)) + f" (+{7 - n})", out)

    def test_the_bounds_are_read_from_vocab(self):
        v = {"items": 6, "unreadable": [], "roots": [
            {"kind": "jacob", "what": f"w{i}", "clears": "c", "count": 2, "ids": [f"x-{i}", f"y-{i}"]} for i in range(3)]}
        with mock.patch.dict(VOCAB.blocker_bounds, {"max_roots": 2, "max_ids": 1}):
            out = blockers.lines(v)
        self.assertEqual(len(out), 3)
        self.assertIn("x-0 (+1)", out[0])
        self.assertIn("(+1 more root(s), holding 2 item(s)", out[2])
        with mock.patch.dict(VOCAB.blocker_bounds, {"max_roots": 3, "max_ids": 2}):
            out = blockers.lines(v)
        self.assertEqual(len(out), 3)
        self.assertIn("x-0, y-0 --", out[0] + " --")

    def test_ties_rank_by_the_declared_order_of_kinds(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "bare", "--kind", NOTE)
        self.todo("-C", a, "add", "q", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WIZARD}:intake")
        v = json.loads(self.todo("-C", a, "blockers", "--json").stdout)
        kinds = [g["kind"] for g in v["roots"]]
        self.assertEqual(kinds, sorted(kinds, key=VOCAB.blocker_roots.index))


class Declared(Case):
    def test_declared_root_kinds_are_the_implemented_ones_both_ways(self):
        self.assertEqual(set(VOCAB.blocker_roots), set(blockers.ROOTS))

    def test_dispatchable_and_blockers_split_the_open_items_between_them(self):
        """Every open item is dispatchable, dispatched, a split parent, or under exactly
        one root: never both, never neither (the seam between the two views)."""
        a, b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", a, "add", "ready approved", "--kind", NOTE, *READY)
        self.todo("-C", a, "approve", "aa-1", "--source", "s")
        self.todo("-C", a, "add", "ready unapproved", "--kind", NOTE, *READY)
        self.todo("-C", a, "add", "bare", "--kind", NOTE)
        self.todo("-C", a, "add", "chained", "--kind", NOTE, *READY, "--blocked-by", "aa-3")
        self.todo("-C", a, "add", "waiting", "--kind", NOTE, *READY, "--status", JACOB, "--waits-on", f"{WIZARD}:intake")
        self.todo("-C", a, "add", "reported", "--kind", NOTE)
        self.todo("-C", a, "report", "aa-6", "--to", "b")
        self.todo("-C", a, "add", "out", "--kind", NOTE, *READY)
        self.todo("-C", a, "approve", "aa-7", "--source", "s")
        self.todo("-C", a, "dispatch", "aa-7")
        disp = json.loads(self.todo("-C", a, "dispatchable", "--json").stdout)
        held = json.loads(self.todo("-C", a, "blockers", "--json").stdout)
        listed = {r["id"].split(":", 1)[1] for r in disp["dispatchable"]}
        out = {d["id"].split(":", 1)[1] for d in disp["dispatched"]}
        rooted = [i for g in held["roots"] for i in g["ids"]]
        self.assertEqual(len(rooted), len(set(rooted)))
        everyone = {it["id"] for s in (a, b) for it in self.store(s)["items"]}
        self.assertEqual(listed | out | set(rooted), everyone)
        self.assertEqual(listed & set(rooted), set())
        self.assertEqual(listed, {"aa-1"})

    def test_dispatchable_prints_the_top_roots_when_nothing_is_dispatchable(self):
        a = self.repo("a", "aa")
        n = VOCAB.blocker_bounds["dispatchable_lines"]
        for i in range(n + 2):
            self.todo("-C", a, "add", f"q{i}", "--kind", NOTE, "--status", JACOB, "--waits-on", f"{WIZARD}:d{i}")
        out = self.todo("-C", a, "dispatchable").stdout
        self.assertIn(f"under {n + 2} root(s), the top {n} here", out)
        self.assertEqual(sum(f"waits on {WIZARD}:d" in ln for ln in out.splitlines()), n)
        self.assertNotIn("carry no approval", out)
        self.todo("-C", a, "add", "go", "--kind", NOTE, *READY)
        self.todo("-C", a, "approve", f"aa-{n + 3}", "--source", "s")
        out = self.todo("-C", a, "dispatchable").stdout
        self.assertNotIn("waits on", out)
        self.assertIn(f"({n + 2} open item(s) carry no approval)", out)

    def test_a_bound_is_a_positive_whole_number_and_the_approval_role_a_declared_waits_on(self):
        import tempfile
        from pathlib import Path
        from tests.helpers import ROOT
        from todolib.vocab import Vocab
        raw = json.loads((ROOT / "vocab.json").read_text())
        bads = [dict(raw, blockers=dict(raw["blockers"], max_ids=0)),
                dict(raw, blockers=dict(raw["blockers"], dispatchable_lines="5")),
                dict(raw, roles=dict(raw["roles"], approval_waits_on="undeclared"))]
        for bad in bads:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump(bad, fh)
            with self.subTest(bad=bad["blockers"], role=bad["roles"]["approval_waits_on"]), self.assertRaises(ValueError):
                Vocab(Path(fh.name))
            Path(fh.name).unlink()
