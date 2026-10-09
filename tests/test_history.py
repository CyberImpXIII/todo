"""History (PLAN §2a): done moves an item whole, history is append-only against
its own git log, and history/show read it back."""
import json
import os

from tests.helpers import Case, git_commit
from todolib.render import field_value
from todolib.vocab import VOCAB


class RoundTrip(Case):
    def test_done_then_history_id_round_trips_every_field(self):
        a, b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", b, "add", "parent", "--kind", "note")
        self.todo("-C", a, "add", "every field", "--kind", "temp", "--status", "blocked",
                  "--evidence", "line one\n\n  indented line", "--probe", "p", "--parent", "bb-1", "--blocked-by", "bb-1", "--tags", "plan:PLAN-x.md", "--size", VOCAB.ready_sizes[0],
                  "--repo", "elsewhere", "--work", "test", "--files", "a.py", "b/c.js",
                  "--done-when", "suite passes", "--retire", "manifest:nodes", today="2026-10-01")
        self.todo("-C", a, "edit", "aa-1", "--handoff", "done: half; next: the rest", today="2026-10-02")
        before = self.store(a)["items"][0]
        self.todo("-C", a, "done", "aa-1", "--resolution", "retired by the check")
        self.assertEqual(self.store(a)["items"], [])
        after = self.history(a)["items"][0]
        self.assertEqual(after, dict(before, status=VOCAB.closed, done="2026-10-04", resolution="retired by the check"))
        unset = [f for f in VOCAB.field_names() if before.get(f) in (None, [], "")]
        self.assertEqual(sorted(unset), ["done", "imported", "reported_to", "resolution"])
        shown = self.todo("-C", a, "history", "aa-1").stdout
        for f in VOCAB.field_names():
            v = after[f]
            if v in (None, [], ""):
                continue
            text = ", ".join(v) if isinstance(v, list) else field_value(f, v) if f == "handoff" else str(v)
            for line in text.split("\n"):
                self.assertIn(line, shown, f"field {f} not shown")
        self.assertIn("closed, in todo-history.json", self.todo("-C", a, "show", "aa-1").stdout)

    def test_history_lists_newest_first_and_filters(self):
        a = self.repo("a", "aa")
        for i, kind in enumerate(["bug", "note", "bug"], 1):
            self.todo("-C", a, "add", f"item {i}", "--kind", kind)
        for i, day in ((1, "2026-10-01"), (2, "2026-10-03"), (3, "2026-10-02")):
            self.todo("-C", a, "done", f"aa-{i}", "--resolution", f"res {i}", today=day)
        ids = lambda out: [ln.split()[0] for ln in out.splitlines() if ln.startswith("aa-")]  # noqa: E731
        self.assertEqual(ids(self.todo("-C", a, "history").stdout), ["aa-2", "aa-3", "aa-1"])
        self.assertEqual(ids(self.todo("-C", a, "history", "--since", "2026-10-02").stdout), ["aa-2", "aa-3"])
        self.assertEqual(ids(self.todo("-C", a, "history", "--kind", "bug").stdout), ["aa-3", "aa-1"])
        self.assertEqual(ids(self.todo("-C", a, "history", "--grep", "RES 3").stdout), ["aa-3"])
        b = self.repo("b", "bb")
        self.assertEqual(ids(self.todo("-C", b, "history", "--repo", "a").stdout), ["aa-2", "aa-3", "aa-1"])
        self.assertIn("no closed items", self.todo("-C", b, "history").stdout)

    def test_history_without_arguments_shows_the_last_ten(self):
        a = self.repo("a", "aa")
        for i in range(1, 13):
            self.todo("-C", a, "add", f"item {i}", "--kind", "note")
            self.todo("-C", a, "done", f"aa-{i}", "--resolution", "ok")
        lines = [ln for ln in self.todo("-C", a, "history").stdout.splitlines() if ln.startswith("aa-")]
        self.assertEqual(len(lines), 10)
        self.assertEqual(lines[0].split()[0], "aa-12")

    def test_edit_of_a_closed_item_is_refused(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "x", "--kind", "note")
        self.todo("-C", a, "done", "aa-1", "--resolution", "ok")
        self.todo("-C", a, "edit", "aa-1", "--title", "y", ok=False)


class AppendOnly(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        for t in ("one", "two"):
            self.todo("-C", self.a, "add", t, "--kind", "note")
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "ok")
        git_commit(self.a, "first close")
        self.todo("-C", self.a, "done", "aa-2", "--resolution", "ok")
        git_commit(self.a, "second close")

    def rewrite(self, fn):
        h = self.history(self.a)
        fn(h["items"])
        self.write_json(self.a / "todo-history.json", h)

    def test_appending_is_green(self):
        self.assertIn("ok    history", self.check(self.a).stdout)

    def test_a_removed_entry_is_red_even_uncommitted(self):
        self.rewrite(lambda items: items.pop(0))
        self.assertFails(self.a, "history", "aa-1     was in todo-history.json at")

    def test_a_changed_entry_is_red(self):
        self.rewrite(lambda items: items[1].update(resolution="rewritten"))
        self.assertFails(self.a, "history", "aa-2     changed since")

    def test_a_removal_committed_later_is_still_red(self):
        self.rewrite(lambda items: items.pop(0))
        git_commit(self.a, "drop aa-1")
        self.assertFails(self.a, "history", "aa-1     was in todo-history.json at")

    def test_an_unparseable_history_is_refused_not_guessed(self):
        os.chmod(self.a / "todo-history.json", 0o644)
        (self.a / "todo-history.json").write_text("{not json")
        r = self.todo("-C", self.a, "check", ok=False)
        self.assertIn("does not parse", r.stderr)

    def test_a_missing_history_is_red(self):
        (self.a / "todo-history.json").unlink()
        self.assertFails(self.a, "history", "todo-history.json missing")
        r = self.todo("-C", self.a, "add", "x", "--kind", "note", ok=False)
        self.assertIn("todo-history.json is missing", r.stderr)
        self.assertFalse((self.a / "todo-history.json").exists(), "history is never recreated empty")
        self.assertEqual(len(json.loads((self.a / "todo.json").read_text())["items"]), 0)
