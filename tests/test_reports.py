"""Reports in pairs: a reported_to has its counterpart in the owner's store or
history, the counterpart's parent points back, and check names every gap."""
from tests.helpers import Case
from todolib.vocab import VOCAB


class Reports(Case):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", self.a, "add", "their bug", "--kind", "bug", "--evidence", "ran x, saw y")

    def test_report_creates_the_counterpart_with_parent_pointing_back(self):
        out = self.todo("-C", self.a, "report", "aa-1", "--to", "b").stdout
        self.assertIn("as bb-1", out)
        mine = self.store(self.a)["items"][0]
        self.assertEqual(mine["kind"], VOCAB.role("report_kind"))
        self.assertEqual(mine["reported_to"], {"repo": "b", "date": "2026-10-04", "their_id": "bb-1"})
        theirs = self.store(self.b)["items"][0]
        self.assertEqual((theirs["parent"], theirs["kind"], theirs["evidence"]), ("aa-1", "bug", "ran x, saw y"))
        self.check(self.a)
        out = self.check(self.b).stdout
        self.assertIn("still open here: bb-1", out)

    def test_pairing_finds_a_counterpart_the_owner_already_closed(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "b")
        self.todo("-C", self.b, "done", "bb-1", "--resolution", "fixed in b")
        out = self.check(self.a).stdout
        self.assertIn("counterpart bb-1 closed 2026-10-04: fixed in b", out)
        self.assertNotIn("FAIL", out)

    def test_reporting_again_pairs_with_the_existing_counterpart_even_closed(self):
        self.todo("-C", self.b, "add", "already filed", "--kind", "bug", "--parent", "aa-1")
        self.todo("-C", self.b, "done", "bb-1", "--resolution", "fixed before we asked")
        out = self.todo("-C", self.a, "report", "aa-1", "--to", "b").stdout
        self.assertIn("already holds bb-1", out)
        self.assertEqual(self.store(self.b)["items"], [])
        self.assertEqual(self.store(self.a)["items"][0]["reported_to"]["their_id"], "bb-1")

    def test_report_to_a_repo_without_a_store_is_a_warning_until_it_has_one(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "c")
        out = self.check(self.a).stdout
        self.assertIn("WARN  reports", out)
        self.assertIn("unpaired", out)
        self.repo("c", "cc")
        self.assertFails(self.a, "reports", "has a store now")
        self.assertIn("as cc-1", self.todo("-C", self.a, "report", "aa-1", "--to", "c").stdout)
        self.check(self.a)

    def test_a_report_to_a_hidden_folder_never_pairs_and_says_so(self):
        """The scan never enters a hidden folder (and todo never reads the delegation
        layer), so a report there can never pair: say so, not "not migrated yet"."""
        out = self.todo("-C", self.a, "report", "aa-1", "--to", ".layer").stdout
        self.assertIn("never pairs", out)
        self.assertNotIn("re-run this once", out)
        self.assertEqual(self.store(self.a)["items"][0]["reported_to"],
                         {"repo": ".layer", "date": "2026-10-04", "their_id": None})
        out = self.check(self.a).stdout
        lines = [ln for ln in out.splitlines() if ln.split()[:3] == ["INFO", "reports", "aa-1"]]
        self.assertTrue(lines and "never pairs" in lines[0], out)
        self.assertNotIn("WARN", out)
        self.assertNotIn("unpaired", out)
        self.assertIn("(relayed by hand; never pairs)", (self.a / "TODO.md").read_text())

    def test_no_store_takes_a_hidden_repo_name(self):
        d = self.ws / "c"
        d.mkdir()
        r = self.todo("-C", d, "init", "--prefix", "cc", "--repo", ".layer", ok=False)
        self.assertIn("hidden", r.stdout + r.stderr)
        self.assertFalse((d / "todo.json").exists())

    def test_a_missing_counterpart_is_red(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "b")
        data = self.store(self.b)
        data["items"] = []
        self.write_json(self.b / "todo.json", data)
        self.assertFails(self.a, "reports", "counterpart bb-1 is in neither")

    def test_a_counterpart_whose_parent_does_not_point_back_is_red(self):
        self.todo("-C", self.a, "add", "other", "--kind", "note")
        self.todo("-C", self.a, "report", "aa-1", "--to", "b")
        data = self.store(self.b)
        data["items"][0]["parent"] = "aa-2"
        self.write_json(self.b / "todo.json", data)
        self.assertFails(self.a, "reports", "has parent aa-2, not aa-1")

    def test_report_to_its_own_repo_is_refused(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "a", ok=False)


class EditReportedTo(Case):
    """`todo edit ID --reported-to REPO[:THEIR_ID]`: sets a report's owner, and its
    counterpart only when the owner's store confirms it; writes no other store."""

    REPORT = VOCAB.role("report_kind")

    def setUp(self):
        super().setUp()
        self.a, self.b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", self.a, "add", "their bug", "--kind", VOCAB.role("default_kind"))

    def rt(self):
        return self.store(self.a)["items"][0]["reported_to"]

    def test_only_a_report_carries_one(self):
        err = self.todo("-C", self.a, "edit", "aa-1", "--reported-to", "c", ok=False).stderr
        self.assertIn(f"add --kind {self.REPORT}", err)
        self.todo("-C", self.a, "edit", "aa-1", "--kind", self.REPORT, "--reported-to", "c")
        self.assertEqual(self.rt(), {"repo": "c", "date": "2026-10-04", "their_id": None})
        self.todo("-C", self.a, "edit", "aa-1", "--reported-to", "", ok=False)  # a report requires it

    def test_it_writes_no_other_store(self):
        before = (self.b / "todo.json").read_bytes()
        self.todo("-C", self.a, "edit", "aa-1", "--kind", self.REPORT, "--reported-to", "b")
        self.assertEqual((self.b / "todo.json").read_bytes(), before)
        self.assertEqual(self.rt()["their_id"], None)

    def test_their_id_is_taken_only_when_the_owner_confirms_it(self):
        self.todo("-C", self.b, "add", "unrelated", "--kind", VOCAB.role("default_kind"))
        self.todo("-C", self.b, "add", "the counterpart", "--kind", VOCAB.role("default_kind"), "--parent", "aa-1")
        edit = ("-C", self.a, "edit", "aa-1", "--kind", self.REPORT, "--reported-to")
        for bad, why in (("b:bb-1", "parent is None, not aa-1"), ("b:bb-9", "in neither"),
                         ("c:cc-1", "no scanned store"), ("a", "another repo"), (".layer:x-1", "hidden")):
            with self.subTest(bad=bad):
                self.assertIn(why, self.todo(*edit, bad, ok=False).stderr)
        self.assertIsNone(self.rt())
        self.todo(*edit, "b:bb-2")
        self.assertEqual(self.rt(), {"repo": "b", "date": "2026-10-04", "their_id": "bb-2"})
        self.check(self.a)

    def test_a_counterpart_the_owner_holds_pairs_without_its_id(self):
        self.todo("-C", self.b, "add", "the counterpart", "--kind", VOCAB.role("default_kind"), "--parent", "aa-1")
        out = self.todo("-C", self.a, "edit", "aa-1", "--kind", self.REPORT, "--reported-to", "b").stdout
        self.assertIn("paired with it", out)
        self.assertEqual(self.rt()["their_id"], "bb-1")

    def test_the_date_is_kept_for_the_same_repo_and_reset_for_another(self):
        self.todo("-C", self.a, "edit", "aa-1", "--kind", self.REPORT, "--reported-to", "c", today="2026-10-01")
        self.todo("-C", self.a, "edit", "aa-1", "--reported-to", "c", today="2026-10-03")
        self.assertEqual(self.rt()["date"], "2026-10-01")
        self.todo("-C", self.a, "edit", "aa-1", "--reported-to", "d", today="2026-10-03")
        self.assertEqual(self.rt(), {"repo": "d", "date": "2026-10-03", "their_id": None})

    def test_an_imported_report_unpaired_is_a_warning_and_a_made_one_is_red(self):
        self.todo("-C", self.a, "edit", "aa-1", "--kind", self.REPORT, "--reported-to", "b")
        self.assertFails(self.a, "reports", "has a store now")
        data = self.store(self.a)
        data["items"][0]["imported"] = {"sha": "0" * 12, "section": ["Reported"], "title_from": "lead", "sep": None}
        self.write_json(self.a / "todo.json", data)
        self.todo("-C", self.a, "render")
        out = self.check(self.a).stdout
        self.assertIn("WARN  reports   aa-1     imported, not paired with b's store", out)


class AddReportedTo(Case):
    """`todo add --kind report --reported-to REPO`: an open report needs its owner,
    so add takes it; a counterpart is paired later, by edit or report."""

    REPORT = VOCAB.role("report_kind")

    def setUp(self):
        super().setUp()
        self.a, self.b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", self.b, "add", "parentless", "--kind", VOCAB.role("default_kind"))

    def test_add_sets_the_owner_pairs_nothing_and_writes_no_other_store(self):
        before = (self.b / "todo.json").read_bytes()
        err = self.todo("-C", self.a, "add", "theirs", "--kind", self.REPORT, ok=False).stderr
        self.assertIn("needs --reported-to", err)
        self.todo("-C", self.a, "add", "theirs", "--kind", self.REPORT, "--reported-to", "b")
        self.assertEqual(self.store(self.a)["items"][0]["reported_to"],
                         {"repo": "b", "date": "2026-10-04", "their_id": None})
        self.assertEqual((self.b / "todo.json").read_bytes(), before)

    def test_a_counterpart_id_another_kind_or_its_own_repo_is_refused(self):
        for extra in (["--kind", self.REPORT, "--reported-to", "b:bb-1"],
                      ["--kind", VOCAB.role("default_kind"), "--reported-to", "b"],
                      ["--kind", self.REPORT, "--reported-to", "a"]):
            with self.subTest(extra=extra):
                self.todo("-C", self.a, "add", "theirs", *extra, ok=False)
        self.assertEqual(self.store(self.a)["items"], [])

    def test_every_field_a_refusal_asks_for_is_a_flag_of_add_and_edit(self):
        """validate names a missing required field as its flag: both verbs that
        call it must parse that flag, or the refusal asks for the impossible."""
        from todolib.cli import build_parser
        ps = build_parser()._subparsers._group_actions[0].choices
        need = {f for spec in (*VOCAB.kinds.values(), *(VOCAB.statuses[s] for s in VOCAB.open_statuses()))
                for f in spec.get("requires", [])}  # add and edit make open items only
        self.assertTrue(need)
        for verb in ("add", "edit"):
            flags = {s for a in ps[verb]._actions for s in a.option_strings}
            for f in sorted(need):
                with self.subTest(verb=verb, field=f):
                    self.assertIn("--" + f.replace("_", "-"), flags)
