"""Sizes (PLAN-small-tasks.md §2): every item gets an estimate, `size`; `todo ready`
lists only the sizes one checkpoint holds and refuses the rest by name; `todo
split` breaks a big item into children under `parent`, and the parent closes
with its last child; `todo check` fails a big open item with no children."""
from tests.helpers import Case
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
WORK = next(iter(VOCAB.works))
S, M = VOCAB.ready_sizes
L = VOCAB.split_size
SUSPICION = next(k for k, v in VOCAB.kinds.items() if "probe" in v["requires"])


def listed(out):
    return [ln.split()[0] for ln in out.splitlines() if ln and not ln.startswith((" ", "(", "refused"))]


class Ready(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        for title, size in (("small", S), ("medium", M), ("large", L), ("unsized", None)):
            self.todo("-C", self.a, "add", title, "--kind", NOTE, "--work", WORK, "--done-when", "dw",
                      *(["--size", size] if size else []))

    def test_ready_lists_only_the_ready_sizes_and_refuses_the_rest_by_name(self):
        out = self.todo("-C", self.a, "ready").stdout
        self.assertEqual(listed(out), ["aa-1", "aa-2"])
        refused = out.split("refused", 1)[1]
        self.assertIn("aa-3     size L: split it first (todo split aa-3", refused)
        self.assertIn("aa-4     no size (todo edit aa-4 --size", refused)

    def test_brief_is_not_ready_for_an_unsized_or_large_item(self):
        self.todo("-C", self.a, "brief", "aa-1")
        for iid, why in (("aa-3", "size L: split it first"), ("aa-4", "no size")):
            with self.subTest(id=iid):
                r = self.todo("-C", self.a, "brief", iid, ok=False)
                self.assertIn(f"NOT READY: {why}", r.stdout)

    def test_sizing_an_item_makes_it_ready_and_clearing_it_refuses_it_again(self):
        self.todo("-C", self.a, "edit", "aa-4", "--size", S)
        self.assertIn("aa-4", listed(self.todo("-C", self.a, "ready").stdout))
        self.todo("-C", self.a, "edit", "aa-4", "--size", "")
        self.assertIsNone(self.store(self.a)["items"][3]["size"])
        self.assertNotIn("aa-4", listed(self.todo("-C", self.a, "ready").stdout))


class Split(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "big job", "--kind", SUSPICION, "--probe", "p", "--work", WORK,
                  "--files", "x.py", "--tags", "origin:jacob", "--done-when", "all of it", "--size", L)

    def items(self):
        return {it["id"]: it for it in self.store(self.a)["items"]}

    def test_an_open_large_item_with_no_children_fails_check_until_split(self):
        self.assertFails(self.a, "sizes", f"size {L} and no children")
        out = self.todo("-C", self.a, "split", "aa-1", "first part", "second part", "--size", S).stdout
        self.assertIn("split aa-1 into aa-2, aa-3", out)
        out = self.check(self.a).stdout
        self.assertTrue([ln for ln in out.splitlines() if ln.split()[:2] == ["ok", "sizes"]], out)

    def test_children_copy_the_parent_and_point_at_it(self):
        self.todo("-C", self.a, "split", "aa-1", "first part", "--size", M)
        child, parent = self.items()["aa-2"], self.items()["aa-1"]
        for f in ("kind", "repo", "work", "files", "tags", "probe"):
            self.assertEqual(child[f], parent[f], f)
        self.assertEqual((child["parent"], child["size"], child["done_when"]), ("aa-1", M, None))
        self.assertIn("split from aa-1", child["evidence"])

    def test_split_makes_the_parent_large_and_refuses_a_large_child(self):
        self.todo("-C", self.a, "add", "medium", "--kind", NOTE, "--size", M)
        self.todo("-C", self.a, "split", "aa-2", "part", "--size", S)
        self.assertEqual(self.items()["aa-2"]["size"], L)
        self.todo("-C", self.a, "split", "aa-1", "part", "--size", L, ok=False)
        self.todo("-C", self.a, "split", "aa-9", "part", "--size", S, ok=False)

    def test_the_parent_closes_with_its_last_child_and_not_before(self):
        self.todo("-C", self.a, "split", "aa-1", "one", "two", "--size", S)
        self.todo("-C", self.a, "done", "aa-2", "--resolution", "r")
        self.assertIn("aa-1", self.items())
        out = self.todo("-C", self.a, "done", "aa-3", "--resolution", "r").stdout
        self.assertIn("closed aa-1 too", out)
        self.assertNotIn("aa-1", self.items())
        closed = {it["id"]: it for it in self.history(self.a)["items"]}
        self.assertIn("every child of this split item is closed (aa-2, aa-3)", closed["aa-1"]["resolution"])
        self.check(self.a)

    def test_a_parent_that_is_not_large_stays_open(self):
        self.todo("-C", self.a, "add", "plain parent", "--kind", NOTE, "--size", M)
        self.todo("-C", self.a, "add", "child", "--kind", NOTE, "--size", S, "--parent", "aa-2")
        self.todo("-C", self.a, "done", "aa-3", "--resolution", "r")
        self.assertIn("aa-2", self.items())


class Gate(Case):
    def test_an_undeclared_size_fails_check_and_is_refused(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE, "--size", "XL", ok=False)
        self.todo("-C", a, "add", "one", "--kind", NOTE)
        self.assertIn("1 open item(s) unsized", self.check(a).stdout)
        data = self.store(a)
        data["items"][0]["size"] = "XL"
        self.write_json(a / "todo.json", data)
        self.assertFails(a, "vocab", "size 'XL' is not declared")
