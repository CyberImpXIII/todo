"""Audits (PLAN-hard-gates.md §9; PLAN-todo-tool.md §10.3c): a refusal at write time
ships with an audit of the same predicate over what is already there.

- rule 1, one predicate, two callers: what `add` and `edit` refuse, `todo audit
  decisions` finds, `todo decisions` never tables and `todo check` fails, each
  decision field in turn (§10.3c step 4);
- rule 2, the audit is a detector: D1 and D2 file one item per store with its
  count, and close it at zero;
- rule 3, an exemption has an end date: a `*_since` key without its `*_until` is
  refused on load, and past `decisions.row_fields_until` an open D1 item fails check;
- rule 4, INFO is not a resting place: the decision and size INFO lines are gone,
  and every gate still printing INFO is listed in checks.INFO_PENDING;
- AUDITS.md is rendered after every run, one row per detector and repo, a failed
  run a row.

Incomplete decisions are planted with write_json (sealed, as the CLI writes): add
refuses them now, which is the point."""
import json
import os
import re
from pathlib import Path

from tests.helpers import Case
from todolib import audits, checks, detect, plans
from todolib.store import AUDITS_FILE
from todolib.vocab import VOCAB, VOCAB_PATH, Vocab

D = VOCAB.decisions
DECISION = VOCAB.role("decision_kind")
NOTE = VOCAB.role("default_kind")
D1 = next(d["id"] for d in VOCAB.detectors["list"] if d["audits"] == "decisions")
D2 = next(d["id"] for d in VOCAB.detectors["list"] if d["audits"] == "sizes")
FIELDS = D["requires"] + D["row_fields"]
FULL = {"pointer": "PLAN-x.md §1", "hinges_on": "h", "recommend": "yes", "today": "t", "problem": "p"}
BEFORE = "2026-10-04"          # tests.helpers.TODAY, before the end date
PAST = "2026-11-04"            # the day after decisions.row_fields_until
PLAN = "# X\n\n## 1. First\n\none\n"


def flag(f):
    return "--" + f.replace("_", "-")


class Base(Case):
    def setUp(self):
        super().setUp()
        _, why = plans.resolve_cli(None)
        if why:
            self.fail(f"these tests read plans through the setup tool: {why}")
        (self.ws / "PLAN-x.md").write_text(PLAN)
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")

    def run_in(self, repo, *args, ok=True, today=BEFORE, env=None):
        return self.todo("-C", repo, "--root", self.ws, *args, ok=ok, today=today, env=env)

    def add_decision(self, repo, title="d", **fields):
        args = ["add", title, "--kind", DECISION]
        for f, v in dict(FULL, **fields).items():
            if v is not None:
                args += [flag(f), v]
        return self.run_in(repo, *args)

    def plant(self, repo, drop, title="old"):
        """An open decision lacking `drop`, written around add (which refuses it)."""
        self.add_decision(repo, title)
        data = self.store(repo)
        it = data["items"][-1]
        it.pop(drop, None)
        self.write_json(repo / "todo.json", data)
        self.run_in(repo, "render")
        return it["id"]

    def check_lines(self, repo, gate, ok=True, today=BEFORE):
        out = self.todo("-C", repo, "--root", self.ws, "check", ok=ok, today=today).stdout
        return [ln for ln in out.splitlines() if ln.split()[1:2] == [gate]]

    def audit(self, rule, repo=None):
        return json.loads(self.run_in(repo or self.a, "audit", rule).stdout)

    def detect(self, today=BEFORE, ok=True, env=None):
        return self.run_in(self.a, "detect", ok=ok, today=today, env=env)

    def held(self, repo, det_id):
        return [it for it in self.store(repo)["items"] if (it.get("detector") or {}).get("id") == det_id]


class OnePredicate(Base):
    """Rule 1 and §10.3c step 4: each refusal fires, each field in turn."""

    def test_add_refuses_each_missing_field_and_the_audit_finds_it(self):
        for f in FIELDS:
            with self.subTest(field=f):
                err = self.run_in(self.a, "add", "t", "--kind", DECISION,
                                  *[x for k, v in FULL.items() if k != f for x in (flag(k), v)], ok=False).stderr
                self.assertIn(flag(f), err)
        self.assertEqual(self.store(self.a)["items"], [])
        planted = {f: self.plant(self.b, f, title=f"lacks {f}") for f in FIELDS}
        found = self.audit("decisions")
        self.assertEqual([(x["repo"], x["count"]) for x in found], [("b", len(FIELDS))])
        for f, iid in planted.items():
            self.assertIn(f"{iid} ({f})", found[0]["evidence"])
        self.assertTrue(found[0]["evidence"].startswith(f"oldest {BEFORE}: "))

    def test_edit_refuses_clearing_each_field(self):
        self.add_decision(self.a)
        for f in FIELDS:
            with self.subTest(field=f):
                err = self.run_in(self.a, "edit", "aa-1", flag(f), "", ok=False).stderr
                self.assertIn(flag(f), err)
        self.assertEqual({f: self.store(self.a)["items"][0][f] for f in FIELDS}, FULL)

    def test_an_old_decision_is_refused_on_edit_whatever_its_date(self):
        """The exemption is gone (PLAN-todo-tool.md §10.3c): a decision added before
        row_fields_since, edited, needs today and problem too."""
        iid = self.plant(self.a, "today")
        data = self.store(self.a)
        data["items"][0]["added"] = "2026-10-01"
        self.write_json(self.a / "todo.json", data)
        self.run_in(self.a, "render")
        err = self.run_in(self.a, "edit", iid, "--hinges-on", "h2", ok=False).stderr
        self.assertIn("--today", err)

    def test_decisions_never_tables_one_lacking_a_field_and_names_its_owner(self):
        for f in FIELDS:
            with self.subTest(field=f):
                iid = self.plant(self.b, f, title=f"lacks {f}")
                out = json.loads(self.run_in(self.a, "decisions", "--json").stdout)
                self.assertNotIn(iid, [r["item"] for r in out["rows"]])
                self.assertIn(f, next(x["missing"] for x in out["incomplete"] if x["id"].endswith(iid)))
        self.add_decision(self.b, "complete")
        out = json.loads(self.run_in(self.a, "decisions", "--json").stdout)
        self.assertEqual(len(out["rows"]), 1)  # the counterfactual: a complete one is tabled

    def test_check_fails_each_field_past_the_end_date(self):
        for n, f in enumerate(FIELDS):
            with self.subTest(field=f):
                d = self.repo(f"c{n}", f"c{'abcdefgh'[n]}")
                iid = self.plant(d, f)
                hits = [ln for ln in self.check_lines(d, "required", ok=False, today=PAST) if ln.startswith("  FAIL")]
                self.assertTrue(any(iid in ln and f in ln for ln in hits), hits)


class Detectors(Base):
    """Rule 2: D1 and D2 are detectors, one item per store with its count, closed at zero;
    and §10.3c step 3: a store at zero fails on any incomplete decision."""

    def test_before_d1_runs_an_incomplete_decision_is_one_info_line_naming_d1(self):
        self.plant(self.b, "problem")
        lines = self.check_lines(self.b, "required")
        self.assertTrue(any(ln.startswith("  INFO") and D1 in ln for ln in lines), lines)

    def test_d1_files_one_item_per_store_holds_it_until_the_end_date_and_closes_it_at_zero(self):
        iid = self.plant(self.b, "problem")
        self.plant(self.b, "today", title="second")
        self.detect()
        held = self.held(self.b, D1)
        self.assertEqual([(it["repo"], it["detector"]["count"]) for it in held], [("b", 2)])
        self.assertEqual(self.held(self.a, D1), [])
        # held by its item: check passes before the end date, fails past it
        self.assertFalse([ln for ln in self.check_lines(self.b, "required") if ln.startswith("  FAIL")])
        past = [ln for ln in self.check_lines(self.b, "required", ok=False, today=PAST) if ln.startswith("  FAIL")]
        self.assertTrue(any(held[0]["id"] in ln and D["row_fields_until"] in ln for ln in past), past)
        # completing them closes the item on the next run
        for it in self.store(self.b)["items"]:
            if it["kind"] == DECISION:
                self.run_in(self.b, "edit", it["id"], "--today", "t", "--problem", "p")
        self.detect()
        self.assertEqual(self.held(self.b, D1), [])
        self.assertIn(iid, [it["id"] for it in self.store(self.b)["items"]])

    def test_a_store_at_zero_fails_on_any_incomplete_decision(self):
        self.add_decision(self.b, "complete")
        self.detect()                       # D1 ran: b is at zero
        self.assertEqual(self.held(self.b, D1), [])
        iid = self.plant(self.b, "pointer", title="slipped in")
        fails = [ln for ln in self.check_lines(self.b, "required", ok=False) if ln.startswith("  FAIL")]
        self.assertTrue(any(iid in ln and "at zero" in ln for ln in fails), fails)

    def test_an_unreadable_store_is_exit_3_never_a_clean_zero(self):
        self.plant(self.a, "problem")
        os.chmod(self.b / "todo.json", 0o644)
        (self.b / "todo.json").write_text("{not json")
        r = self.run_in(self.a, "audit", "decisions", ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertEqual([x["repo"] for x in json.loads(r.stdout)], ["a"])  # what could be read is still reported
        self.assertIn("UNCHECKED", r.stderr)

    def test_d2_counts_unsized_items_per_store_and_not_its_own(self):
        self.run_in(self.b, "add", "unsized one", "--kind", NOTE)
        self.run_in(self.b, "add", "sized", "--kind", NOTE, "--size", VOCAB.ready_sizes[0])
        found = self.audit("sizes")
        self.assertEqual([(x["repo"], x["count"]) for x in found], [("b", 1)])
        self.detect()
        self.assertEqual([it["detector"]["count"] for it in self.held(self.b, D2)], [1])
        self.assertEqual(self.audit("sizes"), found)  # the D2 item itself is unsized, and not counted
        self.assertNotIn("unsized", "\n".join(self.check_lines(self.b, "sizes")))  # rule 4: no INFO line


class EndDates(Case):
    """Rule 3, and the pairing a block and its detector name (checked on load)."""

    def vocab_with(self, change):
        data = json.loads(Path(VOCAB_PATH).read_text())
        change(data)
        p = self.tmp / "vocab.json"
        p.write_text(json.dumps(data))
        return p

    def test_a_since_without_its_until_is_refused(self):
        p = self.vocab_with(lambda d: d["decisions"].pop("row_fields_until"))
        with self.assertRaisesRegex(ValueError, "row_fields_until"):
            Vocab(p)

    def test_an_until_before_its_since_is_refused(self):
        p = self.vocab_with(lambda d: d["decisions"].update(row_fields_until="2026-10-01"))
        with self.assertRaisesRegex(ValueError, "row_fields_until"):
            Vocab(p)

    def test_a_block_naming_an_audit_no_detector_runs_is_refused(self):
        p = self.vocab_with(lambda d: d["decisions"].update(audited_by="D9"))
        with self.assertRaisesRegex(ValueError, "decisions.audited_by"):
            Vocab(p)

    def test_a_detector_naming_no_block_is_refused(self):
        def change(d):
            d["detectors"]["list"][0]["audits"] = "nowhere"
        with self.assertRaisesRegex(ValueError, "nowhere"):
            Vocab(self.vocab_with(change))

    def test_each_rule_the_audit_verb_runs_is_a_registered_detector_and_back(self):
        by_rule = {d["audits"]: d for d in VOCAB.detectors["list"] if d["command"][-2:-1] == ["audit"]}
        self.assertEqual(sorted(by_rule), sorted(audits.RULES))
        for rule, det in by_rule.items():
            self.assertEqual(det["command"][-1], rule)
        self.assertEqual(VOCAB.end_date("decisions"), D["row_fields_until"])


class InfoLines(Case):
    """Rule 4: the gates that still print INFO are listed, both ways, each with why."""

    def test_every_info_gate_is_listed_and_every_listed_gate_prints_info(self):
        src = Path(checks.__file__).read_text()
        printed = set(re.findall(r'\("INFO", "([a-z]+)"', src))
        self.assertEqual(printed, set(checks.INFO_PENDING))
        self.assertNotIn("sizes", printed)
        for gate, why in checks.INFO_PENDING.items():
            self.assertTrue(why.strip(), gate)


class Report(Base):
    """AUDITS.md: rendered after every run, one row per detector and repo; a failed run a row."""

    def rows(self):
        p = self.a / AUDITS_FILE
        self.assertFalse(os.access(p, os.W_OK), "AUDITS.md is written read-only")
        return [ln.strip("|").split("|") for ln in p.read_text().splitlines() if ln.startswith("| ") and "---" not in ln][1:]

    def test_each_detector_and_repo_is_a_row_with_count_oldest_end_and_last_run(self):
        self.plant(self.b, "problem")
        self.detect()
        rows = {(r[1].strip(), r[2].strip()): [c.strip() for c in r] for r in self.rows()}
        ids = [d["id"] for d in VOCAB.detectors["list"]]
        self.assertEqual(sorted(rows), sorted((i, repo) for i in ids for repo in ("a", "b")))
        b = rows[(D1, "b")]
        self.assertEqual(b[3:6], ["1", BEFORE, D["row_fields_until"]])
        self.assertEqual(b[7], "ok")
        self.assertEqual(rows[(D1, "a")][3:5], ["0", "-"])
        # the input changes the output: a second offender changes the count
        self.plant(self.b, "today", title="second")
        self.detect()
        rows = {(r[1].strip(), r[2].strip()): [c.strip() for c in r] for r in self.rows()}
        self.assertEqual(rows[(D1, "b")][3], "2")

    def test_a_failed_run_is_a_row(self):
        lst = [{"id": "F1", "doc": "fails", "command": ["false"], "kind": VOCAB.role("stall_kind"),
                "waits_on": None, "cadence_hours": 1, "audits": "steps"}]
        p = self.tmp / "dets.json"
        p.write_text(json.dumps(lst))
        self.detect(ok=False, env={detect.LIST_ENV: str(p)})
        rows = [[c.strip() for c in r] for r in self.rows()]
        self.assertTrue(rows and all(r[1] == "F1" and r[7].startswith("failed: exited 1") for r in rows), rows)
