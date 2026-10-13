"""A missing id and a repo with no store exit with different codes (README
"Exit codes"): 1 for the id, 4 for the store, so a caller tells "ask elsewhere"
from "set this repo up first" without reading stderr. The README's table is the
contract; this holds the CLI to it, case by case."""
import re

from tests.helpers import ROOT, Case, git_repo
from todolib.store import EXIT_NO_STORE
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
ROW = re.compile(r"^\| (\d) \| (.+) \|$")


def documented():
    text = (ROOT / "README.md").read_text()
    section = text.split("### Exit codes", 1)[1].split("\n## ", 1)[0]
    return {int(m.group(1)): m.group(2) for m in map(ROW.match, section.splitlines()) if m}


class ExitCodes(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "one", "--kind", NOTE)
        self.bare = self.ws / "bare"
        git_repo(self.bare)

    def code(self, *args, cwd=None):
        return self.todo(*args, cwd=cwd, ok=None).returncode

    def test_a_missing_id_and_a_storeless_repo_differ(self):
        missing = self.code("-C", self.a, "show", "aa-99")
        storeless = self.code("-C", self.bare, "show", "aa-1")
        self.assertEqual((missing, storeless), (1, EXIT_NO_STORE))
        self.assertNotEqual(missing, storeless)

    def test_every_way_to_meet_no_store_gives_its_code(self):
        self.assertEqual(self.code("list", cwd=self.bare), EXIT_NO_STORE, "a command that needs the repo's store")
        self.assertEqual(self.code("add", "x", "--kind", NOTE, cwd=self.bare), EXIT_NO_STORE, "a write")
        empty = self.tmp / "nowhere"
        empty.mkdir()
        self.assertEqual(self.code("show", "aa-1", cwd=empty), EXIT_NO_STORE, "a read by id that scans no store")

    def test_counterfactual_with_a_store_the_same_reads_answer(self):
        self.todo("-C", self.bare, "init", "--prefix", "bb")
        self.assertEqual(self.code("list", cwd=self.bare), 0)
        self.assertEqual(self.code("-C", self.bare, "show", "aa-1"), 0)

    def test_the_readme_table_is_the_codes_the_cli_gives(self):
        table = documented()
        self.assertEqual(sorted(table), [0, 1, 2, 3, EXIT_NO_STORE], table)
        self.assertIn("missing", table[1])
        self.assertIn("no store", table[EXIT_NO_STORE])
        self.assertEqual(self.code("get", "zz-1", cwd=self.a), 3, "UNCHECKED, as documented")
        self.assertEqual(self.code("show", cwd=self.a), 2, "a missing argument, as documented")
