"""`todo import` reads what a hand TODO.md already says (PLAN-todo-tool.md §10.2 step 6,
§10.4): an approval in an item's lead, what a waiting item waits on, a suspicion's
probe, a report's owner, and which blocks are not items. Each rule has a passing and
a failing fixture, each knob in vocab.json `import` a test that changing it changes
the output, and every key there is one code reads."""
import json
import tempfile
from pathlib import Path

from tests.helpers import ROOT, TODAY, Case, git_repo
from todolib import importer
from todolib.importer import md_blocks, plan_import, read_approval, read_owner, read_probe, read_waits_on, skip_reasons
from todolib.vocab import VOCAB, Vocab

RAW = json.loads((ROOT / "vocab.json").read_text())
JACOB = VOCAB.jacob_status
OPEN = VOCAB.role("default_status")
NOTE = VOCAB.role("default_kind")
NEEDS = next(r["match"] for r in VOCAB.import_rules if r.get("status") == JACOB)
SUSPECT = next(k for k, v in VOCAB.kinds.items() if "probe" in v["requires"])
REPORT = VOCAB.role("report_kind")
SUSPECT_HEADING, REPORT_HEADING = VOCAB.kinds[SUSPECT]["heading"], VOCAB.kinds[REPORT]["heading"]
PLAIN = [n for n, rx in VOCAB.waits_on_arg.items() if rx is None]  # settings, approval: no argument


def vocab_with(**imp):
    raw = json.loads(json.dumps(RAW))
    raw["import"].update(imp)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(raw, fh)
    try:
        return Vocab(Path(fh.name))
    finally:
        Path(fh.name).unlink()


class FakeStore:
    repo = "me"
    items, closed = [], []

    def owns(self, item_id):
        return False


def imported(text, vocab=VOCAB, **kw):
    plan = plan_import(text, FakeStore(), TODAY, vocab=vocab, **kw)
    return [it for it, _ in plan.new], plan


def under(heading, *bullets):
    return f"# t\n\n## {heading}\n\n" + "\n\n".join(f"- {b}" for b in bullets) + "\n"


class Approval(Case):
    def test_an_approval_in_the_lead_sets_it_and_opens_the_item(self):
        items, plan = imported(under(NEEDS, '**Go ahead** approved: Jacob 2026-10-03 "yes, do it". More.'))
        it = items[0]
        self.assertEqual(it["approved"], {"by": VOCAB.approval_by, "date": "2026-10-03", "source": "yes, do it"})
        self.assertEqual((it["status"], it["waits_on"]), (OPEN, None))
        items, _ = imported(under(NEEDS, "**Go** (Approved: Jacob 2026-10-03.)"))
        self.assertEqual(items[0]["approved"]["source"], "Approved: Jacob 2026-10-03")

    def test_an_approval_outside_the_lead_or_dated_later_is_not_applied(self):
        items, _ = imported(under(NEEDS, "**Ask** first line\n\n  approved: Jacob 2026-10-03, later paragraph"),
                            waits_on=PLAIN[0])
        self.assertEqual((items[0]["approved"], items[0]["status"]), (None, JACOB))
        items, plan = imported(under(NEEDS, "**Ask** approved: Jacob 2099-01-01"), waits_on=PLAIN[0])
        self.assertIsNone(items[0]["approved"])
        self.assertIn("after today: not applied", plan.listed[0][1])
        self.assertIsNone(read_approval("approved: Jacob, no date", TODAY)[0])

    def test_the_pattern_is_read_from_vocab(self):
        text = under(NEEDS, "**Go** approved: Jacob 2026-10-03")
        never = vocab_with(approval="(?P<date>x)^(?P<quote>y)")
        self.assertIsNotNone(imported(text)[0][0]["approved"])
        self.assertIsNone(imported(text, vocab=never, waits_on=PLAIN[0])[0][0]["approved"])


class WaitsOn(Case):
    def test_each_rule_sets_its_value(self):
        cases = {"waits on PLAN-x.md §2.1 being read.": "decision:PLAN-x.md §2.1",
                 "run `wizard run intake` first": "wizard:intake",
                 "it waits on settings, then": "settings",
                 "this waits on his approval.": "approval"}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(read_waits_on(text, lambda ref: None), (want, None))
        self.assertEqual({v.partition(":")[0] for v in cases.values()},
                         {r["value"].partition(":")[0] for r in VOCAB.import_waits_on})

    def test_the_earliest_resolving_pointer_wins_and_an_unresolved_one_is_listed(self):
        text = "waits on PLAN-x.md §9, then waits on settings"
        self.assertEqual(read_waits_on(text, lambda ref: None)[0], "decision:PLAN-x.md §9")
        value, why = read_waits_on(text, lambda ref: f"{ref} is gone")
        self.assertEqual(value, "settings")
        value, why = read_waits_on("waits on PLAN-x.md §9 only", lambda ref: f"{ref} is gone")
        self.assertIsNone(value)
        self.assertIn("PLAN-x.md§9 is gone", why)
        self.assertEqual(read_waits_on("waits on W-1 and JS-5")[1], "'waits on W-1 and JS-5' resolves to no waits_on")
        self.assertEqual(read_waits_on("nothing here")[1], "names nothing it waits on")

    def test_a_waiting_item_naming_none_takes_the_given_value_or_is_counted(self):
        text = under(NEEDS, "**Ask** something")
        items, plan = imported(text)
        self.assertEqual((items[0]["waits_on"], plan.unnamed_waits), (None, ["Ask"]))
        items, plan = imported(text, waits_on=PLAIN[0])
        self.assertEqual((items[0]["waits_on"], plan.unnamed_waits), (PLAIN[0], []))
        items, _ = imported(under(NEEDS, "**Ask** waits on settings"), waits_on=PLAIN[1])
        self.assertEqual(items[0]["waits_on"], "settings")  # the text wins over the default

    def test_the_rules_and_the_mention_are_read_from_vocab(self):
        self.assertEqual(read_waits_on("waits on settings", vocab=vocab_with(waits_on=[]))[0], None)
        mention = vocab_with(waits_on_mention="(?i)hinges on \\S+")
        self.assertEqual(read_waits_on("hinges on X-1", vocab=mention)[1], "'hinges on X-1' resolves to no waits_on")


class Probe(Case):
    def test_the_text_after_a_marker_up_to_a_sentence_end_outside_backticks(self):
        self.assertEqual(read_probe("Seen once. Probe: run `cd a. && b`, then\n  `ps`. Then more."), "run `cd a. && b`, then `ps`.")
        self.assertEqual(read_probe("x -- settle: `cd y && ./dev.sh check` (run alone)"), "`cd y && ./dev.sh check` (run alone)")
        items, _ = imported(under(SUSPECT_HEADING, "**Maybe** Probe: grep it."))
        self.assertEqual((items[0]["kind"], items[0]["probe"]), (SUSPECT, "grep it."))

    def test_no_marker_imports_as_a_note_recording_the_kind_it_wanted(self):
        items, plan = imported(under(SUSPECT_HEADING, "**Maybe** nothing to run"))
        self.assertEqual((items[0]["kind"], items[0]["probe"], items[0]["imported"]["wanted"]), (NOTE, None, SUSPECT))
        self.assertIn(f"--kind {SUSPECT} --probe", plan.listed[0][1])

    def test_the_markers_are_read_from_vocab(self):
        self.assertIsNone(read_probe("Probe: x.", vocab=vocab_with(probe="(?i)check:\\s*")))
        self.assertEqual(read_probe("Check: x.", vocab=vocab_with(probe="(?i)check:\\s*")), "x.")


class Owner(Case):
    REPOS = {"hooks", "setup", "me"}

    def test_the_leads_first_word_when_it_is_a_scanned_repo(self):
        self.assertEqual(read_owner("hooks (2026-10-09, via x): it fails", self.REPOS, "me", TODAY),
                         {"repo": "hooks", "date": "2026-10-09", "their_id": None})
        self.assertEqual(read_owner("**setup**: no date here (2026-10-01 later)\nnext (2026-10-02", self.REPOS, "me", TODAY),
                         {"repo": "setup", "date": "2026-10-01", "their_id": None})
        self.assertEqual(read_owner("setup: plain", self.REPOS, "me", TODAY)["date"], TODAY)

    def test_more_than_one_owner_an_unknown_one_or_this_store_is_none(self):
        for lead in ("hooks + setup (2026-10-09): x", "hooks, setup (2026-10-09): x", "every repo owner (x): y",
                     "nobody (2026-10-09): x", "me (2026-10-09): x", "2026-10-05, via someone (setup): x"):
            with self.subTest(lead=lead):
                self.assertIsNone(read_owner(lead, self.REPOS, "me", TODAY))
        items, plan = imported(under(REPORT_HEADING, "nobody (2026-10-09): x"), repos=self.REPOS)
        self.assertEqual((items[0]["kind"], items[0]["imported"]["wanted"]), (NOTE, REPORT))
        items, _ = imported(under(REPORT_HEADING, "hooks (2026-10-09): x"), repos=self.REPOS)
        self.assertEqual((items[0]["kind"], items[0]["reported_to"]["repo"]), (REPORT, "hooks"))

    def test_a_closed_report_naming_no_owner_is_a_closed_note(self):
        # td-47: a DONE bullet under the reports heading (tools/setup su-72)
        items, plan = imported(under(REPORT_HEADING, "DONE 2026-10-04: hooks fixed it"), repos=self.REPOS)
        it = items[0]
        self.assertEqual((it["kind"], it["status"], it["imported"]["wanted"]), (NOTE, VOCAB.closed, REPORT))
        self.assertIsNone(it.get("reported_to"))
        self.assertIn("history keeps it", plan.listed[0][1])

    def test_the_patterns_are_read_from_vocab(self):
        lead = "hooks (2026-10-09): x"
        self.assertIsNone(read_owner(lead, self.REPOS, "me", TODAY, vocab=vocab_with(report_owner="^(?P<repo>x)y")))
        late = vocab_with(report_date="^(?P<date>\\d{4}-\\d{2}-\\d{2})")
        self.assertEqual(read_owner(lead, self.REPOS, "me", TODAY, vocab=late)["date"], TODAY)


class Skip(Case):
    FILE = ("# t\n\nPreamble under the top heading.\n\n## A\n\nIntro to A.\n\n- **Group:**\n\n- an item\n\n"
            "A paragraph after a bullet.\n\n## B\n\nOnly paragraphs here.\n")

    def reasons(self, text, vocab=VOCAB):
        blocks, _ = md_blocks(text)
        return {blocks[i].text(): why for i, why in skip_reasons(blocks, vocab).items()}

    def test_preamble_intro_and_heading_only_blocks_are_not_items_and_the_rest_are(self):
        self.assertEqual(self.reasons(self.FILE), {
            "Preamble under the top heading.": "text under the top heading alone",
            "Intro to A.": "text above the section's first bullet",
            "**Group:**": "only a heading"})
        items, plan = imported(self.FILE)
        self.assertEqual([it["title"] for it in items], ["an item", "A paragraph after a bullet.", "Only paragraphs here."])
        self.assertEqual(len(plan.not_items), 3)

    def test_a_file_with_no_deeper_heading_keeps_its_paragraphs(self):
        self.assertEqual(self.reasons("# t\n\nOne paragraph.\n\nAnother.\n"), {})

    def test_the_knobs_are_read_from_vocab(self):
        off = vocab_with(skip={"intro": False, "heading_only": RAW["import"]["skip"]["heading_only"]})
        self.assertEqual(set(self.reasons(self.FILE, off)), {"**Group:**"})
        none = vocab_with(skip={"intro": True, "heading_only": "^$"})
        self.assertNotIn("**Group:**", self.reasons(self.FILE, none))


class Declared(Case):
    def test_every_import_key_is_read(self):
        read = {"headings", "done_marker", "approval", "waits_on", "waits_on_mention", "probe", "report_owner",
                "report_date", "skip"}
        self.assertEqual({k for k in RAW["import"] if not k.startswith("_")}, read)
        self.assertEqual({k for k in RAW["import"]["skip"] if not k.startswith("_")}, {"intro", "heading_only"})
        self.assertEqual({k for r in RAW["import"]["waits_on"] for k in r} - {"match", "value", "plan"}, set())
        required = {f for k in VOCAB.kinds.values() for f in k["requires"]}
        self.assertLessEqual(set(importer.FIELD_READERS), required, "a reader for a field no kind requires")

    def test_a_required_field_no_reader_fills_falls_back_and_is_listed(self):
        temp = next(k for k, v in VOCAB.kinds.items() if v["requires"] and not set(v["requires"]) & set(importer.FIELD_READERS))
        rules = RAW["import"]["headings"] + [{"match": "interim", "kind": temp}]
        items, plan = imported(under("Interim rules", "**A rule** for now"), vocab=vocab_with(headings=rules))
        self.assertEqual((items[0]["kind"], items[0]["imported"]["wanted"]), (NOTE, temp))
        self.assertIn(f"--kind {temp}", plan.listed[0][1])

    def test_a_malformed_knob_is_refused_at_load(self):
        for bad in ({"waits_on": [{"match": "x", "value": "undeclared:x"}]},
                    {"approval": "approved (?P<date>x)"},
                    {"report_owner": "^(\\w+)"},
                    {"skip": {"intro": "yes", "heading_only": "^$"}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                vocab_with(**bad)


class Cli(Case):
    def test_a_real_import_refuses_a_waiting_item_naming_nothing_and_a_dry_run_lists_it(self):
        d = self.repo("a", "aa")
        (d / "TODO.md").chmod(0o644)
        (d / "TODO.md").write_text(under(NEEDS, "**Ask** something"))
        out = self.todo("-C", d, "import", "--dry-run", "TODO.md").stdout
        self.assertIn("listed   Ask: names nothing it waits on", out)
        r = self.todo("-C", d, "import", "TODO.md", ok=False)
        self.assertIn("name no waits_on", r.stderr)
        self.assertEqual(self.store(d)["items"], [])
        self.todo("-C", d, "import", "TODO.md", "--waits-on", "nonsense", ok=False)
        self.todo("-C", d, "import", "TODO.md", "--waits-on", PLAIN[0])
        self.assertEqual(self.store(d)["items"][0]["waits_on"], PLAIN[0])
        self.check(d)

    def test_an_owner_resolves_to_a_git_repo_the_scan_finds_store_or_none(self):
        d = self.repo("a", "aa")
        git_repo(self.ws / "hooks")  # a repo with no store yet
        (self.ws / "plain").mkdir()  # a folder, not a repo
        (d / "TODO.md").chmod(0o644)
        (d / "TODO.md").write_text(under(REPORT_HEADING, "hooks (2026-10-09): x", "plain (2026-10-09): y"))
        self.todo("-C", d, "--root", self.ws, "import", "TODO.md")
        got = {it["title"]: (it["kind"], (it["reported_to"] or {}).get("repo")) for it in self.store(d)["items"]}
        self.assertEqual(got, {"hooks (2026-10-09): x": (REPORT, "hooks"), "plain (2026-10-09): y": (NOTE, None)})
        out = self.check(d).stdout
        self.assertIn("0 failed", out)

    def test_a_decision_pointer_resolves_through_the_plans_cli(self):
        from todolib import plans
        if plans.resolve_cli(None)[1]:
            self.fail("this test reads plans through the setup tool")
        (self.ws / "PLAN-x.md").write_text("# X\n\n## 1. First\n\none\n")
        d = self.repo("a", "aa")
        (d / "TODO.md").chmod(0o644)
        (d / "TODO.md").write_text(under(NEEDS, "**Read** waits on PLAN-x.md §1.", "**Gone** waits on PLAN-x.md §7."))
        out = self.todo("-C", d, "--root", self.ws, "import", "TODO.md", "--waits-on", PLAIN[0]).stdout
        got = {it["title"]: it["waits_on"] for it in self.store(d)["items"]}
        self.assertEqual(got, {"Read": "decision:PLAN-x.md §1", "Gone": PLAIN[0]})
        self.assertIn("listed   Gone: no pointer resolves", out)
