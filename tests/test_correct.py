"""`todo correct` and the home-path refusal (PLAN-todo-tool.md §2a): the one change
made to a history entry after its close, logged with the replaced text's SHA-256 and
never the text, admitted by the history audit because the log holds that row; and
`todo done --resolution` refusing a home-folder path before it writes anything."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from tests.helpers import Case, git_commit, workspace_file
from tests.test_db import OnDb
from todolib.store import CORRECTION_KEY, WRITES_FILE, resolution_sha
from todolib.vocab import VOCAB

# Assembled from parts so this file holds no home-folder path itself: the shape is
# what the refusal is about, and a public repo carries none. "someone" is generic.
HOME = "/" + "Users" + "/someone"
OLD = "fixed, the log is in " + HOME + "/notes/run.txt"
NEW = "fixed, the log is in tools/todo/notes/run.txt"


def store_bytes(d):
    """Every store file's bytes: what a refused command must leave as it was."""
    return {p.name: p.read_bytes() for p in sorted(Path(d).iterdir()) if p.is_file()}


class Correct(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        for t in ("one", "two", "three"):
            self.todo("-C", self.a, "add", t, "--kind", "note", "--evidence", f"ran {t}")
        # the leaked text reached history before the refusal existed: planted as todo done wrote it
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "placeholder")
        h = self.history(self.a)
        h["items"][0]["resolution"] = OLD
        self.write_json(self.a / "todo-history.json", h)
        self.todo("-C", self.a, "done", "aa-2", "--resolution", "kept as it is")

    def correct(self, iid="aa-1", resolution=NEW, reason="drop a home-folder path", ok=True):
        return self.todo("-C", self.a, "correct", iid, "--resolution", resolution, "--reason", reason, ok=ok, today="2026-10-05")

    def test_only_the_resolution_changes_and_the_entry_keeps_its_place(self):
        before = self.history(self.a)["items"]
        self.correct()
        after = self.history(self.a)["items"]
        self.assertEqual([it["id"] for it in after], [it["id"] for it in before])
        self.assertEqual(after[1], before[1])
        for field in sorted(set(before[0]) | set(after[0])):
            if field == "resolution":
                self.assertEqual((before[0][field], after[0][field]), (OLD, NEW))
            else:
                self.assertEqual(after[0].get(field), before[0].get(field), f"{field} changed")

    def test_the_log_holds_the_hash_and_the_reason_never_the_old_text(self):
        self.correct(reason="drop a home-folder path")
        log = (self.a / WRITES_FILE).read_text()
        self.assertNotIn(OLD, log)
        self.assertNotIn(HOME, log)
        row = json.loads(log.splitlines()[-1])
        self.assertEqual(row["verb"], "correct")
        self.assertEqual(row[CORRECTION_KEY], {"id": "aa-1", "sha256": resolution_sha(OLD), "reason": "drop a home-folder path"})
        self.assertIn("aa-1", row["ids"])
        earlier = [json.loads(ln) for ln in log.splitlines()[:-1]]
        self.assertTrue(earlier and all(CORRECTION_KEY not in r for r in earlier), "only a correct row carries the key")

    def test_history_id_shows_when_and_why(self):
        self.assertNotIn("corrected", self.todo("-C", self.a, "history", "aa-1").stdout)
        self.correct(reason="drop a home-folder path")
        shown = self.todo("-C", self.a, "history", "aa-1").stdout
        line = next((ln for ln in shown.splitlines() if ln.startswith("corrected ")), None)
        self.assertIsNotNone(line, shown)
        self.assertIn("drop a home-folder path", line)
        self.assertIn(resolution_sha(OLD)[:16], line)
        self.assertRegex(line, r"^corrected \d{4}-\d{2}-\d{2}T")
        self.assertNotIn("corrected ", self.todo("-C", self.a, "history", "aa-2").stdout)

    def test_refused_on_an_open_id_and_on_one_that_does_not_exist(self):
        before = store_bytes(self.a)
        r = self.correct("aa-3", ok=False)
        self.assertIn("aa-3 is open", r.stderr)
        r = self.correct("aa-9", ok=False)
        self.assertIn("aa-9 is not in todo-history.json", r.stderr)
        self.assertEqual(store_bytes(self.a), before)

    def test_other_refusals_write_nothing(self):
        before = store_bytes(self.a)
        for resolution, reason, says in (
                (NEW, "", "--reason is one line"),
                (NEW, "two\nlines", "--reason is one line"),
                (NEW, "see " + HOME + "/x", "--reason holds a home-folder path"),
                (HOME + "/x", "why", "--resolution holds a home-folder path"),
                ("", "why", "--resolution is one line"),
                (OLD, "why", "--resolution holds a home-folder path"),
                (VOCAB.role("import_resolution"), "why", "set by todo import only"),
                (VOCAB.role("detector_resolution"), "why", "set by todo detect only")):
            r = self.correct(resolution=resolution, reason=reason, ok=False)
            self.assertIn(says, r.stderr, (resolution, reason))
        r = self.todo("-C", self.a, "correct", "aa-2", "--resolution", "kept as it is", "--reason", "why", ok=False)
        self.assertIn("nothing written", r.stderr)
        self.assertEqual(store_bytes(self.a), before)

    def test_the_store_still_checks_clean_after_a_correction(self):
        self.correct()
        out = self.check(self.a).stdout
        self.assertNotIn("FAIL", out)


class HistoryAudit(Case):
    """The append-only audit admits a corrected entry because the log holds its row,
    and nothing else: an unlogged edit, or a row whose hash is of another text, stays red."""

    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        for t in ("one", "two"):
            self.todo("-C", self.a, "add", t, "--kind", "note")
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "first words")
        self.todo("-C", self.a, "done", "aa-2", "--resolution", "ok")
        git_commit(self.a, "closed both")

    def history_fails(self, out):
        return [ln for ln in out.splitlines() if ln.split()[:2] == ["FAIL", "history"]]

    def test_a_corrected_entry_passes_uncommitted_and_committed(self):
        self.todo("-C", self.a, "correct", "aa-1", "--resolution", "better words", "--reason", "say what was done")
        out = self.check(self.a).stdout
        self.assertEqual(self.history_fails(out), [])
        self.assertIn("carry a resolution replaced by `todo correct`", out)
        git_commit(self.a, "corrected aa-1")
        self.todo("-C", self.a, "correct", "aa-1", "--resolution", "best words", "--reason", "once more")
        git_commit(self.a, "corrected aa-1 again")
        out = self.check(self.a).stdout
        self.assertEqual(self.history_fails(out), [], out)
        self.assertIn("1 history entr(ies) carry a resolution replaced", out)

    def hand_edit(self, logged_text):
        """aa-1's resolution changed around the CLI, and a correct row appended by hand
        whose hash is of `logged_text`: the audit decides from the hash alone."""
        h = self.history(self.a)
        h["items"][0]["resolution"] = "rewritten"
        self.write_json(self.a / "todo-history.json", h)
        log = self.a / WRITES_FILE
        rows = log.read_text().splitlines()
        row = dict(json.loads(rows[-1]), verb="correct", ids=["aa-1"])
        row[CORRECTION_KEY] = {"id": "aa-1", "sha256": resolution_sha(logged_text), "reason": "by hand"}
        os.chmod(log, 0o644)
        log.write_text("\n".join(rows + [json.dumps(row)]) + "\n")
        os.chmod(log, 0o444)

    def test_a_row_hashing_the_committed_text_is_admitted(self):
        self.hand_edit("first words")
        self.assertEqual(self.history_fails(self.check(self.a).stdout), [])

    def test_a_row_hashing_another_text_is_still_red(self):
        self.hand_edit("words never committed")
        self.assertFails(self.a, "history", "aa-1     changed since")

    def test_an_unlogged_change_is_still_red(self):
        h = self.history(self.a)
        h["items"][0]["resolution"] = "rewritten"
        self.write_json(self.a / "todo-history.json", h)
        self.assertFails(self.a, "history", "aa-1     changed since")

    def test_a_logged_correction_admits_the_resolution_and_nothing_more(self):
        self.hand_edit("first words")
        h = self.history(self.a)
        h["items"][0]["title"] = "renamed by hand"
        self.write_json(self.a / "todo-history.json", h)
        self.assertFails(self.a, "history", "aa-1     changed since")


class WritesGate(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "one", "--kind", "note")
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "first words")
        self.todo("-C", self.a, "correct", "aa-1", "--resolution", "better words", "--reason", "why")

    def replace_correction(self, value):
        log = self.a / WRITES_FILE
        rows = log.read_text().splitlines()
        last = json.loads(rows[-1])
        last[CORRECTION_KEY] = value
        os.chmod(log, 0o644)
        log.write_text("\n".join(rows[:-1] + [json.dumps(last)]) + "\n")
        os.chmod(log, 0o444)

    def test_the_row_todo_correct_writes_passes(self):
        self.assertIn("ok    writes", self.check(self.a).stdout)

    def test_a_correction_of_another_shape_fails(self):
        good = {"id": "aa-1", "sha256": resolution_sha("first words"), "reason": "why"}
        for bad in (dict(good, sha256="abc"), dict(good, reason="two\nlines"), dict(good, id="aa-7"),
                    {"id": "aa-1", "sha256": good["sha256"]}, dict(good, text="first words"), None):
            self.replace_correction(bad)
            self.assertFails(self.a, "writes", f"{CORRECTION_KEY} must be", today="2026-10-04")
        self.replace_correction(good)
        self.assertIn("ok    writes", self.check(self.a).stdout)


class DoneRefusesAHomePath(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "one", "--kind", "note")

    def test_a_home_path_is_refused_and_nothing_written(self):
        before = store_bytes(self.a)
        for text in (HOME + "/x.txt", "see " + HOME, "the run at /" + "home/someone/log"):
            r = self.todo("-C", self.a, "done", "aa-1", "--resolution", text, ok=False)
            self.assertEqual(r.returncode, 1)
            self.assertIn("--resolution holds a home-folder path", r.stderr)
            self.assertIn(VOCAB.home_path_source, r.stderr)
            self.assertIn(VOCAB.home_path.search(text).group(0), r.stderr)
            self.assertEqual(store_bytes(self.a), before)

    def test_a_path_inside_the_repo_closes(self):
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "fixed in tools/todo/todolib/cli.py and ~/notes")
        self.assertEqual(self.history(self.a)["items"][0]["resolution"], "fixed in tools/todo/todolib/cli.py and ~/notes")


class OnTodoDb(OnDb):
    def test_refused_on_todo_db_and_nothing_written(self):
        d = self.moved()
        before = self.snapshot()
        r = self.todo("-C", d, "correct", "aa-1", "--resolution", "better", "--reason", "why", ok=False)
        self.assertIn("todo.db", r.stderr)
        self.assertEqual(self.snapshot(), before)


class AgreesWithTheHub(Case):
    """The pattern has one source in this repo (vocab.json leaks.home_path) and a second
    copy in tools/hub's leak audit: the two must agree by meaning, line by line, or
    `todo done` would let through a path the hub then fails on (or refuse one it passes)."""
    LINES = [HOME + "/x", "/" + "home/someone/y", "~/notes", "/Users/...", "/Users/<x>", "tools/todo/cli.py",
             "a.b" + HOME + "/z", "/" + "Users/_x", "/" + "Users/", "x" + "/" + "home/y"]

    def test_each_line_is_refused_here_exactly_when_the_hub_fails_it(self):
        hub = workspace_file("tools/hub/devtools/hubcheck.py")
        if hub is None:
            self.skipTest("tools/hub is not above this repo (a fresh clone): nothing to agree with")
        root = hub.parent.parent
        with tempfile.TemporaryDirectory(prefix="todo-hub-") as tmp:
            for n, line in enumerate(self.LINES):
                f = Path(tmp) / f"line{n}.txt"
                f.write_text(line + "\n")
                r = subprocess.run(["python3", str(hub), "leaks", str(f)], cwd=root, capture_output=True, text=True, timeout=120)
                self.assertIn(r.returncode, (0, 1), f"the hub's audit did not run on {line!r}: {r.stdout}{r.stderr}")
                hub_fails = r.returncode == 1 and "home-folder path" in r.stdout
                self.assertEqual(bool(VOCAB.home_path.search(line)), hub_fails, f"{line!r}: hub said {r.stdout.strip()!r}")
        self.assertTrue(any(VOCAB.home_path.search(ln) for ln in self.LINES))
        self.assertFalse(all(VOCAB.home_path.search(ln) for ln in self.LINES))
