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
        self.assertEqual(sorted(cfg), ["no-roster"], "checks.json holds only what this repo needs")
        excluded = cfg["no-roster"]["exclude"]
        skip = json.loads((ROOT / "devtools" / "audit.json").read_text())["skip"]
        self.assertTrue(excluded)
        for rel in excluded:
            self.assertIn(rel, skip, f"{rel} is excluded from no-roster but not skipped by devtools/audit.py")
            self.assertTrue((ROOT / rel).is_file(), f"{rel} is excluded but does not exist")

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

    def test_lookalike_words_and_fixtures_pass(self):
        self.write("a.md", "harnessing the planner-free design; a harness-like rig\n")
        self.write("tests/fixtures/x.TODO.md", "reported to harness\n")
        hits, _ = audit.audit(self.root)
        self.assertEqual(hits, [])
