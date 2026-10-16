"""Plans generate their items (PLAN-services.md §3 G6, §4 step 6.3; README "Plan
steps"). `todo sync-plans` reads each plan's steps through the setup tool's
`plans steps --json`, makes a plan-step item per owned step, keeps it in step as
the plan changes, and lists what it will not change.

These run the real setup tool (found the way the CLI finds it by default), so the
seam with its step parser is what is tested: a stub would agree with this module
by construction. Each kind of change has a passing and a failing case."""
import json

from tests.helpers import Case
from todolib import plans, syncplans
from todolib.vocab import VOCAB

STEP = VOCAB.role("plan_step_kind")
NOTE = VOCAB.role("default_kind")
DECISION = VOCAB.role("decision_kind")
WAITING = VOCAB.jacob_status
OPEN = VOCAB.role("default_status")
APPROVAL = VOCAB.role("approval_waits_on")


def plan(*steps, intro="one"):
    """A plan whose §2 holds the steps given (each a line of G1's grammar)."""
    return f"# X\n\n## 1. First\n\n{intro}\n\n## 2. Steps\n\n" + "\n".join(steps) + "\n"


class Sync(Case):
    def setUp(self):
        super().setUp()
        cli, why = plans.resolve_cli(None)
        if why:
            self.fail(f"these tests read plans through the setup tool: {why}")
        self.a = self.repo("a", "aa")
        self.plan = self.ws / "PLAN-x.md"

    def write(self, *steps, **kw):
        self.plan.write_text(plan(*steps, **kw))

    def sync(self, *extra, repo=None, ok=True):
        r = self.todo("-C", repo or self.a, "--root", self.ws, "sync-plans", "--json", *extra, ok=ok)
        return json.loads(r.stdout) if r.stdout.strip() else None, r

    def items(self, repo=None, kind=STEP):
        return [it for it in self.store(repo or self.a)["items"] if it["kind"] == kind]

    def acts(self, out, action):
        return [a for a in out["actions"] if a["action"] == action]


class New(Sync):
    def test_an_owned_step_gets_one_item_waiting_on_his_approval(self):
        self.write("1. `a`: **Build the thing.** It does a lot.")
        out, _ = self.sync()
        [it] = self.items()
        self.assertEqual(it["title"], "Build the thing")
        self.assertEqual((it["status"], it["waits_on"], it["approved"]), (WAITING, APPROVAL, None))
        self.assertEqual(it["plan_step"]["file"], "PLAN-x.md")
        self.assertEqual((it["plan_step"]["section"], it["plan_step"]["step"]), ("2", "1"))
        self.assertEqual(it["tags"], [f"{plans.namespace()}:PLAN-x.md§2"])
        self.assertEqual([p["plan"] for p in it["plan_pins"]], ["PLAN-x.md§2"])
        self.assertIsNone(it["blocked_by"], "a generated item never blocks")
        self.assertEqual([a["id"] for a in self.acts(out, syncplans.NEW)], [f"todo:{it['id']}"])
        self.check(self.a)

    def test_a_second_run_changes_nothing(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        before = self.store(self.a)
        out, _ = self.sync()
        self.assertEqual(out["actions"], [])
        self.assertEqual(self.store(self.a), before)

    def test_a_step_owned_by_a_repo_with_no_store_is_listed_not_made(self):
        self.write("1. `zz`: Build the thing.", "2. no owner here.")
        out, _ = self.sync()
        self.assertEqual(self.items(), [])
        whys = [a["detail"] for a in self.acts(out, syncplans.LISTED)]
        self.assertEqual(len(whys), 2, whys)
        self.assertIn("no scanned store for owner zz", whys)

    def test_a_step_with_sub_steps_is_silent_and_its_sub_steps_are_made(self):
        self.write("1. **Group**, in this order:", "   1. `a`: first part.", "   2. `a`: second part.")
        out, _ = self.sync()
        self.assertEqual(sorted(it["plan_step"]["step"] for it in self.items()), ["1.1", "1.2"])
        self.assertEqual(self.acts(out, syncplans.LISTED), [])

    def test_dry_run_writes_nothing_and_says_what_it_would_make(self):
        self.write("1. `a`: Build the thing.")
        before = self.store(self.a)
        out, _ = self.sync("--dry-run")
        self.assertTrue(out["dry_run"])
        self.assertEqual(len(self.acts(out, syncplans.NEW)), 1)
        self.assertEqual(self.store(self.a), before)

    def test_a_closed_items_step_gets_no_new_item(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        [it] = self.items()
        self.todo("-C", self.a, "done", it["id"], "--resolution", "done")
        [closed] = self.history(self.a)["items"]
        self.assertEqual(closed["plan_step"], it["plan_step"], "history keeps the plan step whole")
        shown = self.todo("-C", self.a, "history", it["id"]).stdout
        self.assertIn(f"hash={it['plan_step']['hash']}", shown)  # show gives it whole
        out, _ = self.sync()
        self.assertEqual((self.items(), out["actions"]), ([], []))

    def test_by_hand_none_is_made_and_none_changes_kind(self):
        def refused(*args, says):
            r = self.todo("-C", self.a, *args, ok=False)
            self.assertIn(says, r.stderr, "refused by its own guard, not by a later gate")

        refused("add", "t", "--kind", STEP, says="never by hand")
        self.write("1. `a`: Build the thing.")
        self.sync()
        [it] = self.items()
        refused("edit", it["id"], "--kind", NOTE, says="made and kept by todo sync-plans")
        self.todo("-C", self.a, "add", "n", "--kind", NOTE)
        refused("edit", "aa-2", "--kind", STEP, says="made and kept by todo sync-plans")
        refused("report", it["id"], "--to", "elsewhere", says="stays one (todo sync-plans keeps it)")

    def test_a_retag_the_parser_hashed_is_still_no_change_of_the_step(self):
        """Should the setup parser one day hash the track tag too, a re-tag reads as a
        changed step: the sync compares the text without it, so it is still no change."""
        rec = {"file": "PLAN-x.md", "section": "2", "step": "1", "text": "`a`: Build the thing.", "hash": "0" * 64}
        it = {"title": "Build the thing", "status": OPEN, "waits_on": None,
              "plan_step": {k: rec[k] for k in syncplans.FIELDS}, "tags": [syncplans.tag_of(rec)]}
        st = dict(rec, text=rec["text"] + ' track: TODO.md "Build"', hash="1" * 64, parent=None,
                  owners=["a"], track=None, placeable=True)
        changes, stale = syncplans._changes(it, st, "changed", {}, lambda ref: (plans.OK, "d"), [], "2026-10-04")
        self.assertFalse(stale)
        self.assertNotIn("title", changes)
        self.assertNotIn("evidence", changes)

    def test_a_split_step_keeps_one_step_item_and_plain_children(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        [it] = self.items()
        self.todo("-C", self.a, "split", it["id"], "one", "two", "--size", list(VOCAB.ready_sizes)[0])
        self.assertEqual(len(self.items()), 1)
        self.assertEqual(len(self.items(kind=NOTE)), 2)
        out, _ = self.sync()
        self.assertEqual(self.acts(out, syncplans.GONE), [])


class Approved(Sync):
    def test_approval_on_the_step_or_a_step_above_makes_it_open_and_approved(self):
        self.write("1. **Group (approved: Jacob 2026-10-02)**, in this order:", "   1. `a`: first part.")
        self.sync()
        [it] = self.items()
        self.assertEqual((it["status"], it["waits_on"]), (OPEN, None))
        self.assertEqual(it["approved"]["date"], "2026-10-02")
        self.assertEqual(it["approved"]["by"], VOCAB.approval_by)
        self.assertIn("PLAN-x.md §2 step 1", it["approved"]["source"])
        self.check(self.a)

    def test_an_approval_added_later_opens_a_waiting_item(self):
        self.write("1. `a`: first part.")
        self.sync()
        self.write("1. `a`: first part (approved: Jacob 2026-10-03).")
        self.sync()
        [it] = self.items()
        self.assertEqual((it["status"], it["approved"]["date"]), (OPEN, "2026-10-03"))

    def test_a_status_a_person_set_is_left_alone(self):
        self.write("1. `a`: first part.")
        self.sync()
        [it] = self.items()
        self.todo("-C", self.a, "edit", it["id"], "--status", VOCAB.role("default_status"))
        self.write("1. `a`: first part. track: needs-yes PLAN-x.md §1")
        self.sync()
        self.assertEqual(self.items()[0]["status"], OPEN)


class NeedsYes(Sync):
    def test_a_needs_yes_step_waits_on_that_decision_made_once(self):
        self.write("1. `a`: first part. track: needs-yes PLAN-x.md §1",
                   "2. `a`: second part. track: needs-yes PLAN-x.md §1")
        out, _ = self.sync()
        steps = self.items()
        self.assertEqual({it["waits_on"] for it in steps}, {"decision:PLAN-x.md §1"})
        [d] = self.items(kind=DECISION)
        self.assertEqual((d["pointer"], d["status"], d["recommend"]),
                         ("PLAN-x.md §1", WAITING, VOCAB.decisions["generated_recommend"]))
        self.assertIn("step 1", d["hinges_on"])
        self.assertIn("step 2", d["hinges_on"])
        self.assertEqual(len(self.acts(out, syncplans.DECISION)), 1)
        out, _ = self.sync()
        self.assertEqual(len(self.items(kind=DECISION)), 1, "a second run makes no second decision")
        self.check(self.a)
        tabled = json.loads(self.todo("-C", self.a, "--root", self.ws, "decisions", "--json").stdout)
        self.assertEqual([r["item"] for r in tabled["rows"]], [d["id"]])

    def test_a_decision_already_held_anywhere_is_not_made_again(self):
        self.write("1. `a`: first part. track: needs-yes PLAN-x.md §1")
        b = self.repo("b", "bb")
        self.todo("-C", b, "--root", self.ws, "add", "held", "--kind", DECISION,
                  "--pointer", "PLAN-x.md §1", "--hinges-on", "h", "--recommend", "yes")
        out, _ = self.sync()
        self.assertEqual(self.items(kind=DECISION), [])
        self.assertEqual(self.acts(out, syncplans.DECISION), [])
        self.assertEqual(self.items()[0]["waits_on"], "decision:PLAN-x.md §1")

    def test_a_decision_at_a_section_that_does_not_read_is_a_notice_not_an_item(self):
        self.write("1. `a`: first part. track: needs-yes PLAN-x.md §9")
        out, _ = self.sync()
        self.assertEqual(self.items(kind=DECISION), [])
        self.assertTrue(any("PLAN-x.md §9" in n for n in out["notices"]), out["notices"])


class Renumbered(Sync):
    def test_an_inserted_step_renumbers_the_items_after_it(self):
        self.write("1. `a`: Build the thing.", "2. `a`: Test the thing.")
        self.sync()
        ids = {it["plan_step"]["step"]: it["id"] for it in self.items()}
        self.write("1. `a`: Plan the thing.", "2. `a`: Build the thing.", "3. `a`: Test the thing.")
        out, _ = self.sync()
        now = {it["title"]: (it["id"], it["plan_step"]["step"]) for it in self.items()}
        self.assertEqual(now["Build the thing"], (ids["1"], "2"))
        self.assertEqual(now["Test the thing"], (ids["2"], "3"))
        self.assertEqual(len(self.acts(out, syncplans.RENUMBERED)), 2)
        self.assertEqual(len(self.acts(out, syncplans.NEW)), 1)
        self.assertEqual(self.acts(out, syncplans.STALE), [], "matched by hash, nothing reads as changed")


class Stale(Sync):
    def test_a_changed_step_updates_mechanical_fields_and_is_listed_stale(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        [it] = self.items()
        self.todo("-C", self.a, "edit", it["id"], "--done-when", "it builds")
        self.write("1. `a`: Build the other thing.")
        out, _ = self.sync()
        [now] = self.items()
        self.assertEqual(now["id"], it["id"])
        self.assertEqual(now["title"], "Build the other thing")
        self.assertEqual(now["done_when"], "it builds", "judgement fields are the owner's")
        self.assertIn("it was: `a`: Build the thing.", now["evidence"])
        self.assertNotEqual(now["plan_step"]["hash"], it["plan_step"]["hash"])
        [st] = self.acts(out, syncplans.STALE)
        self.assertIn("was: `a`: Build the thing. | now: `a`: Build the other thing.", st["detail"])
        self.check(self.a)

    def test_a_new_track_tag_alone_is_no_change_of_the_step(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        self.write('1. `a`: Build the thing. track: TODO.md "Elsewhere"')
        out, _ = self.sync()
        self.assertEqual(self.acts(out, syncplans.STALE), [])
        [it] = self.items()
        self.assertIn("track:", it["plan_step"]["text"], "the step is kept as the plan holds it now")


class Flagged(Sync):
    def test_a_dispatched_item_is_never_changed_only_flagged(self):
        self.write("1. `a`: Build the thing (approved: Jacob 2026-10-02).")
        self.sync()
        [it] = self.items()
        self.todo("-C", self.a, "dispatch", it["id"])
        before = self.items()
        self.write("1. `a`: Build the other thing (approved: Jacob 2026-10-02).")
        out, _ = self.sync()
        self.assertEqual(self.items(), before)
        [f] = self.acts(out, syncplans.FLAGGED)
        self.assertIn("title", f["detail"])

    def test_an_undispatched_item_is_changed(self):
        self.write("1. `a`: Build the thing (approved: Jacob 2026-10-02).")
        self.sync()
        self.write("1. `a`: Build the other thing (approved: Jacob 2026-10-02).")
        out, _ = self.sync()
        self.assertEqual(self.acts(out, syncplans.FLAGGED), [])
        self.assertEqual(self.items()[0]["title"], "Build the other thing", "his yes is no part of a title")


class Gone(Sync):
    def test_a_removed_steps_item_is_listed_gone_and_stays_open(self):
        self.write("1. `a`: Build the thing.", "2. `a`: Test the thing.")
        self.sync()
        self.write("1. `a`: Build the thing.")
        out, _ = self.sync()
        [g] = self.acts(out, syncplans.GONE)
        self.assertEqual(len(self.items()), 2, "never closed by the sync")
        self.assertIn("Test the thing", g["title"])

    def test_a_full_run_judges_the_items_of_a_plan_file_no_longer_there(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        self.plan.unlink()
        out, _ = self.sync()
        self.assertEqual(len(self.acts(out, syncplans.GONE)), 1)

    def test_a_run_naming_other_plans_judges_none_of_this_ones(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        (self.ws / "PLAN-y.md").write_text(plan("1. `a`: Other."))
        self.plan.unlink()
        out, _ = self.sync(str(self.ws / "PLAN-y.md"))
        self.assertEqual(self.acts(out, syncplans.GONE), [])


class Listed(Sync):
    def test_a_step_tracked_in_a_hand_written_file_is_listed_not_made(self):
        self.write('1. `a`: Build the thing. track: TODO.md "Build"')
        out, _ = self.sync()
        self.assertEqual(self.items(), [])
        [l] = self.acts(out, syncplans.LISTED)
        self.assertIn("TODO.md", l["detail"])

    def test_a_step_tracked_by_an_item_id_is_skipped(self):
        self.write("1. `a`: Build the thing. track: todo:a#aa-1")
        out, _ = self.sync()
        self.assertEqual((self.items(), out["actions"]), ([], []))

    def test_the_text_output_is_capped_per_kind_of_change(self):
        n = syncplans.spec()["max_listed"] + 2
        self.write(*[f"{i}. `zz`: step {i}." for i in range(1, n + 1)])
        r = self.todo("-C", self.a, "--root", self.ws, "sync-plans", "--dry-run")
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith(syncplans.LISTED)]
        self.assertEqual(len(lines), syncplans.spec()["max_listed"] + 1, r.stdout)
        self.assertIn("+2 more", lines[-1])


class FailsOpen(Sync):
    def test_no_plans_cli_is_one_notice_and_exit_0(self):
        self.write("1. `a`: Build the thing.")
        before = self.store(self.a)
        r = self.todo("-C", self.a, "--root", self.ws, "sync-plans", "--plans-cli", self.tmp / "none")
        self.assertIn("NOTICE", r.stderr)
        self.assertEqual(self.store(self.a), before)

    def test_an_unreadable_plan_is_a_notice_and_its_items_are_not_judged(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        bad = self.ws / "PLAN-y.md"
        bad.write_text(plan("1. `a`: Other."))
        bad.chmod(0)
        try:
            out, r = self.sync(str(bad), str(self.plan))
        finally:
            bad.chmod(0o644)
        self.assertTrue(any("PLAN-y.md" in n for n in out["notices"]), out["notices"])
        self.assertEqual(out["plans"], 1)

    def test_a_full_run_leaves_the_items_of_an_unreadable_plan_alone(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        self.plan.chmod(0)
        try:
            out, _ = self.sync()
        finally:
            self.plan.chmod(0o644)
        self.assertEqual(out["actions"], [], "a plan not read is no plan emptied")
        self.assertTrue(any("PLAN-x.md" in n for n in out["notices"]), out["notices"])

    def test_a_hand_edited_store_keeps_its_changes_back(self):
        self.write("1. `a`: Build the thing.")
        render = self.a / "TODO.md"
        render.chmod(0o644)
        render.write_text(render.read_text() + "\nhand\n")
        before = self.store(self.a)
        out, _ = self.sync()
        self.assertEqual(self.store(self.a), before)
        self.assertTrue(any("nothing written" in n for n in out["notices"]), out["notices"])
        self.assertEqual(self.acts(out, syncplans.NEW), [])


class Cites(Sync):
    def test_list_cites_finds_tags_steps_and_pointers_in_and_under_a_section(self):
        self.write("1. `a`: Build the thing. track: needs-yes PLAN-x.md §1")
        self.sync()
        self.todo("-C", self.a, "add", "tagged", "--kind", NOTE, "--tags", "plan:PLAN-x.md§2.1")
        self.todo("-C", self.a, "add", "elsewhere", "--kind", NOTE, "--tags", "plan:PLAN-x.md§3")
        self.todo("-C", self.a, "add", "twenty", "--kind", NOTE, "--tags", "plan:PLAN-x.md§20")

        def cited(c):
            out = self.todo("-C", self.a, "--root", self.ws, "list", "--cites", c).stdout
            return sorted(ln.split()[0] for ln in out.splitlines() if not ln.startswith("("))

        step, = [it["id"] for it in self.items()]
        dec, = [it["id"] for it in self.items(kind=DECISION)]
        self.assertEqual(cited("PLAN-x.md §2"), sorted([step, "aa-3"]))
        self.assertEqual(cited("PLAN-x.md§1"), [dec])
        self.assertEqual(cited("PLAN-x.md §2.1"), ["aa-3"])
        self.assertEqual(len(cited("PLAN-x.md")), 5)
        self.assertEqual(cited("PLAN-y.md §2"), [])
        self.todo("-C", self.a, "list", "--cites", "nowhere", ok=False)


class Checked(Sync):
    def test_check_fails_a_plan_step_on_another_kind_and_a_bad_one(self):
        self.write("1. `a`: Build the thing.")
        self.sync()
        data = self.store(self.a)
        data["items"][0]["plan_step"]["hash"] = "nothash"
        self.write_json(self.a / "todo.json", data)
        out = self.check(self.a, ok=False).stdout
        self.assertIn("plan_step.hash is not a sha256 hex digest", out)
        data["items"][0]["plan_step"]["hash"] = "0" * 64
        data["items"][0]["kind"] = NOTE
        self.write_json(self.a / "todo.json", data)
        out = self.check(self.a, ok=False).stdout
        self.assertIn(f"plan_step is set on a {NOTE}", out)

    def test_a_record_the_parser_did_not_promise_refuses_the_whole_plan(self):
        good = {"file": "PLAN-x.md", "section": "2", "step": "1", "parent": None, "text": "t",
                "hash": "0" * 64, "owners": ["a"], "track": None, "placeable": True}
        self.assertIsNone(syncplans.record_problem(good))
        self.assertIn("hash", syncplans.record_problem(dict(good, hash="x")))
        self.assertIn("lacks", syncplans.record_problem({k: v for k, v in good.items() if k != "owners"}))
        self.assertIn("track kind", syncplans.record_problem(dict(good, track={"kind": "odd", "fields": {}})))
