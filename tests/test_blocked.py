"""blocked_by (PLAN-todo-tool.md §9 step 3): `ready` leaves a blocked item out
until every id it names is in history, `list --ready` and `--blocked` split the
open items in two, `brief` says NOT READY, and add, edit and check refuse an id
that resolves nowhere or a cycle."""
from tests.helpers import Case
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
READY = ["--work", "code", "--done-when", "it works", "--size", VOCAB.ready_sizes[0]]


def ids(out):
    return [ln.split()[0] for ln in out.splitlines() if ln[:1].isalpha() and "-" in ln.split()[0]]


class Blocked(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "first", "--kind", NOTE, *READY)
        self.todo("-C", self.a, "add", "second", "--kind", NOTE, *READY, "--blocked-by", "aa-1")

    def test_ready_leaves_a_blocked_item_out_until_its_blocker_closes(self):
        self.assertEqual(ids(self.todo("-C", self.a, "ready").stdout), ["aa-1"])
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "did it")
        self.assertEqual(ids(self.todo("-C", self.a, "ready").stdout), ["aa-2"])

    def test_list_ready_and_blocked_split_the_open_items(self):
        self.todo("-C", self.a, "add", "third", "--kind", NOTE)
        self.assertEqual(ids(self.todo("-C", self.a, "list", "--ready").stdout), ["aa-1", "aa-3"])
        self.assertEqual(ids(self.todo("-C", self.a, "list", "--blocked").stdout), ["aa-2"])
        self.assertEqual(ids(self.todo("-C", self.a, "list").stdout), ["aa-1", "aa-2", "aa-3"])
        self.todo("-C", self.a, "list", "--ready", "--blocked", ok=False)

    def test_brief_of_a_blocked_item_is_not_ready(self):
        out = self.todo("-C", self.a, "brief", "aa-2", ok=False).stdout
        self.assertIn("NOT READY: blocked by aa-1", out)
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "did it")
        out = self.todo("-C", self.a, "brief", "aa-2").stdout
        self.assertIn("Blocked by: aa-1 (all closed)", out)

    def test_a_blocker_in_another_repo_counts(self):
        b = self.repo("b", "bb")
        self.todo("-C", b, "add", "theirs", "--kind", NOTE)
        self.todo("-C", self.a, "edit", "aa-1", "--blocked-by", "bb-1")
        self.assertEqual(ids(self.todo("-C", self.a, "ready").stdout), [])
        self.todo("-C", b, "done", "bb-1", "--resolution", "done there")
        self.assertEqual(ids(self.todo("-C", self.a, "ready").stdout), ["aa-1"])

    def test_add_and_edit_refuse_an_unknown_id_and_a_cycle(self):
        r = self.todo("-C", self.a, "add", "x", "--kind", NOTE, "--blocked-by", "aa-99", ok=False)
        self.assertIn("aa-99 resolves in no scanned store", r.stderr)
        r = self.todo("-C", self.a, "edit", "aa-1", "--blocked-by", "aa-2", ok=False)
        self.assertIn("cycle: aa-1 -> aa-2 -> aa-1", r.stderr)
        r = self.todo("-C", self.a, "edit", "aa-1", "--blocked-by", "aa-1", ok=False)
        self.assertIn("cycle: aa-1 -> aa-1", r.stderr)
        self.assertEqual([it["blocked_by"] for it in self.store(self.a)["items"]], [None, ["aa-1"]])
        self.todo("-C", self.a, "edit", "aa-2", "--blocked-by")
        self.assertIsNone(self.store(self.a)["items"][1]["blocked_by"])

    def test_check_fails_on_an_unknown_id_and_on_a_cycle(self):
        self.check(self.a)
        data = self.store(self.a)
        data["items"][1]["blocked_by"] = ["aa-77"]
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "blockers", "blocked_by aa-77 is in neither")
        data["items"][1]["blocked_by"] = ["aa-1"]
        data["items"][0]["blocked_by"] = ["aa-2"]
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "blockers", "blocked_by cycle: aa-1 -> aa-2 -> aa-1")
        data["items"][0]["blocked_by"] = []
        data["items"][1]["blocked_by"] = "aa-1"
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "schema", "blocked_by must be a non-empty list")

    def test_an_item_from_before_the_field_passes_and_an_unknown_key_still_fails(self):
        data = self.store(self.a)
        del data["items"][0]["blocked_by"]
        self.write_json(self.a / "todo.json", data)
        out = self.check(self.a).stdout
        self.assertIn("ok    schema", out)
        data["items"][0]["blocked_by_typo"] = None
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "schema", "extra ['blocked_by_typo']")
        del data["items"][0]["blocked_by_typo"]
        del data["items"][0]["parent"]
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "schema", "missing ['parent']")
