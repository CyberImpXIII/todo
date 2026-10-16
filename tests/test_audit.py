"""The direction audit finds what it is for, and skips only what it says it skips."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

sys.path.insert(0, str(ROOT / "devtools"))
import audit  # noqa: E402


class Direction(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="todo-audit-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_this_repo_is_clean(self):
        hits, scanned = audit.audit(ROOT)
        self.assertEqual(hits, [])
        self.assertGreater(scanned, 10)

    def test_each_kind_of_violation_is_found(self):
        cases = {
            "a.py": "open('../../.claude/agents.manifest.json')",
            "b.md": "ask the Dispatcher to run it",
            "c.sh": "./.claude/agents.sh list",
            "d.py": "x = 'deep-work'",
            "e.json": "{\"owner\": \"harness\"}",
        }
        for rel, text in cases.items():
            self.write(rel, text)
        hits, _ = audit.audit(self.root)
        self.assertEqual(sorted({h.split()[2].split(":")[0] for h in hits}), sorted(cases))

    def test_checks_json_excludes_only_what_this_audit_skips(self):
        """checks.json (read by tools/checks' no-roster) and audit.json's skip list both
        exempt the files holding the audit's terms and planted violations. An exclusion
        there that this audit does not also skip would hide a file from both; one naming
        a missing file would be a guard that guards nothing."""
        cfg = json.loads((ROOT / "checks.json").read_text())
        self.assertEqual(sorted(cfg), ["accessor", "no-roster"], "checks.json holds only what this repo needs")
        excluded = cfg["no-roster"]["exclude"]
        skip = json.loads((ROOT / "devtools" / "audit.json").read_text())["skip"]
        self.assertTrue(excluded)
        for rel in excluded:
            self.assertIn(rel, skip, f"{rel} is excluded from no-roster but not skipped by devtools/audit.py")
            self.assertTrue((ROOT / rel).is_file(), f"{rel} is excluded but does not exist")

    def test_accessor_exempts_only_the_store_code_and_the_planted_hand_edit(self):
        """accessor (tools/checks) fails a file naming the store files outside `impl`.
        `impl` is the package that holds the one writer (todolib/store.py) and must
        match it. Two exclusions, each because the file must name a store file as data:
        devtools/mutants.json, whose self-gate-quiet mutant plants a hand edit in
        todo.json on purpose, and devtools/audit.json, whose `accepted` entries name the
        append-only history file's line they exempt. Anything wider would let a second
        writer through unseen."""
        cfg = json.loads((ROOT / "checks.json").read_text())["accessor"]
        self.assertEqual(cfg["impl"], ["todolib/*.py"])
        self.assertIn(ROOT / "todolib" / "store.py", list(ROOT.glob(cfg["impl"][0])))
        self.assertEqual(cfg["exclude"], ["devtools/mutants.json", "devtools/audit.json"])
        mutants = json.loads((ROOT / "devtools" / "mutants.json").read_text())["mutants"]
        self.assertIn("todo.json", [m.get("file") for m in mutants])
        accepted = json.loads((ROOT / "devtools" / "audit.json").read_text()).get("accepted", [])
        self.assertIn("todo-history.json", [a["file"] for a in accepted],
                      "audit.json is excluded from accessor for an accepted history line it no longer holds")

    def test_installed_shared_copies_are_skipped_and_nothing_else_is(self):
        """td-16 (Jacob, 2026-10-05): the copies setup's hooks component installs in
        .claude/hooks/ and .claude/lib/ are the renderer's files, gated by
        `hooks copies`, not this repo's code. The same term in todolib/, or in a
        .claude/ folder that is not one of those two, is still a violation."""
        term = "# hooks: applies_to=all dest=.claude/lib\n"
        self.write(".claude/lib/write-targets.sh", term)
        self.write(".claude/hooks/x.sh", term)
        self.assertEqual(audit.audit(self.root)[0], [])
        self.write("todolib/x.py", term)
        self.write(".claude/agents/x.md", term)
        found = sorted(h.split()[2].rsplit(":", 2)[0] for h in audit.audit(self.root)[0])
        self.assertEqual(found, [".claude/agents/x.md", "todolib/x.py"])

    def test_the_runners_logs_are_skipped_only_because_git_never_holds_them(self):
        """.progress/ holds the parts runner's logs, which quote other tools' output; it
        is skipped only because .gitignore keeps it out of every commit. A term in it
        passes; the same term in a sibling folder still fails."""
        ignored = (ROOT / ".gitignore").read_text().split()
        self.assertIn(".progress/", ignored, ".progress/ is skipped by the audit but not gitignored")
        term = "FAIL  .claude/lib/ledger.sh: drift\n"
        self.write(".progress/check.json.logs/checks.log", term)
        self.assertEqual(audit.audit(self.root)[0], [])
        self.write("progress/checks.log", term)
        self.assertEqual(len(audit.audit(self.root)[0]), 1)

    def test_an_accepted_line_is_exempt_alone_and_never_outlives_its_line(self):
        """`accepted` in audit.json: one exact line of one file (an append-only history
        entry that cannot be edited). The same term on another line of that file, or the
        same line in another file, still fails; an entry whose line is gone, or whose line
        hits no term, fails as a stale exemption."""
        accepted = json.loads((ROOT / "devtools" / "audit.json").read_text())["accepted"]
        self.assertTrue(accepted)
        for a in accepted:
            with self.subTest(a["file"]):
                self.assertTrue(a["why"])
                line = a["line"]
                self.write(a["file"], f"  {line}\n")
                self.assertEqual(audit.audit(self.root)[0], [])
                self.write(a["file"], f"  {line}\n  open('.claude/agents/x')\n")
                self.assertEqual(len(audit.audit(self.root)[0]), 1)
                self.write("other.json", f"  {line}\n")
                self.write(a["file"], f"  {line}\n")
                self.assertEqual([h.split()[2].rsplit(":", 2)[0] for h in audit.audit(self.root)[0]], ["other.json"])
                (self.root / "other.json").unlink()
                self.write(a["file"], "nothing here\n")
                hits = audit.audit(self.root)[0]
                self.assertEqual(len(hits), 1)
                self.assertIn("stale exemption", hits[0])
        # an entry whose line hits no term: audit.json is the real one, so plant a config
        cfg = json.loads((ROOT / "devtools" / "audit.json").read_text())
        clean = "a line with no term in it"
        cfg["accepted"] = [{"file": "x.json", "line": clean, "why": "test"}]
        fake = self.root / "devtools"
        fake.mkdir(exist_ok=True)
        (fake / "audit.json").write_text(json.dumps(cfg))
        self.write("x.json", clean + "\n")
        old = audit.HERE
        audit.HERE = fake
        try:
            hits = audit.audit(self.root)[0]
        finally:
            audit.HERE = old
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("needless exemption", hits[0])

    def test_lookalike_words_and_fixtures_pass(self):
        self.write("a.md", "harnessing the planner-free design; a harness-like rig\n")
        self.write("tests/fixtures/x.TODO.md", "reported to harness\n")
        hits, _ = audit.audit(self.root)
        self.assertEqual(hits, [])
