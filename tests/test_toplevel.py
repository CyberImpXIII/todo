"""A store in a folder that is no git repo: the workspace top level
(PLAN-todo-tool.md §9 step 1). Its owner runs `todo init --prefix tl` and
`todo import TODO.md --dry-run` there with no -C, so that is what runs here:
cwd is a workspace folder holding a CLAUDE.md beside a git repo with a store,
like the real top level."""
import subprocess

from tests.helpers import FIXTURES, Case


class TopLevel(Case):
    def test_init_and_a_dry_run_import_work_where_there_is_no_git_repo(self):
        sibling = self.repo("a", "aa")
        self.todo("-C", sibling, "add", "an item in a repo", "--kind", "note")
        # The precondition this test is about: the folder is in no git repo. Asserted,
        # so a temp folder that happened to sit inside one could not pass it vacuously.
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=self.ws, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, f"{self.ws} is inside a git repo: {r.stdout}")
        source = (FIXTURES / "done.TODO.md").read_text()
        (self.ws / "TODO.md").write_text(source)

        out = self.todo("init", "--prefix", "tl", cwd=self.ws).stdout
        self.assertIn("todo import TODO.md", out)
        self.assertEqual(self.store(self.ws)["repo"], "ws")
        self.assertEqual((self.ws / "TODO.md").read_text(), source, "init must not touch a hand-written TODO.md")

        before = {f: (self.ws / f).read_text() for f in ("todo.json", "todo-history.json", "TODO.md")}
        out = self.todo("import", "TODO.md", "--dry-run", cwd=self.ws).stdout
        after = {f: (self.ws / f).read_text() for f in before}
        self.assertEqual(after, before, "a dry run wrote something")
        head = out.splitlines()[0]
        n_open = int(head.split(": ", 1)[1].split(" new open")[0])
        n_closed = int(head.split(", ")[1].split(" new closed")[0])
        self.assertEqual(sum(ln.startswith("  store ") for ln in out.splitlines()), n_open)
        self.assertEqual(sum(ln.startswith("  history ") for ln in out.splitlines()), n_closed)
        self.assertGreater(n_closed, 0, "the fixture's DONE bullets must go to history")
        self.assertGreater(n_open, 0)

        # The dry run's counts are what the import then does.
        self.todo("import", "TODO.md", cwd=self.ws)
        self.assertEqual(len(self.store(self.ws)["items"]), n_open)
        self.assertEqual(len(self.history(self.ws)["items"]), n_closed)

        # The top-level store and the repo's see each other through the scan.
        top = self.todo("repos", cwd=self.ws).stdout
        self.assertIn(f"scan root: {self.ws.resolve()}", top)
        self.assertRegex(top, r"\n  a\s+aa\s")
        self.assertRegex(self.todo("-C", sibling, "repos").stdout, r"\n  ws\s+tl\s")
        out = self.check(self.ws, ok=None).stdout
        self.assertIn("not a git repo: the append-only audit against the git log is skipped here", out)
