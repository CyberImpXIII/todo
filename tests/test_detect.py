"""Detectors (PLAN-todo-tool.md §10.5; README "Detectors"): `todo detect` turns each
finding into one item keyed detector:<id>:<repo>:<subject>, updates it while the
finding stays, closes it when the finding goes, files a stall for a detector that
fails, and `todo check` reports one that has stopped running.

The fixture detectors are the plan's gates: a planted cause is a findings file a
`cat` command prints; removing it is writing []. TODO_DETECTORS points detect at
the fixture list (the override says so on every use). The S7 tests run the real
registered detector, through vocab.json, on a real jacob-step."""
import json
import os

from tests.helpers import WAITS, Case
from todolib import detect
from todolib.vocab import VOCAB, VOCAB_PATH, Vocab

STALL = VOCAB.role("stall_kind")
LAG = VOCAB.role("lag_kind")
NOTE = VOCAB.role("default_kind")
OPEN = VOCAB.role("default_status")
DETECTED = VOCAB.role("detector_resolution")
FAILED = VOCAB.detectors["failed_id"]


def finding(repo="a", subject="3 uncommitted files", count=3, evidence="x.py y.py z.py", clears="commit them"):
    return {"repo": repo, "subject": subject, "count": count, "evidence": evidence, "clears_with": clears}


def det(id_="D1", command=None, kind=None, waits_on=None, cadence=1):
    return {"id": id_, "doc": "a fixture", "command": command or ["cat", "{store}/cause.json"],
            "kind": kind or STALL, "waits_on": waits_on, "cadence_hours": cadence}


class Detect(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.use(det())
        self.cause([])

    def use(self, *dets):
        p = self.tmp / "detectors.json"
        p.write_text(json.dumps(list(dets)))
        self.env = {detect.LIST_ENV: str(p)}

    def cause(self, findings, d=None):
        (d or self.a / "cause.json").write_text(json.dumps(findings))

    def detect(self, *extra, ok=True, today="2026-10-04", now=None):
        env = dict(self.env, **({detect.NOW_ENV: now} if now else {}))
        return self.todo("-C", self.a, "--root", self.ws, "detect", *extra, ok=ok, env=env, today=today)

    def check(self, d, ok=True, today="2026-10-04"):
        return self.todo("-C", d, "check", ok=ok, today=today, env=self.env)

    def open_items(self, d=None):
        return [it for it in self.store(d or self.a)["items"] if it["kind"] in (STALL, LAG)]

    # a planted cause: one item, never two
    def test_a_finding_files_one_item_and_a_second_run_files_none(self):
        self.cause([finding()])
        r = self.detect()
        self.assertIn("NOTICE", r.stderr)  # the override is never silent
        [it] = self.open_items()
        self.assertEqual((it["kind"], it["status"], it["repo"]), (STALL, OPEN, "a"))
        self.assertEqual(it["title"], "D1: 3 uncommitted files (3)")
        self.assertEqual(it["evidence"], "x.py y.py z.py")
        self.assertEqual(it["detector"], {"id": "D1", "subject": "3 uncommitted files", "count": 3,
                                          "clears_with": "commit them", "seen": "2026-10-04"})
        self.assertEqual(detect.key_of(it), "detector:D1:a:3 uncommitted files")
        self.detect(today="2026-10-05")
        [again] = self.open_items()
        self.assertEqual(again["id"], it["id"])
        self.assertEqual(again["detector"]["seen"], "2026-10-05")
        self.check(self.a)

    def test_a_finding_seen_again_updates_its_count_and_evidence(self):
        self.cause([finding()])
        self.detect()
        self.cause([finding(count=5, evidence="five now")])
        r = self.detect()
        [it] = self.open_items()
        self.assertEqual((it["detector"]["count"], it["evidence"]), (5, "five now"))
        self.assertTrue(it["title"].endswith("(5)"))
        self.assertIn("seen", r.stdout)

    def test_the_cause_removed_closes_the_item_as_detected(self):
        self.cause([finding()])
        self.detect()
        self.cause([])
        self.detect()
        self.assertEqual(self.open_items(), [])
        [closed] = self.history(self.a)["items"]
        self.assertEqual((closed["resolution"], closed["detector"]["id"]), (DETECTED, "D1"))
        self.check(self.a)

    def test_two_causes_are_two_items_and_one_going_closes_only_it(self):
        self.cause([finding(), finding(subject="a render file stale", count=1)])
        self.detect()
        self.assertEqual(len(self.open_items()), 2)
        self.cause([finding(subject="a render file stale", count=1)])
        self.detect()
        self.assertEqual([it["detector"]["subject"] for it in self.open_items()], ["a render file stale"])

    def test_a_finding_for_another_scanned_repo_is_filed_in_its_store(self):
        b = self.repo("b", "bb")
        self.cause([finding(repo="b")])
        self.detect()
        self.assertEqual(self.open_items(), [])
        [it] = self.open_items(b)
        self.assertEqual(it["repo"], "b")
        self.cause([])
        self.detect()
        self.assertEqual(self.open_items(b), [])

    def test_a_finding_for_a_repo_with_no_store_is_filed_here_naming_it(self):
        self.cause([finding(repo="nostore")])
        self.detect()
        [it] = self.open_items()
        self.assertEqual(it["repo"], "nostore")

    def test_a_detector_that_needs_jacob_files_a_waiting_item(self):
        self.use(det(kind=LAG, waits_on=WAITS))
        self.cause([finding()])
        self.detect()
        [it] = self.open_items()
        self.assertEqual((it["kind"], it["status"], it["waits_on"]), (LAG, VOCAB.jacob_status, WAITS))
        self.check(self.a)

    def test_id_runs_one_detector_and_judges_its_items_alone(self):
        self.use(det(), det("D2", command=["cat", "{store}/cause2.json"]))
        self.cause([finding()])
        self.cause([finding(subject="two")], self.a / "cause2.json")
        self.detect()
        self.assertEqual(len(self.open_items()), 2)
        self.cause([])
        self.detect("--id", "D2")
        self.assertEqual(len(self.open_items()), 2, "D1 was not run, so its item is not judged")
        self.detect("--id", "nosuch", ok=False)

    # a failing detector
    def test_a_failing_command_files_a_failed_item_and_judges_nothing(self):
        self.cause([finding()])
        self.detect()
        self.use(det(command=["sh", "-c", "echo first >&2; echo the reason >&2; exit 2"]))
        r = self.detect(ok=False)
        self.assertIn("detector D1 failed", r.stderr)
        items = self.open_items()
        self.assertEqual(len(items), 2, "the finding's item stays open: a failed run judges nothing")
        [failed] = [it for it in items if it["detector"]["id"] == FAILED]
        self.assertEqual(failed["detector"]["subject"], "detector D1 failed")
        self.assertIn("exited 2: first | the reason", failed["evidence"])
        self.detect(ok=False)
        self.assertEqual(len(self.open_items()), 2, "a second failing run files no second item")
        self.use(det())
        self.detect()
        self.assertEqual([it["detector"]["id"] for it in self.open_items()], ["D1"])
        self.check(self.a)

    def test_output_that_is_not_findings_is_a_failure(self):
        # each case names its own reason: the failed item from an earlier case stays open,
        # so its presence alone would not show that this case was refused. The output is
        # a file the command prints: braces in the command itself would read as slots.
        bad = {"printed no JSON": "hello", "not a list of findings": "{}",
               "finding 1 is not exactly": json.dumps([{"repo": "a"}]),
               "count is not a whole number": json.dumps([finding(count=0)])}
        for n, (why, text) in enumerate(bad.items()):
            with self.subTest(why):
                out = self.tmp / f"bad{n}.txt"
                out.write_text(text)
                self.use(det(command=["cat", str(out)]))
                r = self.detect(ok=False)
                self.assertIn(why, r.stderr)
                [failed] = [it for it in self.open_items() if it["detector"]["id"] == FAILED]
                self.assertIn(why, failed["evidence"])

    def test_over_the_cap_is_a_failure_not_a_flood(self):
        cap = VOCAB.detectors["cap"]
        self.cause([finding(subject=f"cause {n}", count=1) for n in range(cap + 1)])
        r = self.detect(ok=False)
        self.assertIn("over the cap", r.stderr)
        self.assertEqual([it["detector"]["id"] for it in self.open_items()], [FAILED])

    def test_a_detector_that_cannot_start_is_a_failure(self):
        self.use(det(command=[str(self.tmp / "no-such-command")]))
        r = self.detect(ok=False)
        self.assertIn("could not start", r.stderr)

    # closing by hand
    def test_done_refuses_while_the_detector_reports_it_and_names_it(self):
        self.cause([finding()])
        self.detect()
        r = self.todo("-C", self.a, "--root", self.ws, "done", "aa-1", "--resolution", "fixed", ok=False, env=self.env)
        self.assertIn("detector D1 still reports it", r.stderr)
        self.assertIn("commit them", r.stderr)
        self.cause([])
        self.todo("-C", self.a, "--root", self.ws, "done", "aa-1", "--resolution", "fixed", env=self.env)
        self.assertEqual(self.open_items(), [])

    def test_done_refuses_when_the_detector_cannot_run(self):
        self.cause([finding()])
        self.detect()
        self.use(det(command=["false"]))
        r = self.todo("-C", self.a, "--root", self.ws, "done", "aa-1", "--resolution", "fixed", ok=False, env=self.env)
        self.assertIn("could not be run", r.stderr)

    def test_done_closes_one_whose_detector_is_no_longer_registered(self):
        self.cause([finding()])
        self.detect()
        self.use(det("OTHER"))
        self.todo("-C", self.a, "--root", self.ws, "done", "aa-1", "--resolution", "retired", env=self.env)

    def test_the_detected_resolution_is_set_by_detect_alone(self):
        self.todo("-C", self.a, "add", "x", "--kind", NOTE)
        r = self.todo("-C", self.a, "done", "aa-1", "--resolution", DETECTED, ok=False)
        self.assertIn("todo detect only", r.stderr)

    def test_no_detector_item_is_made_or_changed_by_hand(self):
        for kind in (STALL, LAG):
            r = self.todo("-C", self.a, "add", "x", "--kind", kind, ok=False)
            self.assertIn(VOCAB.made_by[kind], r.stderr)
        self.cause([finding()])
        self.detect()
        r = self.todo("-C", self.a, "edit", "aa-1", "--kind", NOTE, ok=False)
        self.assertIn("made and kept by todo detect", r.stderr)
        self.todo("-C", self.a, "add", "plain", "--kind", NOTE)
        self.todo("-C", self.a, "edit", "aa-2", "--kind", STALL, ok=False)
        r = self.todo("-C", self.a, "report", "aa-1", "--to", "elsewhere", ok=False)
        self.assertIn("todo detect keeps it", r.stderr)

    # check
    def test_check_fails_a_detector_field_on_another_kind_and_a_malformed_one(self):
        self.todo("-C", self.a, "add", "x", "--kind", NOTE)
        data = self.store(self.a)
        data["items"][0]["detector"] = {"id": "D1", "subject": "s", "count": 1, "clears_with": "c", "seen": "2026-10-04"}
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "schema", "detector is set on a")
        self.cause([finding()])
        self.detect()
        data = self.store(self.a)
        it = next(i for i in data["items"] if i["kind"] == STALL)
        it["detector"]["count"] = 0
        data["items"] = [it]
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "schema", "detector.count")

    def test_check_fails_the_detected_resolution_on_an_item_without_a_detector(self):
        self.todo("-C", self.a, "add", "x", "--kind", NOTE)
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "fixed")
        h = self.history(self.a)
        h["items"][0]["resolution"] = DETECTED
        self.write_json(self.a / "todo-history.json", h)
        self.assertFails(self.a, "vocab", "set by todo detect only")

    def test_check_fails_two_open_items_holding_one_key(self):
        self.cause([finding()])
        self.detect()
        data = self.store(self.a)
        twin = dict(data["items"][0], id="aa-2")
        data["items"].append(twin)
        data["next"] = 3
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "detectors", "one item per finding")

    def test_a_stale_run_is_reported_by_check(self):
        self.detect(now="2026-10-04T10:00:00Z")
        runs = json.loads((self.a / "todo-records.json").read_text())["runs"]
        self.assertEqual(runs["D1"]["at"], "2026-10-04T10:00:00Z")
        self.assertTrue(runs["D1"]["ok"])
        ok = self.todo("-C", self.a, "check", env=dict(self.env, **{detect.NOW_ENV: "2026-10-04T11:59:00Z"}))
        self.assertIn("ok    detectors", ok.stdout)
        r = self.todo("-C", self.a, "check", ok=False, env=dict(self.env, **{detect.NOW_ENV: "2026-10-04T12:01:00Z"}))
        self.assertIn("more than 2 x its cadence", r.stdout)

    def test_a_registered_detector_never_run_where_others_ran_is_reported(self):
        self.detect(now="2026-10-04T10:00:00Z")
        self.use(det(), det("D2"))
        r = self.todo("-C", self.a, "check", ok=False, env=dict(self.env, **{detect.NOW_ENV: "2026-10-04T10:01:00Z"}))
        self.assertIn("D2       has never run here", r.stdout)

    def test_a_store_where_no_detector_ran_is_not_reported(self):
        self.check(self.a)

    def test_check_fails_a_malformed_run_record(self):
        self.detect()
        recs = json.loads((self.a / "todo-records.json").read_text())
        recs["runs"]["D1"]["ok"] = False
        self.write_json(self.a / "todo-records.json", recs)
        self.assertFails(self.a, "detectors", "ok is true exactly when there is no why")

    # where the item shows
    def test_blockers_ranks_a_stall_with_its_dependents(self):
        self.cause([finding()])
        self.detect()
        for t in ("one", "two"):
            self.todo("-C", self.a, "add", t, "--kind", NOTE, "--blocked-by", "aa-1")
        v = json.loads(self.todo("-C", self.a, "blockers", "--json").stdout)
        [g] = [g for g in v["roots"] if "aa-2" in g["ids"]]
        self.assertEqual(g["what"], "open item aa-1")
        self.assertEqual(sorted(g["ids"]), ["aa-2", "aa-3"])

    def test_the_detector_field_renders(self):
        self.cause([finding()])
        self.detect()
        md = (self.a / "TODO.md").read_text()
        self.assertIn("## " + VOCAB.kinds[STALL]["heading"], md)
        self.assertIn("D1 on 3 uncommitted files, count 3, last seen 2026-10-04; clears with: commit them", md)


class S7(Case):
    """The registered S7 detector, run through vocab.json: a step taken is closed
    with no one asking, and only one that could not be closed is a stall."""

    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "do it", "--kind", VOCAB.role("step_kind"), "--done-check", "test -f done.flag")

    def findings(self, *extra):
        return json.loads(self.todo("-C", self.a, "--root", self.ws, "steps", "--findings", *extra).stdout)

    def test_findings_lists_a_step_whose_check_passes_and_only_it(self):
        self.assertEqual(self.findings(), [])
        (self.a / "done.flag").write_text("")
        [f] = self.findings()
        self.assertEqual((f["repo"], f["subject"], f["count"]), ("a", "aa-1 is taken: its done_check passes", 1))
        self.assertIsNone(detect.finding_problem(f), "steps --findings speaks the detector's form")
        self.assertEqual(len(self.store(self.a)["items"]), 1, "without --run nothing is closed")

    def test_detect_closes_a_taken_step_and_files_nothing(self):
        (self.a / "done.flag").write_text("")
        r = self.todo("-C", self.a, "--root", self.ws, "detect", "--id", "S7")
        self.assertNotIn("NOTICE", r.stderr)
        self.assertEqual(self.store(self.a)["items"], [])
        [closed] = self.history(self.a)["items"]
        self.assertEqual(closed["resolution"], VOCAB.role("step_resolution"))

    def test_a_taken_step_in_a_hand_edited_store_is_a_stall_until_it_closes(self):
        b = self.repo("b", "bb")
        self.todo("-C", b, "add", "bs", "--kind", VOCAB.role("step_kind"), "--done-check", "true")
        os.chmod(b / "TODO.md", 0o644)
        (b / "TODO.md").write_text((b / "TODO.md").read_text() + "\nhand edit\n")
        self.todo("-C", self.a, "--root", self.ws, "detect", "--id", "S7")
        [stall] = [it for it in self.store(self.a)["items"] if it["kind"] == STALL]
        self.assertEqual((stall["repo"], stall["detector"]["subject"]), ("b", "bb-1 is taken: its done_check passes"))
        self.assertIn("not closed", stall["evidence"])
        self.todo("-C", b, "render", "--force")
        self.todo("-C", self.a, "--root", self.ws, "detect", "--id", "S7")
        self.assertEqual([it for it in self.store(self.a)["items"] if it["kind"] == STALL], [])
        self.assertEqual(self.store(b)["items"], [])


class Vocabulary(Case):
    """vocab.json `detectors` both ways: every key consumed and checked, every
    consumed key present (todolib/vocab.py)."""

    def variant(self, change):
        data = json.loads(VOCAB_PATH.read_text())
        change(data)
        p = self.tmp / "vocab.json"
        p.write_text(json.dumps(data))
        return p

    def test_every_key_is_required_and_no_other_is_read(self):
        def drop(k):
            return lambda d: d["detectors"].pop(k)
        def add(d):
            d["detectors"]["extra"] = 1
        for k in ("cap", "timeout_s", "digest_lines", "evidence_max", "stale_factor", "failed_id", "list"):
            with self.subTest(drop=k), self.assertRaises((ValueError, KeyError)):
                Vocab(self.variant(drop(k)))
        with self.assertRaises(ValueError):
            Vocab(self.variant(add))
        Vocab(self.variant(lambda d: None))

    def test_a_bad_detector_refuses_to_load(self):
        good = det()
        bad = {"an extra key": dict(good, extra=1), "a missing key": {k: v for k, v in good.items() if k != "doc"},
               "an unknown slot": dict(good, command=["cat", "{home}/x"]), "an empty command": dict(good, command=[]),
               "a kind that holds no detector": dict(good, kind=NOTE), "the reserved id": dict(good, id=FAILED),
               "a bad waits_on": dict(good, waits_on="nosuch:thing"), "a zero cadence": dict(good, cadence_hours=0),
               "an id with a colon": dict(good, id="a:b")}
        for why, d in bad.items():
            with self.subTest(why):
                with self.assertRaises(ValueError):
                    Vocab(self.variant(lambda data: data["detectors"].update(list=[d])))
                self.assertIsNotNone(VOCAB.detector_list_problem([d], FAILED))
        self.assertIsNotNone(VOCAB.detector_list_problem([good, good], FAILED), "an id used twice")
        self.assertIsNone(VOCAB.detector_list_problem([good], FAILED))

    def test_the_override_is_checked_as_vocab_json_is(self):
        a = self.repo("a", "aa")
        p = self.tmp / "detectors.json"
        p.write_text(json.dumps([dict(det(), kind=NOTE)]))
        r = self.todo("-C", a, "detect", ok=False, env={detect.LIST_ENV: str(p)})
        self.assertIn("is not one of", r.stderr)

    def test_made_by_names_a_command_and_the_detector_kinds_require_the_field(self):
        with self.assertRaises(ValueError):
            Vocab(self.variant(lambda d: d["kinds"][STALL].update(made_by=" ")))
        with self.assertRaises(ValueError):
            Vocab(self.variant(lambda d: d["kinds"][LAG].update(requires=[])))
        self.assertEqual(set(VOCAB.detector_kinds), {STALL, LAG})
        for k in VOCAB.detector_kinds:
            self.assertEqual(VOCAB.made_by[k], "todo detect")
