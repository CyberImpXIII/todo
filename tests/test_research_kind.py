"""The research kind (PLAN-services.md §4 step 8.3; §3 S7 R1): an item that points
at the research service's question ids (`rs-<n>`) and never restates the answer.
The ids are stored bare in the `research` field, reach `find` and `refs` as derived
`ref:research:rs-<n>` tags, and stay unchecked (INFO) until a registry resolves them:
tools/research has no CLI yet."""
from tests.helpers import Case
from todolib.vocab import VOCAB

RS = VOCAB.research_service
KIND = next(k for k, v in VOCAB.kinds.items() if "research" in v["requires"])
NOTE = VOCAB.role("default_kind")


def found(out):
    return [ln.split()[0] for ln in out.splitlines() if ln.startswith("todo:")]


class ResearchKind(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")

    def item(self):
        return self.store(self.a)["items"][-1]

    def test_a_research_item_needs_its_ids(self):
        r = self.todo("-C", self.a, "add", "q", "--kind", KIND, ok=False)
        self.assertIn("needs --research", r.stderr)
        self.todo("-C", self.a, "add", "q", "--kind", KIND, "--research", "rs-3", f"{RS}:rs-12")
        self.assertEqual(self.item()["research"], ["rs-3", "rs-12"])

    def test_a_malformed_id_is_refused(self):
        for bad in ("rs-0", "rs-x", "td-3", "other:rs-3"):
            with self.subTest(bad):
                r = self.todo("-C", self.a, "add", "q", "--kind", KIND, "--research", bad, ok=False)
                self.assertIn("research must be", r.stderr)
        r = self.todo("-C", self.a, "add", "q", "--kind", KIND, "--research", "rs-1", "rs-1", ok=False)
        self.assertIn("twice", r.stderr)

    def test_the_ids_are_refs_that_find_and_refs_reach(self):
        self.todo("-C", self.a, "add", "q", "--kind", KIND, "--research", "rs-3")
        self.assertEqual(found(self.todo("-C", self.a, "find", f"ref:{RS}:rs-3").stdout), ["todo:aa-1"])
        self.assertEqual(found(self.todo("-C", self.a, "find", f"ref:{RS}:rs-4").stdout), [])
        self.assertIn("todo:aa-1", self.todo("-C", self.a, "refs", f"{RS}:rs-3", ok=None).stdout)

    def test_any_kind_may_point_at_research_and_edit_clears_it(self):
        self.todo("-C", self.a, "add", "n", "--kind", NOTE, "--research", "rs-5")
        self.todo("-C", self.a, "edit", "aa-1", "--research")
        self.assertIsNone(self.item()["research"])

    def test_a_research_item_cannot_lose_its_ids(self):
        self.todo("-C", self.a, "add", "q", "--kind", KIND, "--research", "rs-3")
        self.todo("-C", self.a, "edit", "aa-1", "--research", ok=False)
        self.assertEqual(self.item()["research"], ["rs-3"])

    def test_check_counts_them_unchecked_and_fails_one_written_around_the_cli(self):
        self.todo("-C", self.a, "add", "q", "--kind", KIND, "--research", "rs-3", "rs-4")
        out = self.check(self.a).stdout
        self.assertIn("2 ref: tag(s) name another service's record: unchecked", out)
        data = self.store(self.a)
        data["items"][0]["research"] = ["nope"]
        self.write_json(self.a / "todo.json", data)
        self.assertFails(self.a, "schema", "research must be")

    def test_it_renders(self):
        self.todo("-C", self.a, "add", "q", "--kind", KIND, "--research", "rs-3")
        self.assertIn("rs-3", (self.a / "TODO.md").read_text())
        self.assertIn(VOCAB.kinds[KIND]["heading"], (self.a / "TODO.md").read_text())
