"""A report to a repo with no store (PLAN-architecture.md §11 S4): when the scan
finds a git repo of that name without a todo.json, `todo report` files one bullet
in its hand-written TODO.md, marked todo:<id>, once; the item's evidence says so,
and their_id stays null until the repo has a store."""
import json

from tests.helpers import ROOT, TODAY, Case, git_repo
from todolib import store as storelib
from todolib.importer import plan_import
from todolib.vocab import VOCAB, Vocab

HEADING = "## " + VOCAB.fallback_heading
NOTE = VOCAB.role("default_kind")
REPORT = VOCAB.role("report_kind")


class Fallback(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "their bug", "--kind", VOCAB.role("default_kind"),
                  "--evidence", "ran x\nsaw y", "--done-when", "x passes")
        self.c = git_repo(self.ws / "c")

    def report(self, **kw):
        return self.todo("-C", self.a, "report", "aa-1", "--to", "c", **kw)

    def test_the_bullet_is_filed_once_and_the_evidence_says_so(self):
        (self.c / "TODO.md").write_text("# c\n\n## Own bugs\n\n- one\n")
        out = self.report().stdout
        self.assertIn("a bullet marked todo:aa-1 was added", out)
        self.assertIn("Commit it there", out)
        text = (self.c / "TODO.md").read_text()
        self.assertTrue(text.startswith("# c\n\n## Own bugs\n\n- one\n\n" + HEADING + "\n\n- todo:aa-1 from a "), text)
        self.assertIn("  evidence: ran x\n  saw y\n  done when: x passes\n", text)
        item = self.store(self.a)["items"][0]
        self.assertEqual(item["reported_to"]["their_id"], None)
        self.assertIn("as a bullet marked todo:aa-1", item["evidence"])
        out = self.report().stdout
        self.assertIn("names todo:aa-1 already: nothing added", out)
        self.assertEqual((self.c / "TODO.md").read_text(), text)
        self.assertEqual(self.store(self.a)["items"][0]["evidence"], item["evidence"])

    def test_a_second_report_joins_the_section_before_the_next_heading(self):
        (self.c / "TODO.md").write_text(f"# c\n\n{HEADING}\n\n- todo:zz-9 earlier\n\n## Notes\n\n- n\n")
        self.report()
        text = (self.c / "TODO.md").read_text()
        head, rest = text.split("## Notes", 1)
        self.assertIn("- todo:zz-9 earlier\n- todo:aa-1 from a", head)
        self.assertTrue(head.endswith(")\n\n"), head)
        self.assertEqual(rest, "\n\n- n\n")

    def test_no_file_yet_is_made(self):
        self.report()
        self.assertTrue((self.c / "TODO.md").read_text().startswith(HEADING + "\n\n- todo:aa-1 "))

    def test_a_longer_id_is_not_this_one(self):
        (self.c / "TODO.md").write_text("- todo:aa-10 another\n")
        self.assertIn("was added", self.report().stdout)
        self.assertFalse(storelib.marker_in("- todo:aa-10 x", "todo:aa-1"))
        self.assertTrue(storelib.marker_in("- todo:aa-1 x", "todo:aa-1"))

    def test_nothing_is_written_without_a_git_repo_or_when_the_name_is_ambiguous(self):
        self.todo("-C", self.a, "add", "second", "--kind", VOCAB.role("default_kind"))
        out = self.todo("-C", self.a, "report", "aa-2", "--to", "d").stdout  # no folder d at all
        self.assertIn("no counterpart yet", out)
        (self.ws / "e").mkdir()  # a folder, not a git repo
        self.todo("-C", self.a, "add", "third", "--kind", VOCAB.role("default_kind"))
        self.assertIn("no counterpart yet", self.todo("-C", self.a, "report", "aa-3", "--to", "e").stdout)
        self.assertFalse((self.ws / "e" / "TODO.md").exists())
        git_repo(self.ws / "x" / "c")
        out = self.report().stdout
        self.assertIn("2 repos are named c", out)
        self.assertFalse((self.c / "TODO.md").exists())
        self.assertFalse((self.ws / "x" / "c" / "TODO.md").exists())

    def test_vocab_refuses_a_nested_file_or_a_broken_heading(self):
        raw = json.loads((ROOT / "vocab.json").read_text())
        for block in ({"file": "docs/TODO.md", "heading": "h"}, {"file": "TODO.md", "heading": ""},
                      {"file": "TODO.md", "heading": "a\nb"}):
            with self.subTest(block):
                path = self.tmp / "vocab.json"
                path.write_text(json.dumps(dict(raw, report_fallback=block)))
                with self.assertRaises(ValueError):
                    Vocab(path)


class OwnerImports(Case):
    """td-70: the repo that was reported to later gets a store and imports its
    TODO.md. The bullet `todo report` filed there is the report's counterpart (parent
    the reported id), never a report from that repo to the one named like the
    marker's `todo:` prefix; the reporter's next run then pairs with it."""

    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "their bug", "--kind", NOTE, "--evidence", "ran x", "--done-when", "x passes")
        self.c = git_repo(self.ws / "c")
        git_repo(self.ws / VOCAB.service)  # a repo named like the marker's prefix, as tools/todo is

    def test_the_bullet_imports_as_the_counterpart_and_the_reporter_pairs_with_it(self):
        (self.c / "TODO.md").write_text("# c\n\n## Notes\n\n- one\n")
        self.todo("-C", self.a, "report", "aa-1", "--to", "c")
        self.todo("-C", self.c, "init", "--prefix", "cc")
        out = self.todo("-C", self.c, "--root", self.ws, "import", "TODO.md").stdout
        got = {it["title"]: (it["kind"], it["parent"], it["reported_to"]) for it in self.store(self.c)["items"]}
        self.assertEqual(got, {"one": (NOTE, None, None), "their bug": (NOTE, "aa-1", None)}, out)
        # Unpaired: the counterpart is right, so its store only warns; the report's FAILs.
        self.assertRegex(self.check(self.c).stdout, r"WARN +reports +cc-2 +parent aa-1 in a is not paired with it yet: "
                                                    r"`todo -C \S+ report aa-1 --to c` pairs them")
        self.assertFails(self.a, "reports", "pair it with `todo report aa-1 --to c`")
        out = self.todo("-C", self.a, "report", "todo:aa-1", "--to", "c").stdout  # the global form pairs too
        self.assertIn("c already holds cc-2 for aa-1", out)
        self.assertEqual(self.store(self.a)["items"][0]["reported_to"]["their_id"], "cc-2")
        self.assertEqual(len(self.store(self.c)["items"]), 2)
        for d in (self.a, self.c):
            self.assertNotRegex(self.check(d).stdout, r"(WARN|FAIL) +reports ")

    def test_a_counterpart_another_item_answers_fails(self):
        self.todo("-C", self.a, "report", "aa-1", "--to", "c")
        self.todo("-C", self.c, "init", "--prefix", "cc")
        self.todo("-C", self.c, "--root", self.ws, "import", "TODO.md")
        data = self.store(self.a)
        data["items"][0]["reported_to"]["their_id"] = "cc-9"
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.c, "reports", "parent aa-1 in a points at cc-9, not here")

    def test_only_under_the_fallback_heading_and_a_hand_bullet_there_gets_no_parent(self):
        lead = storelib.fallback_lead("todo:aa-1", "a", "2026-10-19", "their bug")
        repos = {"a", VOCAB.service}
        items, plan = imported(f"# c\n\n{HEADING}\n\n- {lead}\n\n- todo:aa-2 a hand note\n\n- no marker at all\n", repos)
        self.assertEqual([(it["kind"], it["parent"], it["title"]) for it in items],
                         [(NOTE, "aa-1", "their bug"), (NOTE, "aa-2", "todo:aa-2 a hand note"),
                          (NOTE, None, "no marker at all")])
        self.assertEqual([why for _, why in plan.listed], [f"under {VOCAB.fallback_heading!r} with no todo:<id> marker: "
                                                           "imported as a note with no parent"])
        # The same bullet under the reports heading is a report, as any other: the heading decides.
        items, _ = imported(f"# c\n\n## {VOCAB.kinds[REPORT]['heading']}\n\n- {lead}\n", repos)
        self.assertEqual((items[0]["kind"], items[0]["parent"]), (REPORT, None))

    def test_the_lead_reads_back_what_the_report_writes(self):
        lead = storelib.fallback_lead("todo:aa-1", "claudeTest", "2026-10-19", "a title: with (parens)")
        self.assertEqual(storelib.read_fallback_lead(lead),
                         {"marker": "todo:aa-1", "repo": "claudeTest", "date": "2026-10-19", "title": "a title: with (parens)"})
        self.assertIsNone(storelib.read_fallback_lead("todo:aa-1 a hand note"))


def imported(text, repos):
    class Owner:
        repo, items, closed = "c", [], []

        def owns(self, item_id):
            return False

    plan = plan_import(text, Owner(), TODAY, repos=repos)
    return [it for it, _ in plan.new], plan
