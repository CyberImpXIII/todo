"""What can be dispatched now (Jacob, 2026-10-09; README "Dispatch"): `todo
dispatchable` lists the open items Jacob approved (`todo approve`), not dispatched
(`todo dispatch`), and ready as `todo brief` judges it, across every scanned store.
Every approved item is accounted for (listed, held with why, or dispatched) and the
unapproved ones are counted, never silently dropped."""
import json

from tests.helpers import TODAY, Case
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
READY = ["--work", next(iter(VOCAB.works)), "--done-when", "dw", "--size", VOCAB.ready_sizes[0]]


class Dispatchable(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")

    def view(self, *extra, cwd=None, ok=True):
        args = ["--root", self.ws] if cwd is None else []
        args += ["dispatchable", "--json", *extra]
        r = self.todo(*(["-C", self.a] if cwd is None else []), *args, cwd=cwd, ok=ok)
        return json.loads(r.stdout)

    def ids(self, view, key="dispatchable"):
        return [r["id"] for r in view[key]]

    def test_an_unapproved_item_is_left_out_and_counted(self):
        self.todo("-C", self.a, "add", "not approved", "--kind", NOTE, *READY)
        v = self.view()
        self.assertEqual(self.ids(v), [])
        self.assertEqual(self.ids(v, "held"), [])
        self.assertEqual(v["unapproved"], 1)

    def test_an_approved_ready_item_is_listed_with_its_pointer_from_every_store(self):
        self.todo("-C", self.a, "add", "here", "--kind", NOTE, *READY)
        self.todo("-C", self.b, "add", "there", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "Jacob in chat")
        self.todo("-C", self.b, "approve", "bb-1", "--source", "Jacob in chat", "--date", "2026-10-01")
        v = self.view()
        self.assertEqual(sorted(self.ids(v)), ["todo:aa-1", "todo:bb-1"])
        row = next(r for r in v["dispatchable"] if r["id"] == "todo:bb-1")
        self.assertEqual(row["repo"], "b")
        self.assertEqual(row["approved"], {"by": VOCAB.approval_by, "date": "2026-10-01", "source": "Jacob in chat"})
        self.assertEqual(row["brief"], "todo brief todo:bb-1")
        self.assertTrue(row["mark"].endswith(f"-C {self.b.resolve()} dispatch bb-1"), row["mark"])
        out = self.todo("-C", self.a, "--root", self.ws, "dispatchable").stdout
        self.assertIn("todo:aa-1", out)
        self.assertIn("brief: todo brief todo:aa-1", out)

    def test_a_dispatched_item_is_left_out_until_cleared(self):
        self.todo("-C", self.a, "add", "job", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "s")
        self.todo("-C", self.a, "dispatch", "aa-1", "--note", "the 2026-10-04 Dispatch")
        self.assertEqual(self.store(self.a)["items"][0]["dispatched"], {"date": TODAY, "text": "the 2026-10-04 Dispatch"})
        v = self.view()
        self.assertEqual(self.ids(v), [])
        self.assertEqual(self.ids(v, "dispatched"), ["todo:aa-1"])
        self.todo("-C", self.a, "dispatch", "aa-1", ok=False)  # once only
        self.todo("-C", self.a, "dispatch", "aa-1", "--clear")
        self.assertEqual(self.ids(self.view()), ["todo:aa-1"])

    def test_an_approved_item_not_ready_is_held_with_why(self):
        self.todo("-C", self.a, "add", "no done-when", "--kind", NOTE, "--work", next(iter(VOCAB.works)))
        self.todo("-C", self.a, "add", "waiting", "--kind", NOTE, *READY, "--status", VOCAB.open_statuses()[1])
        self.todo("-C", self.a, "add", "blocked", "--kind", NOTE, *READY, "--blocked-by", "aa-1")
        for i in (1, 2, 3):
            self.todo("-C", self.a, "approve", f"aa-{i}", "--source", "s")
        v = self.view()
        self.assertEqual(self.ids(v), [])
        why = {h["id"]: "; ".join(h["why"]) for h in v["held"]}
        self.assertIn("missing done_when", why["todo:aa-1"])
        self.assertIn(f"status {VOCAB.open_statuses()[1]}", why["todo:aa-2"])
        self.assertIn("blocked by aa-1", why["todo:aa-3"])

    def test_dispatch_refuses_an_unapproved_item_and_approve_needs_a_source(self):
        self.todo("-C", self.a, "add", "job", "--kind", NOTE, *READY)
        err = self.todo("-C", self.a, "dispatch", "aa-1", ok=False).stderr
        self.assertIn("carries no approval", err)
        self.assertIsNone(self.store(self.a)["items"][0].get("dispatched"))
        self.todo("-C", self.a, "approve", "aa-1", ok=False)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "two\nlines", ok=False)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "s", "--date", "2099-01-01", ok=False)
        self.assertIsNone(self.store(self.a)["items"][0].get("approved"))

    def test_approval_clears_only_while_not_dispatched(self):
        self.todo("-C", self.a, "add", "job", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "s")
        self.todo("-C", self.a, "dispatch", "aa-1")
        self.todo("-C", self.a, "approve", "aa-1", "--clear", ok=False)
        self.todo("-C", self.a, "dispatch", "aa-1", "--clear")
        self.todo("-C", self.a, "approve", "aa-1", "--clear")
        self.assertIsNone(self.store(self.a)["items"][0]["approved"])
        self.assertEqual(self.view()["unapproved"], 1)

    def test_split_children_carry_the_approval_and_the_parent_is_not_held(self):
        self.todo("-C", self.a, "add", "big", "--kind", NOTE, "--work", next(iter(VOCAB.works)), "--done-when", "dw",
                  "--size", VOCAB.split_size)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "s")
        self.todo("-C", self.a, "split", "aa-1", "one", "two", "--size", VOCAB.ready_sizes[0])
        self.todo("-C", self.a, "edit", "aa-2", "--done-when", "one done")
        self.todo("-C", self.a, "edit", "aa-3", "--done-when", "two done")
        v = self.view()
        self.assertEqual(sorted(self.ids(v)), ["todo:aa-2", "todo:aa-3"])
        self.assertEqual(self.ids(v, "held"), [])

    def test_it_answers_from_the_workspace_root_with_no_store_of_its_own(self):
        self.todo("-C", self.b, "add", "there", "--kind", NOTE, *READY)
        self.todo("-C", self.b, "approve", "bb-1", "--source", "s")
        self.assertEqual(self.ids(self.view(cwd=self.ws)), ["todo:bb-1"])

    def test_repo_narrows_the_list(self):
        self.todo("-C", self.a, "add", "here", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "add", "for b", "--kind", NOTE, *READY, "--repo", "b")
        for i in (1, 2):
            self.todo("-C", self.a, "approve", f"aa-{i}", "--source", "s")
        self.assertEqual(self.ids(self.view("--repo", "b")), ["todo:aa-2"])

    def test_render_show_and_brief_carry_approval_and_dispatch(self):
        self.todo("-C", self.a, "add", "job", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "approve", "aa-1", "--source", "his words")
        self.todo("-C", self.a, "dispatch", "aa-1", "--note", "n")
        line = f"approved: {VOCAB.approval_by} {TODAY}: his words"
        self.assertIn("· " + line, (self.a / "TODO.md").read_text())
        self.assertIn(f"· dispatched: {TODAY}: n", (self.a / "TODO.md").read_text())
        self.assertIn(line, self.todo("-C", self.a, "show", "aa-1").stdout)
        brief = self.todo("-C", self.a, "brief", "aa-1").stdout
        self.assertIn(f"Approved: {VOCAB.approval_by} {TODAY}: his words", brief)
        self.assertIn(f"Dispatched: {TODAY}: n", brief)
        self.check(self.a)


class Checked(Case):
    def test_check_fails_a_malformed_approval_or_dispatch(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "job", "--kind", NOTE)
        good = {"by": VOCAB.approval_by, "date": TODAY, "source": "s"}
        cases = [({"approved": "yes"}, "approved must be"),
                 ({"approved": dict(good, by="someone-else")}, "approved must be"),
                 ({"approved": dict(good, source="")}, "approved must be"),
                 ({"approved": good, "dispatched": {"date": "today", "text": None}}, "dispatched must be"),
                 ({"dispatched": {"date": TODAY, "text": None}}, "dispatched without approved")]
        for fields, text in cases:
            with self.subTest(fields=fields):
                data = self.store(a)
                data["items"][0].update({"approved": None, "dispatched": None, **fields})
                self.write_json(a / "todo.json", data)
                self.assertFails(a, "schema", text)
