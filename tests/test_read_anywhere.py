"""Reads by id or tag need no store of their own: from a folder with none (the
workspace root, or a repo not migrated yet), show, get, find, refs, brief,
tree ID and history ID answer from the stores scanned from there. A write still
needs its store, and -C naming a folder without one stays an error."""
import json

from tests.helpers import Case, git_repo
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")


class ReadAnywhere(Case):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", self.a, "add", "theirs first", "--kind", NOTE)
        self.todo("-C", self.b, "add", "points at aa-1", "--kind", NOTE, "--parent", "aa-1", "--tags", "origin:tool")
        self.todo("-C", self.a, "add", "closes", "--kind", NOTE)
        self.todo("-C", self.a, "done", "aa-2", "--resolution", "fixed")

    def test_the_workspace_root_answers_every_read_by_id_or_tag(self):
        root = self.ws
        self.assertIn("points at aa-1", self.todo("show", "bb-1", cwd=root).stdout)
        self.assertEqual(json.loads(self.todo("get", "todo:aa-1", cwd=root).stdout)["id"], "todo:aa-1")
        self.assertIn("todo:bb-1", self.todo("find", "origin:tool", cwd=root).stdout)
        self.assertIn("todo:bb-1", self.todo("refs", "aa-1", cwd=root).stdout)
        self.assertIn("What: points at aa-1", self.todo("brief", "bb-1", cwd=root, ok=None).stdout)
        self.assertIn("points at aa-1", self.todo("tree", "aa-1", cwd=root).stdout)
        self.assertIn("fixed", self.todo("history", "aa-2", cwd=root).stdout)

    def test_a_repo_without_a_store_reads_the_workspace_around_it(self):
        bare = self.ws / "unmigrated"
        git_repo(bare)
        self.assertIn("theirs first", self.todo("show", "aa-1", cwd=bare).stdout)

    def test_writes_and_an_explicit_folder_still_need_a_store(self):
        root = self.ws
        self.assertIn("no todo.json", self.todo("add", "x", "--kind", NOTE, cwd=root, ok=False).stderr)
        self.assertIn("no todo.json", self.todo("-C", root, "show", "aa-1", ok=False).stderr)

    def test_nothing_to_scan_is_an_error_not_an_empty_answer(self):
        empty = self.tmp / "elsewhere"
        empty.mkdir()
        err = self.todo("show", "aa-1", cwd=empty, ok=False).stderr
        self.assertIn("no todo.json", err)
        self.assertIn("and none under", err)
