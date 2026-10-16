"""Approval by rule (TD-B1, PLAN-todo-tool.md §10.1; Jacob 2026-10-12): an open item
of a rule kind, in its own repo, sized S or M, with work and done_when, touching no
settings and of no excluded work, counts as approved without `todo approve`.

The gates the plan names: a fixture for each condition shows the rule not applying
when that condition fails, and `dispatchable` names rule approvals separately. Also:
the rule's approval is never stored except by `todo dispatch` (and removed by
`dispatch --clear`), Jacob's own approval wins over it, `blockers` and
`dispatchable` still split the open items between them, and check fails a rule
approval written around the CLI."""
import json

from tests.helpers import Case
from todolib import approval
from todolib.vocab import VOCAB

RULE = VOCAB.approval_rule
KIND = RULE["kinds"][0]
SIZE = RULE["sizes"][0]
WORK = next(w for w in VOCAB.works if w not in RULE["exclude_works"])
NOT_KIND = next(k for k in VOCAB.kinds if k not in RULE["kinds"] and k != VOCAB.role("report_kind")
                and not VOCAB.kinds[k]["requires"])
NOT_SIZE = next(s for s in VOCAB.sizes if s not in RULE["sizes"])
JACOB = VOCAB.jacob_status
WAITS = f"{VOCAB.role('approval_waits_on')}"


def requires(kind):
    """The flags a kind's required fields need on `todo add` (a temp needs --retire)."""
    out = []
    for f in VOCAB.kinds[kind]["requires"]:
        out += [f"--{f.replace('_', '-')}", f"{f} text"]
    return out


class Rule(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")

    def add(self, *extra, kind=KIND, size=SIZE, work=WORK, done_when="dw"):
        args = ["-C", self.a, "add", "job", "--kind", kind, *requires(kind)]
        if work:
            args += ["--work", work]
        if size:
            args += ["--size", size]
        if done_when:
            args += ["--done-when", done_when]
        self.todo(*args, *extra)
        return self.store(self.a)["items"][-1]["id"]

    def view(self):
        return json.loads(self.todo("-C", self.a, "dispatchable", "--json").stdout)

    def roots(self):
        return json.loads(self.todo("-C", self.a, "blockers", "--json").stdout)

    def held_by_jacob(self, item_id):
        return any(item_id in g["ids"] and g["kind"] == "jacob" for g in self.roots()["roots"])

    def assert_ruled(self, item_id):
        v = self.view()
        self.assertEqual([r["id"] for r in v["by_rule"]], [f"todo:{item_id}"], v)
        self.assertEqual(v["dispatchable"], [], "a rule approval is never listed as Jacob's")
        self.assertEqual(v["by_rule"][0]["approved"], approval.rule_approval())
        self.assertFalse(any(item_id in g["ids"] for g in self.roots()["roots"]), "dispatchable, so no root holds it")
        self.assertIsNone(self.store(self.a)["items"][0]["approved"], "judged at the read, never stored")

    def assert_not_ruled(self, item_id, *, root="jacob"):
        v = self.view()
        self.assertEqual(v["by_rule"], [], v)
        self.assertEqual(v["dispatchable"], [], v)
        self.assertEqual(v["unapproved"], 1)
        hits = [g for g in self.roots()["roots"] if item_id in g["ids"]]
        self.assertEqual([g["kind"] for g in hits], [root], hits)
        self.todo("-C", self.a, "dispatch", item_id, ok=False)

    # the passing fixture, then one failing fixture per condition
    def test_an_item_meeting_every_condition_is_approved_by_rule_and_listed_apart(self):
        self.assert_ruled(self.add())
        out = self.todo("-C", self.a, "dispatchable").stdout
        self.assertIn(f"approved by rule {RULE['id']}", out)
        self.assertIn("todo:aa-1", out)

    def test_every_rule_kind_is_approved(self):
        for kind in RULE["kinds"]:
            with self.subTest(kind):
                self.tearDown()
                self.setUp()
                self.assert_ruled(self.add(kind=kind))

    def test_another_kind_is_not(self):
        self.assert_not_ruled(self.add(kind=NOT_KIND))

    def test_another_repo_is_not(self):
        self.assert_not_ruled(self.add("--repo", "elsewhere"))

    def test_a_size_outside_the_rule_or_none_is_not(self):
        self.assert_not_ruled(self.add(size=NOT_SIZE), root="field")
        self.tearDown()
        self.setUp()
        self.assert_not_ruled(self.add(size=None), root="field")

    def test_no_work_or_no_done_when_is_not(self):
        self.assert_not_ruled(self.add(work=None), root="field")
        self.tearDown()
        self.setUp()
        self.assert_not_ruled(self.add(done_when=None), root="field")

    def test_a_status_other_than_open_is_not(self):
        self.assert_not_ruled(self.add("--status", JACOB, "--waits-on", WAITS))

    def test_an_excluded_work_is_not(self):
        for work in RULE["exclude_works"]:
            with self.subTest(work):
                self.tearDown()
                self.setUp()
                self.assert_not_ruled(self.add(work=work))

    def test_an_item_touching_settings_is_not(self):
        for path in (".claude/settings.json", "sub/.claude/settings.local.json"):
            with self.subTest(path):
                self.tearDown()
                self.setUp()
                self.assert_not_ruled(self.add("--files", path))
        self.tearDown()
        self.setUp()
        self.assert_ruled(self.add("--files", "todolib/cli.py"))

    def test_the_misses_name_each_failed_condition(self):
        it = {"kind": NOT_KIND, "repo": "b", "size": NOT_SIZE, "work": RULE["exclude_works"][0], "done_when": None,
              "status": JACOB, "files": [".claude/settings.json"]}
        why = approval.rule_misses(it, "a")
        self.assertEqual(len(why), 7, why)

    # what the rule approval is, and is not
    def test_jacobs_own_approval_wins_and_is_listed_as_his(self):
        iid = self.add()
        self.todo("-C", self.a, "approve", iid, "--source", "Jacob in chat")
        v = self.view()
        self.assertEqual([r["id"] for r in v["dispatchable"]], ["todo:aa-1"])
        self.assertEqual(v["by_rule"], [])

    def test_dispatch_stores_the_rule_approval_and_clear_removes_it(self):
        iid = self.add()
        out = self.todo("-C", self.a, "dispatch", iid).stdout
        self.assertIn(f"rule {RULE['id']}", out)
        stored = self.store(self.a)["items"][0]
        self.assertEqual(stored["approved"], approval.rule_approval())
        self.assertTrue(approval.is_rule(stored["approved"]))
        self.check(self.a)
        v = self.view()
        self.assertEqual([d["id"] for d in v["dispatched"]], ["todo:aa-1"])
        self.assertTrue(v["dispatched"][0]["by_rule"])
        self.todo("-C", self.a, "dispatch", iid, "--clear")
        self.assertIsNone(self.store(self.a)["items"][0]["approved"])
        self.assert_ruled(iid)

    def test_dispatch_refuses_an_item_the_rule_does_not_cover_and_says_why(self):
        iid = self.add(kind=NOT_KIND)
        r = self.todo("-C", self.a, "dispatch", iid, ok=False)
        self.assertIn(f"rule {RULE['id']} does not cover it", r.stderr)
        self.assertIn(f"kind {NOT_KIND}", r.stderr)

    def test_check_fails_a_rule_approval_stored_on_an_undispatched_item(self):
        iid = self.add(kind=NOT_KIND)
        data = self.store(self.a)
        data["items"][0]["approved"] = approval.rule_approval()
        self.write_json(self.a / "todo.json", data)
        r = self.check(self.a, ok=False)
        self.assertIn(f"rule {RULE['id']} approval stored on an item not dispatched", r.stdout)
        # and the stored copy approves nothing: the rule is judged afresh
        self.assertEqual(self.view()["by_rule"], [])
        self.assertTrue(self.held_by_jacob(iid))


class Vocab(Case):
    def test_the_rule_names_only_declared_values(self):
        self.assertTrue(set(RULE["kinds"]) <= set(VOCAB.kinds))
        self.assertTrue(set(RULE["sizes"]) <= set(VOCAB.ready_sizes))
        self.assertTrue(set(RULE["needs"]) <= set(VOCAB.fields))
        self.assertTrue(set(RULE["exclude_works"]) <= set(VOCAB.works))
        self.assertNotIn(VOCAB.role("report_kind"), RULE["kinds"])
        self.assertTrue(RULE["exclude_files"])

    def test_an_undeclared_value_in_the_rule_refuses_to_load(self):
        from todolib.vocab import VOCAB_PATH, Vocab
        base = json.loads(VOCAB_PATH.read_text())
        for key, bad in (("kinds", ["nosuch"]), ("sizes", ["XL"]), ("needs", ["nosuch"]),
                         ("exclude_works", ["nosuch"]), ("source", " "), ("approved", "someday")):
            with self.subTest(key):
                data = json.loads(json.dumps(base))
                data["approval"]["rule"][key] = bad
                p = self.tmp / f"vocab-{key}.json"
                p.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    Vocab(p)
