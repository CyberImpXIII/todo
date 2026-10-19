"""`todo ready --json` and the workspace form (PLAN-routing-tree.md §25 step 2): the
release job reads what is ready in one call, from the workspace root, as data. The
document is the text form's rows, in its order; --json changes the output and not
the answer; a store that cannot be read makes either form UNCHECKED (exit 3), never
a shorter list that reads as complete."""
import json
import os

from tests.helpers import TODAY, Case
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
WORK = next(iter(VOCAB.works))
OTHER_WORK = next(w for w in VOCAB.works if w != WORK)
S = VOCAB.ready_sizes[0]
READY = ["--work", WORK, "--done-when", "dw", "--size", S]


def text_ids(out):
    """The ids the text form lists (its rows; not the refused block or a notice)."""
    return [ln.split()[0] for ln in out.splitlines() if ln and not ln.startswith((" ", "(", "refused", "UNREADABLE"))]


class ReadyJson(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")
        self.todo("-C", self.a, "add", "here", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "add", "unsized", "--kind", NOTE, "--work", WORK, "--done-when", "dw")
        self.todo("-C", self.b, "add", "there", "--kind", NOTE, *READY)
        self.todo("-C", self.b, "add", "other work", "--kind", NOTE, "--work", OTHER_WORK, "--done-when", "dw",
                  "--size", S)

    def ready(self, *extra, cwd=None, ok=True):
        c = ["-C", self.a, "--root", self.ws] if cwd is None else []
        return self.todo(*c, "ready", *extra, cwd=cwd, ok=ok)

    def doc(self, *extra, cwd=None, ok=True):
        return json.loads(self.ready("--json", *extra, cwd=cwd, ok=ok).stdout)

    def test_the_flag_changes_the_output_and_not_the_answer(self):
        text = self.ready().stdout
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)  # without --json: lines, not a document
        d = self.doc()
        self.assertEqual(sorted(d), ["count", "ready", "refused", "root", "unreadable"])
        self.assertEqual([r["local_id"] for r in d["ready"]], text_ids(text))
        self.assertEqual(sorted(r["id"] for r in d["ready"]), ["todo:aa-1", "todo:bb-1", "todo:bb-2"])
        self.assertEqual(d["count"], 3)
        self.assertEqual([r["local_id"] for r in d["refused"]], ["aa-2"])
        self.assertIn("aa-2", text.split("refused", 1)[1])
        self.assertEqual(d["unreadable"], [])
        self.assertEqual(d["root"], str(self.ws.resolve()))

    def test_a_row_carries_its_store_and_brief(self):
        row = next(r for r in self.doc()["ready"] if r["id"] == "todo:bb-1")
        self.assertEqual({k: row[k] for k in ("repo", "work", "size", "title")},
                         {"repo": "b", "work": WORK, "size": S, "title": "there"})
        self.assertEqual(row["store"], str(self.b.resolve()))
        self.assertEqual(row["brief"], "todo brief todo:bb-1")

    def test_approval_and_dispatch_change_the_row_and_it_stays_listed(self):
        def row():
            return next(r for r in self.doc()["ready"] if r["id"] == "todo:aa-1")
        self.assertIsNone(row()["dispatched"])
        self.todo("-C", self.a, "approve", "aa-1", "--source", "Jacob in chat")
        approved = row()
        self.assertEqual(approved["approved"], {"by": VOCAB.approval_by, "date": TODAY, "source": "Jacob in chat"})
        self.assertFalse(approved["by_rule"])
        self.todo("-C", self.a, "dispatch", "aa-1", "--note", "n")
        self.assertEqual(row()["dispatched"], {"date": TODAY, "text": "n"})

    def test_approved_and_not_dispatched_rows_are_exactly_what_dispatchable_lists(self):
        """The seam with `todo dispatchable`: one judgement of approval, not two."""
        rule = VOCAB.approval_rule
        kind = rule["kinds"][0]
        needs = [x for f in VOCAB.kinds[kind]["requires"] for x in (f"--{f.replace('_', '-')}", f"{f} text")]
        self.todo("-C", self.b, "add", "by rule", "--kind", kind, *needs, "--size", rule["sizes"][0],
                  "--work", next(w for w in VOCAB.works if w not in rule["exclude_works"]), "--done-when", "dw")
        self.todo("-C", self.b, "approve", "bb-1", "--source", "s")
        self.todo("-C", self.b, "approve", "bb-2", "--source", "s")
        self.todo("-C", self.b, "dispatch", "bb-2")
        rows = self.doc()["ready"]
        mine = sorted(r["id"] for r in rows if r["approved"] is not None and not r["dispatched"])
        v = json.loads(self.todo("-C", self.a, "--root", self.ws, "dispatchable", "--json").stdout)
        theirs = sorted(r["id"] for r in v["dispatchable"] + v["by_rule"])
        self.assertIn("todo:bb-1", theirs)
        self.assertEqual([r["id"] for r in v["by_rule"]], ["todo:bb-3"])  # the rule's, not Jacob's
        self.assertEqual(mine, theirs)
        self.assertEqual({r["id"]: r["by_rule"] for r in rows if r["approved"] is not None and not r["dispatched"]},
                         {r["id"]: r in v["by_rule"] for r in v["dispatchable"] + v["by_rule"]})

    def test_repo_and_work_narrow_the_document(self):
        self.assertEqual([r["id"] for r in self.doc("--repo", "b")["ready"]], ["todo:bb-1", "todo:bb-2"])
        self.assertEqual([r["id"] for r in self.doc("--repo", "b", "--work", OTHER_WORK)["ready"]], ["todo:bb-2"])

    def test_nothing_ready_is_an_empty_list_and_exit_0(self):
        d = self.doc("--work", OTHER_WORK, "--repo", "a")
        self.assertEqual((d["ready"], d["count"]), ([], 0))

    def test_the_workspace_form_answers_from_the_root_with_no_store_of_its_own(self):
        d = self.doc(cwd=self.ws)
        self.assertEqual(sorted(r["id"] for r in d["ready"]), ["todo:aa-1", "todo:bb-1", "todo:bb-2"])
        self.assertEqual(d["root"], str(self.ws.resolve()))
        self.assertEqual(sorted(text_ids(self.ready(cwd=self.ws).stdout)), ["aa-1", "bb-1", "bb-2"])

    def test_an_unreadable_store_is_unchecked_in_either_form(self):
        path = self.b / "todo.json"
        os.chmod(path, 0o644)
        path.write_text("{")
        r = self.ready("--json", ok=None)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("UNCHECKED", r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual([r["id"] for r in d["ready"]], ["todo:aa-1"])
        self.assertEqual(len(d["unreadable"]), 1)
        t = self.ready(ok=None)
        self.assertEqual(t.returncode, 3, t.stdout + t.stderr)
        self.assertIn("UNREADABLE", t.stdout)
