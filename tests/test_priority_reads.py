"""The reads of priority and areas (PLAN-todo-tool.md §11 step 1c, tl-722): `--area`
and priority order on list, ready, decisions and dispatchable; a priority vocab.json
never dispatches leaves ready and dispatchable, one it never tables leaves decisions,
each shown only in a count; `todo brief` prints the effective priority and where it
came from; `todo projects` counts each project's open, ready and parked items.

The fixture: a workspace store holding the tables, three repos, one project each
(pj-1 alpha: a, devtools; pj-2 beta: b, lifestyle; pj-3 gamma: c, devtools), and in
each repo one approved ready note and one complete decision. Decisions' pointers
resolve through the real setup tool, as in tests/test_decisions.py."""
import json
import os
import tempfile
from pathlib import Path

from tests.helpers import Case
from todolib import plans, tables
from todolib.vocab import VOCAB_PATH, Vocab, VOCAB

NOTE = VOCAB.role("default_kind")
DECISION = VOCAB.role("decision_kind")
ORDER = list(VOCAB.priorities)
NOW, NEXT, LATER, PARKED = ORDER
# the behaviours the fixture leans on, so a vocabulary change that moves them fails here first
assert (VOCAB.priorities[LATER]["dispatched"], VOCAB.priorities[LATER]["tabled"], VOCAB.priorities[LATER]["count"],
        VOCAB.priorities[PARKED]["dispatched"], VOCAB.priorities[PARKED]["tabled"],
        VOCAB.priorities[PARKED]["count"]) == (True, False, "project", False, False, "total")
READY = ["--work", next(iter(VOCAB.works)), "--done-when", "dw", "--size", VOCAB.ready_sizes[0]]
PLAN = "# X\n\n## 1. First\n\none\n"


class Reads(Case):
    def setUp(self):
        super().setUp()
        _, why = plans.resolve_cli(None)
        if why:
            self.fail(f"these tests read plans through the setup tool: {why}")
        (self.ws / "PLAN-x.md").write_text(PLAN)
        self.todo("-C", self.ws, "init", "--prefix", "tl")
        self.dirs = {}
        for name in ("a", "b", "c"):
            self.dirs[name] = self.repo(name, name * 2)
        for area in ("devtools", "lifestyle"):
            self.todo("-C", self.ws, "area-add", area, "--name", area, "--doc", "d")
        for name, area in (("a", "devtools"), ("b", "lifestyle"), ("c", "devtools")):
            self.todo("-C", self.ws, "project-add", f"p{name}", "--area", area, "--repo", name)  # pj-1..pj-3
            d = self.dirs[name]
            self.run_in(d, "add", f"work {name}", "--kind", NOTE, *READY)                           # xx-1
            self.run_in(d, "approve", f"{name * 2}-1", "--source", "Jacob: yes")
            self.run_in(d, "add", f"decide {name}", "--kind", DECISION, "--pointer", "PLAN-x.md §1",  # xx-2
                        "--hinges-on", f"whether {name}", "--recommend", "yes",
                        "--today", f"today: {name} undecided", "--problem", f"problem: {name} waits")

    def run_in(self, d, *args, ok=True):
        return self.todo("-C", d, "--root", self.ws, *args, ok=ok)

    def at_root(self, *args, ok=True):
        return self.todo("-C", self.ws, *args, ok=ok)

    def set_priority(self, target, value):
        if value is None:
            self.at_root("priority", target, "--clear")
        else:
            self.at_root("priority", target, value, "--source", f"Jacob: {target} {value}")

    def doc(self, *args):
        return json.loads(self.at_root(*args, "--json").stdout)

    def ready_ids(self, *extra):
        return [r["local_id"] for r in self.doc("ready", *extra)["ready"]]

    def decision_ids(self, *extra):
        return [r["item"] for r in self.doc("decisions", *extra)["rows"]]

    def dispatchable_ids(self, view):
        return [r["id"].split(":", 1)[1] for r in view["dispatchable"] + view["by_rule"]]

    # -- parked: out of decisions, dispatchable and ready, only in the count ------

    def test_a_parked_projects_items_leave_decisions_and_dispatchable_and_show_only_in_the_count(self):
        # counterfactual first: unparked, b's items are there
        self.assertIn("bb-2", self.decision_ids())
        self.assertIn("bb-1", self.dispatchable_ids(self.doc("dispatchable")))
        self.assertIn("bb-1", self.ready_ids())
        self.set_priority("pj-2", PARKED)
        dec = self.doc("decisions")
        self.assertEqual([r["item"] for r in dec["rows"]], ["aa-2", "cc-2"])
        self.assertEqual(dec["untabled"], [{"priority": PARKED, "project": None, "count": 1}])
        disp = self.doc("dispatchable")
        listed = json.dumps({k: disp[k] for k in ("dispatchable", "by_rule", "held", "dispatched")})
        self.assertNotIn("bb-", listed, "a parked item is in no list of dispatchable, only the count")
        self.assertEqual(disp["priority_out"], [{"priority": PARKED, "count": 2}], "bb-1 and the decision bb-2")
        ready = self.doc("ready")
        self.assertNotIn("bb-1", [r["local_id"] for r in ready["ready"]])
        self.assertEqual(ready["priority_out"], [{"priority": PARKED, "count": 1}])
        # the text forms say the count, and name none of b's items
        for verb, says in (("decisions", f"1 {PARKED}"), ("dispatchable", f"2 {PARKED}"), ("ready", f"1 {PARKED}")):
            with self.subTest(verb=verb):
                out = self.at_root(verb).stdout
                self.assertIn(says, out)
                self.assertNotIn("bb-1", out)
                self.assertNotIn("decide b", out)
        # brief agrees with dispatchable: a parked item is NOT READY, and says why
        r = self.at_root("brief", "bb-1", ok=False)
        self.assertIn("NOT READY", r.stdout)
        self.assertIn(f"priority {PARKED} (from pj-2): never dispatched", r.stdout)

    def test_an_items_own_parked_wins_over_a_dispatched_project(self):
        self.run_in(self.dirs["a"], "priority", "aa-1", PARKED, "--source", "Jacob: not aa-1")
        self.assertNotIn("aa-1", self.ready_ids())
        self.assertNotIn("aa-1", self.dispatchable_ids(self.doc("dispatchable")))
        self.assertIn("aa-2", self.decision_ids(), "the project is not parked: its decision stays")

    # -- order --------------------------------------------------------------------

    def test_later_items_come_after_every_now_and_next_item_in_ready(self):
        self.set_priority("pj-1", LATER)
        self.set_priority("pj-3", NOW)
        self.run_in(self.dirs["b"], "add", "later in b", "--kind", NOTE, *READY)                  # bb-3
        self.run_in(self.dirs["b"], "priority", "bb-3", LATER, "--source", "Jacob: bb-3 later")
        rows = self.doc("ready")["ready"]
        prios = [r["priority"] for r in rows]
        self.assertEqual(sorted(prios, key=ORDER.index), prios, "ready is in vocab.json's priority order")
        first_later = prios.index(LATER)
        self.assertEqual(set(prios[first_later:]), {LATER}, prios)
        self.assertEqual([r["local_id"] for r in rows], ["cc-1", "bb-1", "aa-1", "bb-3"])
        self.assertEqual([r["priority_from"] for r in rows], ["pj-3", None, "pj-1", "own"])
        # the text form in the same order, each line with its priority
        lines = [ln.split() for ln in self.at_root("ready").stdout.splitlines() if ln[:2] in ("aa", "bb", "cc")]
        self.assertEqual([(ln[0], ln[4]) for ln in lines], [(r["local_id"], r["priority"]) for r in rows])
        # list orders the same way, dispatchable too
        self.assertEqual([r["local_id"] for r in self.doc("list", "--all")["items"]][:2], ["cc-1", "cc-2"])
        self.assertEqual(self.dispatchable_ids(self.doc("dispatchable")), ["cc-1", "bb-1", "aa-1"])

    def test_a_later_decision_is_counted_per_project_and_decisions_sort_by_priority_first(self):
        self.assertEqual(self.decision_ids(), ["aa-2", "bb-2", "cc-2"], "none frees more: by repo, as before")
        self.set_priority("pj-3", NOW)
        self.assertEqual(self.decision_ids(), ["cc-2", "aa-2", "bb-2"])
        self.set_priority("pj-1", LATER)
        dec = self.doc("decisions")
        self.assertEqual([r["item"] for r in dec["rows"]], ["cc-2", "bb-2"])
        self.assertEqual([r["priority"] for r in dec["rows"]], [NOW, NEXT])
        self.assertEqual(dec["untabled"], [{"priority": LATER, "project": "pj-1", "count": 1}])
        self.assertIn(f"1 {LATER} in pj-1", self.at_root("decisions").stdout)

    def test_changing_a_projects_priority_changes_the_order_of_ready(self):
        """The input changes the output, and putting it back restores it."""
        before = self.ready_ids()
        self.assertEqual(before, ["aa-1", "bb-1", "cc-1"])
        self.set_priority("pj-3", NOW)
        self.assertEqual(self.ready_ids(), ["cc-1", "aa-1", "bb-1"])
        self.set_priority("pj-1", LATER)
        self.assertEqual(self.ready_ids(), ["cc-1", "bb-1", "aa-1"])
        self.set_priority("pj-3", None)
        self.set_priority("pj-1", None)
        self.assertEqual(self.ready_ids(), before)

    # -- --area ---------------------------------------------------------------------

    def test_area_keeps_the_items_whose_effective_areas_hold_it(self):
        self.assertEqual(self.ready_ids("--area", "lifestyle"), ["bb-1"])
        self.assertEqual(self.ready_ids("--area", "devtools"), ["aa-1", "cc-1"])
        self.assertEqual(self.decision_ids("--area", "lifestyle"), ["bb-2"])
        self.assertEqual(self.dispatchable_ids(self.doc("dispatchable", "--area", "lifestyle")), ["bb-1"])
        self.assertEqual([r["local_id"] for r in self.doc("list", "--all", "--area", "lifestyle")["items"]],
                         ["bb-1", "bb-2"])
        # an item's own area: replaces its project's
        self.run_in(self.dirs["a"], "area", "aa-1", "lifestyle")
        self.assertEqual(self.ready_ids("--area", "lifestyle"), ["aa-1", "bb-1"])
        self.assertEqual(self.ready_ids("--area", "devtools"), ["cc-1"])

    def test_an_area_the_table_does_not_hold_is_refused_by_every_read(self):
        for verb in ("list", "ready", "decisions", "dispatchable"):
            with self.subTest(verb=verb):
                r = self.at_root(verb, "--area", "nope", ok=False)
                self.assertIn("no such area", r.stderr)

    # -- brief and projects ------------------------------------------------------

    def brief_priority(self, iid, ok=True):
        out = self.at_root("brief", iid, ok=ok).stdout
        return next(ln.split(": ", 1)[1] for ln in out.splitlines() if ln.startswith("Priority: "))

    def test_brief_prints_the_effective_priority_and_its_source(self):
        self.assertEqual(self.brief_priority("aa-1"), f"{NEXT} (the default: pj-1, by its repo a, has none set)")
        self.set_priority("pj-1", NOW)
        self.assertEqual(self.brief_priority("aa-1"),
                         f'{NOW} (from pj-1 pa, by its repo a: {VOCAB.approval_by} 2026-10-04, "Jacob: pj-1 {NOW}")')
        self.run_in(self.dirs["a"], "priority", "aa-1", LATER, "--source", "Jacob: aa-1 can wait")
        self.assertEqual(self.brief_priority("aa-1"),
                         f'{LATER} (its own: {VOCAB.approval_by} 2026-10-04, "Jacob: aa-1 can wait")')
        d = self.repo("d", "dd")
        self.run_in(d, "add", "no project", "--kind", NOTE, *READY)
        self.assertEqual(self.brief_priority("dd-1", ok=None),
                         f"{NEXT} (the default: no project names its plan or its repo d)")

    def test_projects_prints_open_ready_and_parked_counts(self):
        self.set_priority("pj-2", PARKED)
        d = self.repo("d", "dd")
        self.run_in(d, "add", "no project", "--kind", NOTE)
        doc = self.doc("projects")
        counts = {p["id"]: p["counts"] for p in doc["projects"]}
        self.assertEqual({k: (c["items"], c["ready"], c["by_priority"][PARKED]) for k, c in counts.items()},
                         {"pj-1": (2, 1, 0), "pj-2": (2, 0, 2), "pj-3": (2, 1, 0)})
        self.assertEqual(counts["pj-1"]["by_priority"], {NOW: 0, NEXT: 2, LATER: 0, PARKED: 0})
        self.assertEqual(doc["no_project"]["items"], 1)
        out = self.at_root("projects").stdout
        self.assertIn(f"(open 2, ready 0, {PARKED} 2)", out)
        self.assertIn(f"(open 2, ready 1, {PARKED} 0)", out)
        self.assertIn(f"in no project: open 1, ready 0, {PARKED} 0", out)
        # the input changes the output: unparked, b's item is ready again
        self.set_priority("pj-2", None)
        counts = {p["id"]: p["counts"] for p in self.doc("projects")["projects"]}
        self.assertEqual((counts["pj-2"]["ready"], counts["pj-2"]["by_priority"][PARKED]), (1, 0))


class Unread(Case):
    """With no store at the scan root the priority is unknown: every read keeps the
    item in, in the store's order, says null in its JSON and says why on stderr;
    --area is refused (there is no table to judge it by)."""

    def test_no_table_keeps_items_in_and_says_unknown(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "x", "--kind", NOTE, *READY)
        r = self.todo("-C", a, "ready", "--json")
        doc = json.loads(r.stdout)
        self.assertEqual([(x["local_id"], x["priority"]) for x in doc["ready"]], [("aa-1", None)])
        self.assertTrue(doc["priority_unread"])
        self.assertIn("priority unknown", r.stderr)
        self.assertIn("unknown", next(ln for ln in self.todo("-C", a, "brief", "aa-1", ok=None).stdout.splitlines()
                                      if ln.startswith("Priority: ")))
        r = self.todo("-C", a, "ready", "--area", "devtools", ok=False)
        self.assertIn("no store at the scan root", r.stderr)


class Behaviour(Case):
    """vocab.json's priority behaviour is what the reads consume: a value missing it,
    or saying it wrong, does not load."""

    def test_a_priority_value_without_its_behaviour_does_not_load(self):
        raw = json.loads(Path(VOCAB_PATH).read_text())
        values = raw["priority"]["values"]

        def without(value, **change):
            spec = {k: v for k, v in dict(values[value], **change).items() if v is not None}
            return dict(raw, priority=dict(raw["priority"], values=dict(values, **{value: spec})))

        for name, bad in (("no tabled", without(NOW, tabled=None)), ("no dispatched", without(NOW, dispatched=None)),
                          ("untabled, no count", without(LATER, count=None)),
                          ("tabled with a count", without(NOW, count="project")),
                          ("count not project or total", without(LATER, count="repo")),
                          ("a key nothing reads", without(NOW, rank=1)),
                          ("a default that hides", without(NEXT, dispatched=False))):
            with self.subTest(name=name):
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                    json.dump(bad, fh)
                try:
                    with self.assertRaises(ValueError):
                        Vocab(Path(fh.name))
                finally:
                    os.unlink(fh.name)
        self.assertEqual(Vocab(Path(VOCAB_PATH)).priorities, VOCAB.priorities, "the real one loads")

    def test_the_reader_reads_each_behaviour_from_the_vocabulary(self):
        """tables.Reader with no CLI: an item's own priority, and the default."""
        class WS:
            root, stores = Path("/nowhere"), []
        r = tables.Reader(WS())
        own = {"id": "x-1", "priority": {"value": PARKED, "source": "s", "by": VOCAB.approval_by, "date": "2026-10-04"}}
        self.assertEqual((r.value(own, "x"), r.dispatched(own, "x"), r.tabled(own, "x")), (PARKED, False, False))
        unset = {"id": "x-2"}
        self.assertEqual((r.value(unset, "x"), r.rank(unset, "x"), r.dispatched(unset, "x")),
                         (None, ORDER.index(NEXT), True), "unknown: ordered and kept as the default, never guessed")
