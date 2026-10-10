"""Items made from a plan go stale when the plan changes (Jacob, 2026-10-09;
README "Plan pins"). `--pin-plan` records each plan:FILE§n section as the setup
tool's `plans show` prints it; `todo stale-plans` lists the open items whose
section changed, is gone, or was never pinned, across every store.

These run the real setup tool (found the way the CLI finds it by default), so the
seam with its output is what is tested: a stub would agree with this module by
construction."""
import hashlib
import json
import subprocess

from tests.helpers import TODAY, Case
from todolib import plans
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
PLAN = "# X\n\n## 1. First\n\none\n\n## 2. Second\n\ntwo\n"
LATER = "2026-10-06"


class Pins(Case):
    def setUp(self):
        super().setUp()
        cli, why = plans.resolve_cli(None)
        if why:
            self.fail(f"these tests read plans through the setup tool: {why}")
        self.cli = cli
        self.plan = self.ws / "PLAN-x.md"
        self.plan.write_text(PLAN)
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")

    def add(self, repo, title, *tags, pin=True, ok=True):
        return self.todo("-C", repo, "--root", self.ws, "add", title, "--kind", NOTE, "--tags", *tags,
                         *(["--pin-plan"] if pin else []), ok=ok)

    def stale(self, *extra, ok=True, cwd=None):
        args = ([] if cwd else ["-C", self.a, "--root", self.ws]) + ["stale-plans", "--json", *extra]
        r = self.todo(*args, ok=ok, cwd=cwd)
        return json.loads(r.stdout), r

    def rows(self, view):
        return sorted((r["id"], r["plan"], r["state"]) for r in view["stale"])

    def test_an_unchanged_section_lists_nothing(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        view, r = self.stale()
        self.assertEqual((view["stale"], view["fresh"], view["unchecked"], r.returncode), ([], 1, [], 0))
        out = self.todo("-C", self.a, "--root", self.ws, "stale-plans").stdout
        self.assertIn("(no open item's plan section has changed", out)

    def test_the_pin_is_the_section_as_setup_prints_it_not_the_file(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        pin = self.store(self.a)["items"][0]["plan_pins"]
        shown = subprocess.run([str(self.cli), "plans", "show", str(self.plan), "§1"], capture_output=True)
        self.assertEqual(pin, [{"plan": "PLAN-x.md§1", "digest": hashlib.sha256(shown.stdout).hexdigest(),
                                "date": TODAY}])
        self.assertNotEqual(pin[0]["digest"], hashlib.sha256(self.plan.read_bytes()).hexdigest())
        # so an edit to another section leaves this one fresh
        self.plan.write_text(PLAN.replace("two\n", "two, rewritten\n"))
        self.assertEqual(self.stale()[0]["stale"], [])

    def test_a_changed_section_lists_its_items_in_every_store_and_no_other(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        self.add(self.a, "from two", "plan:PLAN-x.md§2")
        self.add(self.b, "also from one", "plan:PLAN-x.md§1")
        self.plan.write_text(PLAN.replace("one\n", "one, rewritten\n"))
        view, r = self.stale()
        self.assertEqual(self.rows(view), [("todo:aa-1", "PLAN-x.md §1", "changed"),
                                           ("todo:bb-1", "PLAN-x.md §1", "changed")])
        self.assertEqual({x["last_matched"] for x in view["stale"]}, {TODAY})
        self.assertEqual((view["fresh"], r.returncode), (1, 0))
        out = self.todo("-C", self.a, "--root", self.ws, "stale-plans").stdout
        self.assertIn("todo:bb-1", out)
        self.assertIn(f"PLAN-x.md §1", out)
        self.assertIn(f"last matched {TODAY}", out)

    def test_a_repin_after_the_update_makes_it_fresh_and_moves_last_matched(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        self.plan.write_text(PLAN.replace("one\n", "one, rewritten\n"))
        self.todo("-C", self.a, "--root", self.ws, "edit", "aa-1", "--pin-plan", today=LATER)
        self.assertEqual(self.store(self.a)["items"][0]["plan_pins"][0]["date"], LATER)
        self.assertEqual(self.stale()[0]["stale"], [])
        self.plan.write_text(PLAN)
        self.assertEqual([x["last_matched"] for x in self.stale()[0]["stale"]], [LATER])

    def test_a_removed_section_or_file_says_section_gone(self):
        self.add(self.a, "from two", "plan:PLAN-x.md§2")
        self.plan.write_text(PLAN.split("## 2.")[0])
        view, _ = self.stale()
        self.assertEqual(self.rows(view), [("todo:aa-1", "PLAN-x.md §2", "section gone")])
        self.assertIn("no section §2", view["stale"][0]["why"])
        self.plan.unlink()
        view, _ = self.stale()
        self.assertEqual(self.rows(view), [("todo:aa-1", "PLAN-x.md §2", "section gone")])
        self.assertIn("is not in", view["stale"][0]["why"])

    def test_a_plan_tag_with_no_pin_is_never_pinned_not_fresh(self):
        self.add(self.a, "unpinned", "plan:PLAN-x.md§1", pin=False)
        self.add(self.a, "whole plan", "plan:PLAN-x.md", pin=False)
        view, r = self.stale()
        self.assertEqual(self.rows(view), [("todo:aa-1", "PLAN-x.md §1", "never pinned"),
                                           ("todo:aa-2", "PLAN-x.md", "never pinned")])
        self.assertEqual((view["fresh"], r.returncode), (0, 0))
        self.assertIsNone(view["stale"][0]["last_matched"])
        self.assertIn("never matched", self.todo("-C", self.a, "--root", self.ws, "stale-plans").stdout)

    def test_pin_plan_refuses_what_it_cannot_read_and_writes_nothing(self):
        self.add(self.a, "no section", "plan:PLAN-x.md", ok=False)
        r = self.add(self.a, "missing section", "plan:PLAN-x.md§9", ok=False)
        self.assertIn("no section §9", r.stderr)
        r = self.add(self.a, "missing plan", "plan:PLAN-gone.md§1", ok=False)
        self.assertIn("is not in", r.stderr)
        r = self.todo("-C", self.a, "--root", self.ws, "add", "no cli", "--kind", NOTE, "--tags", "plan:PLAN-x.md§1",
                      "--pin-plan", "--plans-cli", self.tmp / "absent", ok=False)
        self.assertIn("no plans CLI", r.stderr)
        self.assertEqual(self.store(self.a)["items"], [])

    def test_a_plans_cli_that_cannot_answer_is_unchecked_never_fresh(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        self.add(self.a, "unpinned", "plan:PLAN-x.md§2", pin=False)
        view, r = self.stale("--plans-cli", self.tmp / "absent", ok=None)
        self.assertEqual(r.returncode, 3)
        self.assertIn("UNCHECKED", r.stderr)
        self.assertEqual([u["id"] for u in view["unchecked"]], ["todo:aa-1"])
        self.assertEqual(view["fresh"], 0)
        self.assertEqual(self.rows(view), [("todo:aa-2", "PLAN-x.md §2", "never pinned")])

    def test_an_ambiguous_section_is_unchecked_not_gone(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        self.plan.write_text(PLAN + "\n## 1. First again\n\nagain\n")
        view, r = self.stale(ok=None)
        self.assertEqual((r.returncode, view["stale"], view["fresh"]), (3, [], 0))
        self.assertIn("ambiguous", view["unchecked"][0]["why"])

    def test_plans_dir_is_where_the_files_are_read(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        other = self.tmp / "plans"
        other.mkdir()
        (other / "PLAN-x.md").write_text(PLAN.replace("one\n", "elsewhere\n"))
        self.assertEqual(self.rows(self.stale("--plans-dir", other)[0]), [("todo:aa-1", "PLAN-x.md §1", "changed")])

    def test_taking_the_tag_off_takes_its_pin(self):
        self.add(self.a, "from both", "plan:PLAN-x.md§1", "plan:PLAN-x.md§2")
        self.assertEqual(len(self.store(self.a)["items"][0]["plan_pins"]), 2)
        self.todo("-C", self.a, "--root", self.ws, "edit", "aa-1", "--tags", "plan:PLAN-x.md§2")
        self.assertEqual([p["plan"] for p in self.store(self.a)["items"][0]["plan_pins"]], ["PLAN-x.md§2"])
        self.todo("-C", self.a, "--root", self.ws, "edit", "aa-1", "--tags", "origin:jacob")
        self.assertIsNone(self.store(self.a)["items"][0]["plan_pins"])
        self.check(self.a)

    def test_repo_narrows_answers_from_the_root_and_closed_items_are_left_out(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        self.add(self.b, "also from one", "plan:PLAN-x.md§1")
        self.add(self.b, "closed", "plan:PLAN-x.md§1")
        self.todo("-C", self.b, "done", "bb-2", "--resolution", "r")
        self.plan.write_text(PLAN.replace("one\n", "one, rewritten\n"))
        self.assertEqual([x["id"] for x in self.stale("--repo", "b")[0]["stale"]], ["todo:bb-1"])
        self.assertEqual(self.rows(self.stale(cwd=self.ws)[0]), [("todo:aa-1", "PLAN-x.md §1", "changed"),
                                                                 ("todo:bb-1", "PLAN-x.md §1", "changed")])

    def test_split_children_carry_the_pins(self):
        self.todo("-C", self.a, "--root", self.ws, "add", "big", "--kind", NOTE, "--size", VOCAB.split_size,
                  "--tags", "plan:PLAN-x.md§1", "--pin-plan")
        self.todo("-C", self.a, "split", "aa-1", "one", "two", "--size", VOCAB.ready_sizes[0])
        items = {it["id"]: it for it in self.store(self.a)["items"]}
        self.assertEqual(items["aa-2"]["plan_pins"], items["aa-1"]["plan_pins"])

    def test_show_and_render_carry_the_pin(self):
        self.add(self.a, "from one", "plan:PLAN-x.md§1")
        line = f"plan pins: PLAN-x.md§1 as of {TODAY} (sha256 "
        self.assertIn("· " + line, (self.a / "TODO.md").read_text())
        self.assertIn(f"plan_pins: PLAN-x.md§1 as of {TODAY} (sha256 ", self.todo("-C", self.a, "show", "aa-1").stdout)


class Checked(Case):
    def test_check_fails_a_pin_written_around_the_cli(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "job", "--kind", NOTE, "--tags", "plan:PLAN-x.md§1")
        good = {"plan": "PLAN-x.md§1", "digest": "0" * 64, "date": TODAY}
        cases = [([], "non-empty list"),
                 ([dict(good, digest="abc")], "not a sha256"),
                 ([dict(good, plan="PLAN-x.md§2")], "no plan:FILE§n tag"),
                 ([dict(good, date="today")], "not YYYY-MM-DD"),
                 ([good, good], "twice"),
                 ([{"plan": "PLAN-x.md§1"}], "is not {plan, digest, date}")]
        for pins, text in cases:
            with self.subTest(pins=pins):
                data = self.store(a)
                data["items"][0]["plan_pins"] = pins
                self.write_json(a / "todo.json", data)
                self.assertFails(a, "schema", text)
        data = self.store(a)
        data["items"][0]["plan_pins"] = [good]
        self.write_json(a / "todo.json", data)
        self.todo("-C", a, "render")  # the fixture changed todo.json; the render follows it
        self.check(a)
