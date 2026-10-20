"""`todo list --json` (td-59): the one way a reader outside this tool gets a store's
open items as data, so none opens todo.json itself and none breaks when the store
moves to todo.db. The document is the text form's rows, in its order, each record
whole; the filters narrow it as they narrow the text; it reads the same before and
after `todo migrate`; and a store that cannot be read makes a scan UNCHECKED (exit
3) in either form, never a shorter list that reads as complete."""
import json
import os

from tests.helpers import WAITS, Case
from tests.test_db import OnDb
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
WAITING = "waiting-jacob"


def text_ids(out):
    """The ids the text form lists (its rows; not a notice)."""
    return [ln.split()[0] for ln in out.splitlines() if ln and not ln.startswith((" ", "(", "UNREADABLE"))]


class ListJson(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")
        self.todo("-C", self.a, "add", "here ü", "--kind", NOTE, "--evidence", "ran x, saw y")
        self.todo("-C", self.a, "add", "asks him", "--kind", NOTE, "--status", WAITING, "--waits-on", WAITS)
        self.todo("-C", self.b, "add", "there", "--kind", NOTE)

    def doc(self, *extra, d=None, ok=True):
        return json.loads(self.todo("-C", d or self.a, "--root", self.ws, "list", "--json", *extra, ok=ok).stdout)

    def test_the_flag_changes_the_output_and_not_the_answer(self):
        text = self.todo("-C", self.a, "list").stdout
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)  # without --json: lines, not a document
        d = self.doc()
        self.assertEqual(sorted(d), ["count", "items", "root", "unreadable"])
        self.assertEqual([r["local_id"] for r in d["items"]], text_ids(text))
        self.assertEqual([r["id"] for r in d["items"]], ["todo:aa-1", "todo:aa-2"])
        self.assertEqual((d["count"], d["unreadable"], d["root"]), (2, [], str(self.ws.resolve())))

    def test_each_record_is_the_stored_item_whole(self):
        """What ask.py and the wizard read out of todo.json today, field for field."""
        d = self.doc()
        self.assertEqual([r["record"] for r in d["items"]], self.store(self.a)["items"])
        self.assertEqual({r["store"] for r in d["items"]}, {str(self.a.resolve())})

    def test_the_filters_narrow_the_document(self):
        self.assertEqual([r["id"] for r in self.doc("--status", WAITING)["items"]], ["todo:aa-2"])
        self.assertEqual(sorted(r["id"] for r in self.doc("--all")["items"]), ["todo:aa-1", "todo:aa-2", "todo:bb-1"])
        self.assertEqual([r["id"] for r in self.doc(d=self.b)["items"]], ["todo:bb-1"])

    def test_nothing_matching_is_an_empty_list_and_exit_0(self):
        d = self.doc("--status", WAITING, d=self.b)
        self.assertEqual((d["items"], d["count"]), ([], 0))

    def test_an_unreadable_store_is_unchecked_in_either_form(self):
        path = self.b / "todo.json"
        os.chmod(path, 0o644)
        path.write_text("{")
        r = self.todo("-C", self.a, "--root", self.ws, "list", "--all", "--json", ok=None)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("UNCHECKED", r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual([x["id"] for x in d["items"]], ["todo:aa-1", "todo:aa-2"])
        self.assertEqual(len(d["unreadable"]), 1)
        t = self.todo("-C", self.a, "--root", self.ws, "list", "--all", ok=None)
        self.assertEqual(t.returncode, 3, t.stdout + t.stderr)
        self.assertIn("UNREADABLE", t.stdout)
        # this store alone: the broken one is not in scope, so nothing is unchecked
        self.assertEqual(self.doc()["unreadable"], [])


class ListJsonOnDb(OnDb):
    def test_the_document_is_the_same_before_and_after_the_move(self):
        """The seam the readers rely on: moving to todo.db changes no record they read."""
        d = self.a_store()
        before = json.loads(self.todo("-C", d, "list", "--json").stdout)
        self.assertEqual(before["count"], 1)
        self.todo("-C", d, "migrate")
        self.assertFalse((d / "todo.json").exists())
        after = json.loads(self.todo("-C", d, "list", "--json").stdout)
        self.assertEqual(after, before)
