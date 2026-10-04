"""The direction audit finds what it is for, and skips only what it says it skips."""
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

    def test_lookalike_words_and_fixtures_pass(self):
        self.write("a.md", "harnessing the planner-free design; a harness-like rig\n")
        self.write("tests/fixtures/x.TODO.md", "reported to harness\n")
        hits, _ = audit.audit(self.root)
        self.assertEqual(hits, [])
