"""`todo repos --status` (PLAN-architecture.md step 5; README): every git repo the scan
finds, with a store or not, its open items, last commit and uncommitted files.
Each field is proved to change with what it reports, not only to be present."""
import json

from tests.helpers import Case, git, git_commit, git_repo
from todolib import repostatus
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")


class Status(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        git_commit(self.a, "first in a")
        self.bare = self.ws / "nostore"
        git_repo(self.bare)

    def status(self, *extra, ok=True):
        return self.todo("-C", self.a, "--root", self.ws, "repos", "--status", *extra, ok=ok)

    def rows(self):
        return {r["name"]: r for r in json.loads(self.status("--json").stdout)["repos"]}

    def test_every_git_repo_is_listed_with_a_store_or_not_sorted_by_path(self):
        out = json.loads(self.status("--json").stdout)
        self.assertEqual([r["path"] for r in out["repos"]], ["a", "nostore"])
        rows = self.rows()
        self.assertEqual((rows["a"]["has_store"], rows["a"]["open_items"]), (True, 0))
        self.assertEqual((rows["nostore"]["has_store"], rows["nostore"]["open_items"]), (False, None))
        self.assertIsNone(rows["a"]["whose"], "todo reads no stamp ledger: whose is never guessed")

    def test_open_counts_the_store_items(self):
        self.todo("-C", self.a, "add", "one", "--kind", NOTE)
        self.todo("-C", self.a, "add", "two", "--kind", NOTE)
        self.assertEqual(self.rows()["a"]["open_items"], 2)

    def test_last_commit_follows_the_repo(self):
        self.assertIsNone(self.rows()["nostore"]["last_commit"], "no commit yet: null, not a guess")
        c = self.rows()["a"]["last_commit"]
        self.assertEqual(c["subject"], "first in a")
        self.assertEqual(c["sha"], git(self.a, "rev-parse", "--short", "HEAD").strip())
        (self.a / "x.txt").write_text("x")
        git_commit(self.a, "second in a")
        self.assertEqual(self.rows()["a"]["last_commit"]["subject"], "second in a")

    def test_dirty_counts_uncommitted_files_and_caps_the_list(self):
        self.assertEqual(self.rows()["a"]["dirty"], {"count": 0, "files": []})
        for n in range(repostatus.DIRTY_LISTED + 2):
            (self.a / f"f{n:02}.txt").write_text("x")
        d = self.rows()["a"]["dirty"]
        self.assertEqual(d["count"], repostatus.DIRTY_LISTED + 2)
        self.assertEqual(len(d["files"]), repostatus.DIRTY_LISTED)
        self.assertIn("f00.txt", d["files"])

    def test_text_names_each_repo(self):
        (self.a / "y.txt").write_text("y")
        out = self.status().stdout
        self.assertIn("1 uncommitted", out)
        self.assertIn("no store", out)
        self.assertIn("first in a", out)

    def test_json_goes_with_status(self):
        r = self.todo("-C", self.a, "--root", self.ws, "repos", "--json", ok=False)
        self.assertIn("--status", r.stderr)

    def test_an_unreadable_store_is_said_not_counted(self):
        (self.bare / "todo.json").write_text("{not json")
        r = self.rows()["nostore"]
        self.assertEqual((r["has_store"], r["open_items"]), (True, None))
        self.assertIn("does not parse", r["unreadable"])
