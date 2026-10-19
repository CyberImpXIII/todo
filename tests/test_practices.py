"""`todo brief` carries the practices (PLAN-services.md §3 A3, §4 step 7.4; README
"Practices in the brief"): the prose rows of the practice registry that apply to
the item's repo, by id, one line each, and the `practices:` line the report must
end with. Read through the real checks tool (`checks practices --json`), with a
fixture registry handed to it by tests/fixtures/checks-registry.sh: a stub would
agree with todolib/practices.py by construction, so the seam with that tool's
output is what is tested. A registry that cannot be read is UNCHECKED, never
"no practice applies"."""
import json
import subprocess

from tests.helpers import FIXTURES, Case, git_repo, workspace_file
from todolib import practices
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
READY = ["--work", next(iter(VOCAB.works)), "--size", VOCAB.ready_sizes[0], "--done-when", "it is done"]
WRAPPER = FIXTURES / "checks-registry.sh"
REGISTRY = FIXTURES / "practices-gates.json"
WORDS = VOCAB.practices
HEAD = WORDS["heading"]


def real_cli(case):
    cli, why = practices.resolve_cli(None)
    if why:
        case.fail(f"these tests read the practice rows through the checks tool: {why}")
    return cli


def block(out):
    """The brief's practices block: its first line to the end of the brief."""
    lines = out.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.startswith(HEAD + " ") or ln.startswith(HEAD + ":")]
    if len(starts) != 1:
        raise AssertionError(f"{len(starts)} practices blocks in:\n{out}")
    return lines[starts[0]:]


def ids(out):
    return [ln.strip().split(":", 1)[0] for ln in block(out)[1:] if ln.startswith("  ")]


class Fixture(Case):
    """The fixture registry: rows for all, for a, for b and for the folder x,
    and a principle, a gate, an unbuilt and a superseded row the brief leaves out."""

    def setUp(self):
        super().setUp()
        self.env = {"CHECKS_REAL": str(real_cli(self)), "CHECKS_REGISTRY": str(REGISTRY)}
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")
        (self.ws / "x").mkdir()

    def brief(self, store, iid, ok=True, cli=WRAPPER):
        return self.todo("-C", store, "--root", self.ws, "brief", iid, "--checks-cli", cli, env=self.env, ok=ok)

    def add(self, store, repo, title="work"):
        self.todo("-C", store, "add", title, "--kind", NOTE, "--repo", repo, *READY)
        return self.store(store)["items"][-1]["id"]

    def test_the_prose_rows_for_the_items_repo_and_no_others(self):
        out = self.brief(self.a, self.add(self.a, "a")).stdout
        self.assertEqual(ids(out), ["fx-everywhere", "fx-in-a"], "registry order; b's, x's, the gate, the unbuilt, "
                                                                 "the principle and the superseded row left out")
        lines = block(out)
        self.assertIn("2 prose row(s)", lines[0])
        self.assertIn("  fx-everywhere: must show: the log shows it", lines)
        self.assertIn("  fx-in-a: prose (a alone)", lines, "no `shows`: the words it was handed over with")
        self.assertEqual(lines[-1], f"Report line: {WORDS['report_line']}")

    def test_counterfactual_the_repo_changes_which_rows(self):
        out = self.brief(self.a, self.add(self.a, "b")).stdout
        self.assertEqual(ids(out), ["fx-everywhere", "fx-in-b"])

    def test_a_repo_named_by_its_folder_with_no_store(self):
        self.assertEqual(ids(self.brief(self.a, self.add(self.a, "x")).stdout), ["fx-everywhere", "fx-in-x"])

    def test_a_store_named_otherwise_than_its_folder_is_found_by_its_store(self):
        d = git_repo(self.ws / "folder")
        self.todo("-C", d, "init", "--prefix", "ff", "--repo", "a-name")
        out = self.brief(self.a, self.add(self.a, "a-name")).stdout
        self.assertIn("apply to folder;", block(out)[0], "the store's folder, not a folder named a-name")
        # counterfactual: a name no store holds and no folder bears
        out = self.brief(self.a, self.add(self.a, "no-such-repo")).stdout
        self.assertTrue(block(out)[0].startswith(f"{HEAD}: UNCHECKED: repo no-such-repo is no store's and no folder"))

    def test_no_row_applying_says_so_and_asks_for_the_none_line(self):
        (self.ws / "c").mkdir()
        out = self.brief(self.a, self.add(self.a, "c")).stdout
        self.assertEqual(ids(out), ["fx-everywhere"], "an all row applies to any folder")
        # a registry with no prose row for c at all
        reg = self.tmp / "gates.json"
        doc = json.loads(REGISTRY.read_text())
        doc["practices"]["rows"] = [r for r in doc["practices"]["rows"] if r["id"] != "fx-everywhere"
                                    and r["id"] != "fx-old"]
        reg.write_text(json.dumps(doc))
        self.env["CHECKS_REGISTRY"] = str(reg)
        out = self.brief(self.a, self.add(self.a, "c", "again")).stdout
        self.assertEqual(block(out), [f"{HEAD}: no prose row of the practice registry applies to c. {WORDS['none_line']}"])

    def test_an_invalid_registry_is_unchecked_never_none_apply(self):
        reg = self.tmp / "gates.json"
        doc = json.loads(REGISTRY.read_text())
        doc["practices"]["rows"][1]["held"]["kind"] = "not-a-kind"
        reg.write_text(json.dumps(doc))
        self.env["CHECKS_REGISTRY"] = str(reg)
        r = self.brief(self.a, self.add(self.a, "a"))
        self.assertEqual(r.returncode, 0, "the brief itself still stands")
        self.assertTrue(block(r.stdout)[0].startswith(f"{HEAD}: UNCHECKED: `checks practices --json` gave no rows"))
        self.assertNotIn("no prose row", r.stdout)
        self.assertIn(WORDS["unchecked"], r.stdout)

    def test_an_empty_registry_is_unchecked(self):
        # the real checks refuses a registry with no rows (exit 2: the next
        # assertion); a tool that printed {"rows": []} is still no reading
        reg = self.tmp / "gates.json"
        doc = json.loads(REGISTRY.read_text())
        doc["practices"]["rows"] = []
        reg.write_text(json.dumps(doc))
        self.env["CHECKS_REGISTRY"] = str(reg)
        iid = self.add(self.a, "a")
        self.assertIn(f"{HEAD}: UNCHECKED: `checks practices --json` gave no rows", self.brief(self.a, iid).stdout)
        out = self.brief(self.a, iid, cli=FIXTURES / "checks-no-rows.sh").stdout
        self.assertTrue(block(out)[0].startswith(f"{HEAD}: UNCHECKED: `checks practices --json` printed no rows"),
                        block(out)[0])

    def test_no_checks_cli_or_one_that_prints_no_json_is_unchecked(self):
        iid = self.add(self.a, "a")
        for cli, says in ((self.tmp / "absent", "no checks CLI at"), ("/bin/echo", "gave no rows"),
                          ("/usr/bin/true", "gave no rows")):
            with self.subTest(cli=str(cli)):
                r = self.brief(self.a, iid, cli=cli)
                self.assertIn("What: work", r.stdout, "the rest of the brief is printed")
                first = block(r.stdout)[0]
                self.assertTrue(first.startswith(f"{HEAD}: UNCHECKED:"), first)
                self.assertIn(says, first)
                self.assertEqual(ids(r.stdout), [])

    def test_an_item_naming_no_repo_is_unchecked(self):
        # `todo add` fills the repo from the store, so a repo-less item is only a
        # hand-edited store's; the reader says so rather than guessing the root
        lines = practices.brief_lines(WRAPPER, self.ws, None, None, WORDS)
        self.assertEqual(lines, [f"{HEAD}: UNCHECKED: the item names no repo. {WORDS['unchecked']}"])
        self.assertEqual(practices.location(self.ws, None, ""), (None, "the item names no repo"))


class RealRegistry(Case):
    """The checks tool's own registry, as `todo brief` reads it by default: its
    output parses, and the brief lists exactly the live prose rows that apply."""

    def test_the_real_rows_parse_and_the_brief_lists_the_prose_ones(self):
        cli = real_cli(self)
        rows, why = practices.rows(cli, "a")
        self.assertIsNone(why)
        r = subprocess.run([str(cli), "practices", "--json", "--from", "/dev/stdin"], capture_output=True, text=True,
                           input=json.dumps({"repos": [{"rel": "a", "results": []}]}))
        expect = [x["id"] for x in json.loads(r.stdout)["rows"] if x.get("status") == "live"
                  and x["held"]["kind"] == "prose" and (x["applies"] == "all" or "a" in x["applies"])]
        self.assertTrue(expect, "the registry has prose rows for every repo (applies all); none would test nothing")
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "work", "--kind", NOTE, "--repo", "a", *READY)
        out = self.todo("-C", a, "--root", self.ws, "brief", "aa-1").stdout
        self.assertEqual(ids(out), expect)


class Words(Case):
    def test_the_report_line_names_the_line_and_every_state(self):
        self.assertTrue(WORDS["report_line"].startswith("End your report with one line `" + WORDS["line"] + " "))
        for s in WORDS["states"]:
            self.assertIn(f"<id> {s}:", WORDS["report_line"])
        self.assertIn(WORDS["line"], WORDS["none_line"])
        self.assertIn(WORDS["line"], WORDS["unchecked"])

    def test_the_states_are_the_plans_cell_states(self):
        plan = workspace_file("PLAN-services.md")
        if plan is None:
            self.skipTest("PLAN-services.md is not above this repo (a lone clone)")
        part = plan.read_text().split("**Every cell in `checks practices` is one of four:**", 1)
        self.assertEqual(len(part), 2, "PLAN-services.md §3 no longer lists the four cell states where it did")
        cells = part[1].split("\n  - A prose row", 1)[0]
        for s in WORDS["states"]:
            self.assertIn(f"`{s}", cells, f"{s} is no cell state of the plan's")
