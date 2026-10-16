"""--repo names a repo some scanned store knows (cli.known_repo): a misspelt repo is
an error naming the known ones, never "0 items" with exit 0. Known: a readable
store's own repo, or a repo an open or closed item names. With a store unreadable,
an unknown repo is UNCHECKED (exit 3): that store may hold it."""
import os

from tests.helpers import Case

COMMANDS = ("list", "ready", "dispatchable", "blockers", "stale-plans")


class RepoFilter(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.b = self.repo("b", "bb")

    def test_an_unknown_repo_is_refused_naming_the_known_ones(self):
        for cmd in COMMANDS:
            with self.subTest(cmd):
                r = self.todo("-C", self.a, cmd, "--repo", "no-such-repo", ok=None)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("'no-such-repo'", r.stderr)
                self.assertIn("known: a, b", r.stderr)

    def test_a_known_repo_still_reads(self):
        for cmd in COMMANDS:
            with self.subTest(cmd):
                self.todo("-C", self.a, cmd, "--repo", "b")

    def test_a_repo_named_only_by_an_item_is_known(self):
        self.todo("-C", self.a, "add", "elsewhere", "--kind", "note", "--repo", "far")
        r = self.todo("-C", self.a, "list", "--repo", "far")
        self.assertIn("elsewhere", r.stdout)

    def test_a_repo_named_only_by_a_closed_item_is_known(self):
        self.todo("-C", self.a, "add", "gone", "--kind", "note", "--repo", "past")
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "r")
        self.todo("-C", self.a, "list", "--repo", "past")

    def test_with_a_store_unreadable_an_unknown_repo_is_unchecked(self):
        path = self.b / "todo.json"
        os.chmod(path, 0o644)
        path.write_text("{")
        r = self.todo("-C", self.a, "blockers", "--repo", "no-such-repo", ok=None)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("could not be read", r.stderr)
