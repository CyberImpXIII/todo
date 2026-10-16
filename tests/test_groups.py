"""A heading is not an item (PLAN-todo-tool.md §10.2 step 4): the todo.group:
namespace (this service's own, PLAN-services.md §3 row 2), and the `groups` gate,
which warns on an open item with no work that open items use as a group."""
import json
import tempfile
from pathlib import Path

from tests.helpers import Case
from todolib import tags
from todolib.vocab import VOCAB, VOCAB_PATH, Vocab

NOTE = VOCAB.role("default_kind")
REPORT = VOCAB.role("report_kind")
GROUP = tags.GROUP_NS


class Groups(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")

    def add(self, title, *extra):
        self.todo("-C", self.a, "add", title, "--kind", NOTE, *extra)
        return self.store(self.a)["items"][-1]["id"]

    def warnings(self):
        out = self.check(self.a).stdout  # a WARN, never red
        return [ln for ln in out.splitlines() if ln.split()[:2] == ["WARN", "groups"]]

    def test_the_namespace_is_the_services_own(self):
        self.assertTrue(GROUP.startswith(VOCAB.service + "."), GROUP)
        self.assertNotIn(GROUP, VOCAB.shared_namespaces)

    def test_a_group_tag_is_stored_and_found(self):
        iid = self.add("child", "--tags", f"{GROUP}:inc-2")
        self.assertEqual(self.store(self.a)["items"][0]["tags"], [f"{GROUP}:inc-2"])
        out = self.todo("-C", self.a, "find", f"{GROUP}:inc-2").stdout
        self.assertEqual([ln.split()[0] for ln in out.splitlines() if ln.startswith("todo:")], [f"todo:{iid}"])

    def test_a_group_must_be_a_name(self):
        for bad in ("Inc-2", "a/b", "-x"):
            with self.subTest(bad):
                r = self.todo("-C", self.a, "add", "x", "--kind", NOTE, "--tags", f"{GROUP}:{bad}", ok=False)
                self.assertIn("is not a name", r.stderr)
        self.todo("-C", self.a, "add", "x", "--kind", NOTE, "--tags", "group:inc-2", ok=False)

    def test_a_heading_used_as_a_parent_warns(self):
        head = self.add("Heading")
        self.add("child", "--parent", head)
        hits = self.warnings()
        self.assertEqual(len(hits), 1, hits)
        self.assertIn(head, hits[0])
        self.assertIn(f"{GROUP}:{head}", hits[0])

    def test_a_heading_named_by_a_group_tag_warns(self):
        head = self.add("Heading")
        self.add("child", "--tags", f"{GROUP}:{head}")
        self.assertEqual(len(self.warnings()), 1)

    def test_an_item_with_work_is_a_real_parent(self):
        head = self.add("Real work", "--work", "code")
        self.add("child", "--parent", head)
        self.assertEqual(self.warnings(), [])

    def test_a_heading_nobody_uses_is_not_flagged(self):
        self.add("Heading")
        self.assertEqual(self.warnings(), [])

    def test_a_closed_child_does_not_make_a_group(self):
        head = self.add("Heading")
        kid = self.add("child", "--parent", head)
        self.todo("-C", self.a, "done", kid, "--resolution", "r")
        self.assertEqual(self.warnings(), [])

    def test_a_split_item_without_work_is_a_heading_too(self):
        """The imported headings inc-2..12 are size L with children: the case itself."""
        head = self.add("Big", "--size", VOCAB.split_size)
        self.add("child", "--parent", head)
        self.assertEqual(len(self.warnings()), 1)

    def test_a_report_is_not_a_heading(self):
        self.todo("-C", self.a, "add", "told them", "--kind", REPORT, "--reported-to", "elsewhere")
        rep = self.store(self.a)["items"][-1]["id"]
        self.add("child", "--parent", rep)
        self.assertEqual(self.warnings(), [])

    def test_an_own_namespace_outside_the_prefix_refuses_to_load(self):
        data = json.loads(VOCAB_PATH.read_text())
        data["tags"]["own"]["group"] = {"doc": "x", "rule": "name"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "vocab.json"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "service prefix"):
                Vocab(p)
