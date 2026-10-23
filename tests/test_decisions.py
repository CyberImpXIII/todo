"""Decisions (PLAN-todo-tool.md §10.3, §10.3a, §10.3b; README "Decisions"): a
decision carries its plan section (FILE §n, which must resolve), what it hinges
on and the recommended answer; `todo decisions` tables the open ones for Jacob,
numbered 1..n and recorded as dt-N; `todo approve` / `todo done --as rejected` /
`todo answer` close them. An approval frees what the decision blocked into
dispatchable; a rejection frees nothing and puts each item it blocked back to
waiting on him, on that decision.

Pointers resolve through the real setup tool, as the CLI finds it by default."""
import json
import os
import re
from pathlib import Path

from tests.helpers import TODAY, Case, git_commit
from todolib import decisions as decide
from todolib import plans
from todolib.store import RECORDS_FILE, new_item, sealed
from todolib.vocab import VOCAB

DECISION = VOCAB.role("decision_kind")
NOTE = VOCAB.role("default_kind")
ACCEPTED = VOCAB.role("decision_accepted_resolution")
CHOSEN = VOCAB.role("decision_option_resolution")
REJECTED = VOCAB.role("decision_rejected_resolution")
D = VOCAB.decisions
READY = ["--work", next(iter(VOCAB.works)), "--done-when", "dw", "--size", VOCAB.ready_sizes[0]]
PLAN = "# X\n\n## 1. First\n\none\n\n## 2. Second\n\ntwo\n\n## 3. Third\n\nthree\n"
LATER = "2026-10-05"
# A plan's Decisions table, as its question gate reads one (PLAN-todo-tool.md §10.3):
# the decision cell starts FILE.md §n, recommend is yes, no, or a part of the hinges cell.
HEADER = "| # | decision | hinges on | recommend |"
SEPARATOR = "|---|---|---|---|"
POINTER_CELL = re.compile(r"^[A-Za-z0-9_./-]+\.md[\s,]+§\s*[0-9]+")


class Base(Case):
    def setUp(self):
        super().setUp()
        _, why = plans.resolve_cli(None)
        if why:
            self.fail(f"these tests read plans through the setup tool: {why}")
        (self.ws / "PLAN-x.md").write_text(PLAN)
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")

    def run_in(self, repo, *args, ok=True, today=TODAY):
        return self.todo("-C", repo, "--root", self.ws, *args, ok=ok, today=today)

    def decide(self, title, section=1, recommend="yes", repo=None, options=(), ok=True, extra=()):
        args = ["add", title, "--kind", DECISION, "--pointer", f"PLAN-x.md §{section}",
                "--hinges-on", f"whether {title}", "--recommend", recommend, *extra]
        for o in options:
            args += ["--option", o]
        return self.run_in(repo or self.a, *args, ok=ok)

    def child(self, title, blocker, repo=None):
        self.run_in(repo or self.a, "add", title, "--kind", NOTE, *READY, "--blocked-by", blocker)

    def item(self, repo, iid):
        hit = [it for it in self.store(repo)["items"] + self.history(repo)["items"] if it["id"] == iid]
        return hit[0] if hit else None

    def dispatchable(self, repo=None):
        r = self.run_in(repo or self.a, "dispatchable", "--json")
        return sorted(x["id"] for x in json.loads(r.stdout)["dispatchable"])

    def table(self, *extra, repo=None, ok=True, today=TODAY):
        r = self.run_in(repo or self.a, "decisions", "--json", *extra, ok=ok, today=today)
        return json.loads(r.stdout)

    def records(self, repo=None):
        return json.loads((Path(repo or self.a) / RECORDS_FILE).read_text())

    def plant_legacy(self, repo=None, ids=("aa-1",)):
        """Open decisions written before their fields existed (as an import leaves one):
        add refuses to make one, so they are planted, replacing the store's items."""
        repo = repo or self.a
        data = self.store(repo)
        data["items"] = [new_item(id=i, title=f"legacy {i}", kind=DECISION, status=VOCAB.role("default_status"),
                                  added=TODAY) for i in ids]
        data["next"] = len(ids) + 1
        self.write_json(repo / "todo.json", data)
        self.run_in(repo, "render", "--force")


class Add(Base):
    def test_a_decision_is_added_waiting_on_jacob_with_its_fields(self):
        self.decide("use sqlite", options=["a=sqlite", "b=json files"], recommend="a")
        it = self.item(self.a, "aa-1")
        self.assertEqual((it["status"], it["waits_on"]), (D["status"], D["waits_on"]))
        self.assertEqual(it["pointer"], "PLAN-x.md §1")
        self.assertEqual(it["options"], [{"name": "a", "text": "sqlite"}, {"name": "b", "text": "json files"}])
        self.check(self.a)
        shown = self.run_in(self.a, "show", "aa-1").stdout
        self.assertIn("options: a = sqlite; b = json files", shown)

    def test_the_pointer_is_stored_with_a_space_however_given(self):
        self.run_in(self.a, "add", "t", "--kind", DECISION, "--pointer", "PLAN-x.md§2", "--hinges-on", "h",
                    "--recommend", "no")
        self.assertEqual(self.item(self.a, "aa-1")["pointer"], "PLAN-x.md §2")

    def test_each_missing_field_is_refused_by_name(self):
        base = ["add", "t", "--kind", DECISION]
        full = {"--pointer": "PLAN-x.md §1", "--hinges-on": "h", "--recommend": "yes"}
        for drop in full:
            args = base + [x for k, v in full.items() if k != drop for x in (k, v)]
            err = self.run_in(self.a, *args, ok=False).stderr
            self.assertIn(drop, err)
        self.assertEqual(self.store(self.a)["items"], [])

    def test_a_pointer_that_does_not_resolve_is_refused(self):
        err = self.decide("t", section=9, ok=False).stderr
        self.assertIn("PLAN-x.md §9", err)
        err = self.run_in(self.a, "add", "t", "--kind", DECISION, "--pointer", "nowhere", "--hinges-on", "h",
                          "--recommend", "yes", ok=False).stderr
        self.assertIn("FILE §n", err)
        self.assertEqual(self.store(self.a)["items"], [])

    def test_a_recommend_that_is_no_answer_is_refused(self):
        self.assertIn("recommend 'maybe'", self.decide("t", recommend="maybe", ok=False).stderr)
        self.assertIn("recommend 'c'", self.decide("t", recommend="c", options=["a=x", "b=y"], ok=False).stderr)
        self.decide("t", recommend="b", options=["a=x", "b=y"])

    def test_an_option_named_like_an_answer_word_is_refused(self):
        word = D["verdicts"]["no"][0]
        self.assertIn("answer word", self.decide("t", options=[f"{word}=x"], ok=False).stderr)

    def test_decision_fields_on_another_kind_are_refused(self):
        err = self.run_in(self.a, "add", "t", "--kind", NOTE, "--hinges-on", "h", ok=False).stderr
        self.assertIn("hinges_on", err)

    def test_another_status_is_refused(self):
        err = self.decide("t", ok=False, extra=["--status", VOCAB.role("default_status")]).stderr
        self.assertIn(D["status"], err)

    def test_edit_revalidates_the_fields(self):
        self.decide("t")
        self.assertIn("recommend", self.run_in(self.a, "edit", "aa-1", "--recommend", "maybe", ok=False).stderr)
        self.run_in(self.a, "edit", "aa-1", "--pointer", "PLAN-x.md §9", ok=False)
        self.run_in(self.a, "edit", "aa-1", "--pointer", "PLAN-x.md §3")
        self.assertEqual(self.item(self.a, "aa-1")["pointer"], "PLAN-x.md §3")
        # turning a note into a decision needs the fields
        self.run_in(self.a, "add", "n", "--kind", NOTE)
        self.run_in(self.a, "edit", "aa-2", "--kind", DECISION, "--status", D["status"], "--waits-on",
                    D["waits_on"], ok=False)


class Close(Base):
    def test_an_approval_closes_it_and_frees_a_child_into_dispatchable(self):
        self.decide("go")
        self.child("the work", "aa-1")
        self.run_in(self.a, "approve", "aa-2", "--source", "Jacob in chat")
        self.assertEqual(self.dispatchable(), [])
        out = self.run_in(self.a, "approve", "aa-1", "--source", "Jacob in chat").stdout
        self.assertIn("no longer blocks aa-2", out)
        closed = self.item(self.a, "aa-1")
        self.assertEqual((closed["status"], closed["resolution"], closed["chosen"]), (VOCAB.closed, ACCEPTED, None))
        self.assertEqual(closed["approved"]["source"], "Jacob in chat")
        self.assertEqual(self.dispatchable(), ["todo:aa-2"])
        self.check(self.a)

    def test_approve_option_closes_on_that_option_and_a_plain_yes_takes_the_recommended_one(self):
        self.decide("store", options=["a=sqlite", "b=json"], recommend="b")
        self.decide("store2", options=["a=sqlite", "b=json"], recommend="b")
        self.run_in(self.a, "approve", "aa-1", "--source", "s", "--option", "c", ok=False)
        self.run_in(self.a, "approve", "aa-1", "--source", "s", "--option", "a")
        self.run_in(self.a, "approve", "aa-2", "--source", "s")
        self.assertEqual([(self.item(self.a, i)["resolution"], self.item(self.a, i)["chosen"]) for i in ("aa-1", "aa-2")],
                         [(CHOSEN, "a"), (CHOSEN, "b")])
        self.run_in(self.a, "add", "n", "--kind", NOTE)
        self.run_in(self.a, "approve", "aa-3", "--source", "s", "--option", "a", ok=False)
        self.check(self.a)

    def test_a_rejection_frees_nothing_and_requeues_every_dependent_on_the_decision(self):
        self.decide("go", section=2)
        self.child("here", "aa-1")
        self.child("there", "aa-1", repo=self.b)
        out = self.run_in(self.a, "done", "aa-1", "--as", REJECTED, "--reason", "not this quarter").stdout
        self.assertIn("aa-2", out)
        self.assertIn("bb-1", out)
        self.assertEqual(self.item(self.a, "aa-1")["resolution"], REJECTED)
        for repo, iid in ((self.a, "aa-2"), (self.b, "bb-1")):
            it = self.item(repo, iid)
            self.assertEqual((it["status"], it["waits_on"]),
                             (VOCAB.jacob_status, f"{VOCAB.role('decision_waits_on')}:PLAN-x.md §2"))
            self.assertIn("not this quarter", it["evidence"])
            self.check(repo)
        self.assertEqual(self.dispatchable(), [])

    def test_done_as_needs_a_reason_and_a_decision(self):
        self.decide("go")
        self.run_in(self.a, "add", "n", "--kind", NOTE)
        self.run_in(self.a, "done", "aa-1", "--as", REJECTED, ok=False)
        self.assertIn(DECISION, self.run_in(self.a, "done", "aa-2", "--as", REJECTED, "--reason", "r", ok=False).stderr)
        for res in (ACCEPTED, CHOSEN, REJECTED):
            self.assertIn("Jacob's answer", self.run_in(self.a, "done", "aa-1", "--resolution", res, ok=False).stderr)
        self.assertEqual(len(self.store(self.a)["items"]), 2)


class Table(Base):
    def test_the_table_is_the_plan_shape_numbered_and_ordered_by_what_each_frees(self):
        self.decide("small")                       # aa-1 frees nothing
        self.decide("big", section=2)              # aa-2 frees three, one of them in b
        self.child("c1", "aa-2")                   # aa-3
        self.child("c2", "aa-3")                   # aa-4, behind aa-2 through aa-3
        self.child("c3", "aa-2", repo=self.b)
        self.run_in(self.a, "add", "old", "--kind", NOTE)
        out = self.run_in(self.a, "decisions").stdout.splitlines()
        self.assertEqual(out[0], "## Decisions")
        at = out.index(HEADER)
        self.assertEqual(out[at + 1], SEPARATOR)
        rows = [ln for ln in out[at + 2:] if ln.startswith("| ")]
        self.assertEqual(len(rows), 2)
        for n, row in enumerate(rows, 1):
            cells = [c.strip() for c in row.strip("|").split(" | ")]
            self.assertEqual(cells[0], str(n))
            self.assertRegex(cells[1], POINTER_CELL)
            self.assertIn(cells[3], D["verdicts"])
        self.assertIn("PLAN-x.md §2: big", rows[0])
        self.assertFalse([ln for ln in out if ln.rstrip().endswith("?")], "a line ending in ? is a stray question")
        view = self.table()
        self.assertEqual([(r["n"], r["id"], r["frees"]) for r in view["rows"]], [(1, "todo:aa-2", 3), (2, "todo:aa-1", 0)])
        self.assertEqual(view["table"], f"{D['table_prefix']}-1")

    def test_an_options_decision_shows_them_in_the_hinges_cell_and_recommends_one(self):
        self.decide("store", options=["a=sqlite", "b=json files"], recommend="b")
        row = self.table()["rows"][0]
        self.assertIn("options: a = sqlite; b = json files", row["cells"][1])
        self.assertIn(row["cells"][2], row["cells"][1])

    def test_each_render_is_recorded_and_the_same_rows_return_the_same_id(self):
        self.decide("one")
        first = self.table()
        self.assertTrue(first["new"])
        again = self.table(today=LATER)
        self.assertEqual((again["table"], again["new"], again["date"]), (first["table"], False, TODAY))
        self.assertEqual(len(self.records()["tables"]), 1)
        self.decide("two", section=2)
        self.assertEqual(self.table()["table"], f"{D['table_prefix']}-2")
        self.check(self.a)

    def test_from_tables_only_the_still_open_rows_recording_what_each_supersedes(self):
        for s in (1, 2, 3):
            self.decide(f"d{s}", section=s)
        dt1 = self.table()["table"]
        self.run_in(self.a, "approve", "aa-2", "--source", "s")
        self.decide("d4")
        view = self.table("--from", dt1)
        self.assertEqual([r["id"] for r in view["rows"]], ["todo:aa-1", "todo:aa-3"])
        self.assertEqual([r["n"] for r in view["rows"]], [1, 2])
        self.assertEqual(view["supersedes"], [{"n": 1, "table": dt1, "row": 1}, {"n": 2, "table": dt1, "row": 3}])
        self.run_in(self.a, "decisions", "--from", "dt-9", ok=False)

    def test_an_incomplete_decision_is_listed_never_tabled(self):
        self.run_in(self.a, "add", "legacy", "--kind", DECISION, "--status", VOCAB.role("default_status"), ok=False)
        self.plant_legacy()
        view = self.table()
        self.assertEqual((view["rows"], view["table"]), ([], None))
        self.assertEqual([r["id"] for r in view["incomplete"]], ["todo:aa-1"])
        out = self.run_in(self.a, "decisions").stdout
        self.assertIn("todo:aa-1 (pointer, hinges_on, recommend)", out)
        self.assertFalse((self.a / RECORDS_FILE).exists())

    def test_the_untabled_footer_says_whose_they_are_and_that_none_asks_the_reader(self):
        # td-93: '<N> open decision(s) not tabled' read as N questions for Jacob. A store
        # with one tabled and one untabled decision: the table has the one row, and the
        # footer names the untabled one as its owner's, with a count per repo.
        self.plant_legacy()                                   # aa-1, untabled
        self.decide("tabled")                                 # aa-2, a row
        out = self.run_in(self.a, "decisions").stdout
        self.assertIn("| 1 | PLAN-x.md §1: tabled |", out)
        foot = out.split("\n\n")[-1].splitlines()
        self.assertEqual(foot[0], "1 decision item(s) in owners' stores lack row fields (a 1): "
                                  "not questions for you until an owner tables them", out)
        self.assertEqual(foot[1], "for their owners (todo edit ID --pointer --hinges-on --recommend): "
                                  "todo:aa-1 (pointer, hinges_on, recommend)", out)
        self.assertNotIn("not tabled", out, "the old wording, read as the reader's backlog")
        # The counts follow the stores: two more in b put b first, the total 3.
        self.plant_legacy(self.b, ("bb-1", "bb-2"))
        foot = self.run_in(self.a, "decisions").stdout.split("\n\n")[-1].splitlines()
        self.assertTrue(foot[0].startswith("3 decision item(s) in owners' stores lack row fields (b 2, a 1): "), foot)
        # Bounded: past max_listed repos and ids, the rest is counted, never dropped silently.
        lines = decide.untabled_lines([{"id": f"todo:x{i}-1", "repo": f"r{i}", "missing": ["pointer"]} for i in range(3)], n=2)
        self.assertIn("(r0 1, r1 1, ...)", lines[0])
        self.assertTrue(lines[1].endswith("; +1 more (--json lists them)"), lines)
        self.assertEqual(decide.untabled_lines([]), [], "no untabled decision: no footer")


class Answer(Base):
    def setUp(self):
        super().setUp()
        self.decide("go", section=1)                                        # row 1: frees 2
        self.decide("stop", section=2)                                      # row 2: frees 1
        self.decide("store", section=3, options=["a=sqlite", "b=json"], recommend="a")  # row 3
        self.decide("later")                                                # row 4
        self.child("blocked by stop", "aa-2")                               # aa-5
        self.child("blocked by go", "aa-1")                                 # aa-6
        self.child("after that", "aa-6")                                    # aa-7
        view = self.table()
        self.tid = view["table"]
        self.assertEqual([r["id"] for r in view["rows"]], [f"todo:aa-{i}" for i in (1, 2, 3, 4)])

    def test_a_reply_applies_yes_no_and_options_and_keeps_other_words(self):
        out = self.run_in(self.a, "answer", "1) yes 2) no 3) b 4) not yet, ask me after the move?").stdout
        self.assertIn("kept as his words", out)
        self.assertEqual(self.item(self.a, "aa-1")["resolution"], ACCEPTED)
        self.assertIn(f"answer {TODAY} ({self.tid} row 1)", self.item(self.a, "aa-1")["approved"]["source"])
        self.assertEqual(self.item(self.a, "aa-2")["resolution"], REJECTED)
        self.assertEqual(self.item(self.a, "aa-5")["status"], VOCAB.jacob_status)
        self.assertEqual((self.item(self.a, "aa-3")["resolution"], self.item(self.a, "aa-3")["chosen"]), (CHOSEN, "b"))
        later = self.item(self.a, "aa-4")
        self.assertEqual(later["status"], D["status"])
        self.assertEqual(later["jacob_words"], [{"date": TODAY, "table": self.tid, "row": 4,
                                                 "text": "not yet, ask me after the move?"}])
        answers = self.records()["tables"][0]["answers"]
        self.assertEqual([r["verdict"] for r in answers[0]["rows"]], ["yes", "no", "option", "words"])
        self.check(self.a)

    def test_an_unknown_or_repeated_row_refuses_the_whole_reply(self):
        before = self.store(self.a)
        self.assertIn("row 7", self.run_in(self.a, "answer", "1) yes 7) no", ok=False).stderr)
        self.assertIn("twice", self.run_in(self.a, "answer", "1) yes 1) no", ok=False).stderr)
        self.run_in(self.a, "answer", "yes to all", ok=False)
        self.run_in(self.a, "answer", "sure: 1) yes", ok=False)
        self.assertEqual(self.store(self.a)["items"], before["items"])
        self.assertEqual(self.records()["tables"][0]["answers"], [])

    def test_a_row_already_closed_refuses_the_reply(self):
        self.run_in(self.a, "approve", "aa-1", "--source", "s")
        err = self.run_in(self.a, "answer", "1) yes 2) yes", ok=False).stderr
        self.assertIn("closed already", err)
        self.assertEqual(self.item(self.a, "aa-2")["status"], D["status"])

    def test_an_answer_naming_a_table_applies_to_that_table_only(self):
        self.run_in(self.a, "answer", "4) later")
        self.run_in(self.a, "approve", "aa-1", "--source", "s")
        dt2 = self.table("--from", self.tid)["table"]
        # dt-2 row 1 is aa-2; dt-1 row 1 is aa-1 (closed)
        self.run_in(self.a, "answer", f"{self.tid}: 1) yes", ok=False)
        self.run_in(self.a, "answer", f"{dt2}: 1) yes")
        self.assertEqual(self.item(self.a, "aa-2")["resolution"], ACCEPTED)
        self.run_in(self.a, "answer", "1) yes", "--table", "dt-9", ok=False)
        self.run_in(self.a, "answer", f"{self.tid}: 2) no", "--table", dt2, ok=False)

    def test_the_records_gate_holds_a_committed_table_unchanged(self):
        git_commit(self.a)
        self.check(self.a)
        path = self.a / RECORDS_FILE
        data = json.loads(path.read_text())
        data.pop("seal")
        data["tables"][0]["rows"][0]["cells"][2] = "no"
        os.chmod(path, 0o644)
        path.write_text(json.dumps(sealed(data), indent=2) + "\n")
        self.assertFails(self.a, "records", "never changes")
        data["tables"][0]["rows"][0]["cells"][2] = "yes"
        data["tables"] = []
        path.write_text(json.dumps(sealed(data), indent=2) + "\n")
        self.assertFails(self.a, "records", "never removed")

    def test_the_records_gate_holds_a_committed_answer(self):
        self.run_in(self.a, "answer", "4) later")
        git_commit(self.a)
        self.check(self.a)
        path = self.a / RECORDS_FILE
        data = json.loads(path.read_text())
        data.pop("seal")
        data["tables"][0]["answers"] = []
        os.chmod(path, 0o644)
        path.write_text(json.dumps(sealed(data), indent=2) + "\n")
        self.assertFails(self.a, "records", "answers are appended only")


class Checks(Base):
    def test_check_fails_a_decision_resolution_on_another_kind_or_without_approval(self):
        self.run_in(self.a, "add", "n", "--kind", NOTE)
        self.run_in(self.a, "done", "aa-1", "--resolution", "fixed")
        hist = self.history(self.a)
        hist["items"][0]["resolution"] = ACCEPTED
        self.write_json(self.a / "todo-history.json", hist)
        self.run_in(self.a, "render", "--force")
        self.assertFails(self.a, "vocab", f"closes a {DECISION} only")

    def test_check_lists_an_open_decision_lacking_the_fields(self):
        self.plant_legacy()
        out = self.check(self.a).stdout
        self.assertIn("aa-1 (pointer, hinges_on, recommend)", out)
