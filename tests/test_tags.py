"""Ids and tags (PLAN-services.md §3; PLAN-todo-tool.md §9 step 4): `todo:<id>`
wherever an id is taken; tags derived from the fields plus the ones set by hand;
`get`, `find` and `refs`; and the `tags` gate. The test PLAN-services.md §3 asks
of every service: a planted tag changes what `find` returns."""
import json
import re
import unittest

from tests.helpers import ROOT, Case, workspace_file
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
OTHER_KIND = next(k for k in VOCAB.kinds if k not in (NOTE, VOCAB.role("report_kind")) and not VOCAB.kinds[k]["requires"])
PLAN = "plan:PLAN-x.md§3"
SERVICES_PLAN = workspace_file("PLAN-services.md")


def found(out):
    return [ln.split()[0] for ln in out.splitlines() if ln.startswith("todo:")]


class Ids(Case):
    def test_every_id_argument_takes_the_service_form(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE)
        self.todo("-C", a, "add", "two", "--kind", NOTE, "--parent", "todo:aa-1", "--blocked-by", "todo:aa-1")
        self.assertEqual(self.store(a)["items"][1]["parent"], "aa-1")
        self.assertEqual(self.store(a)["items"][1]["blocked_by"], ["aa-1"])
        self.assertIn("title: two", self.todo("-C", a, "show", "todo:aa-2").stdout)
        self.todo("-C", a, "edit", "todo:aa-2", "--title", "two, edited")
        self.todo("-C", a, "done", "todo:aa-1", "--resolution", "r")
        self.assertIn("aa-1", self.todo("-C", a, "history", "todo:aa-1").stdout)
        self.assertEqual(json.loads(self.todo("-C", a, "get", "todo:aa-2").stdout)["id"], "todo:aa-2")


class Find(Case):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", self.a, "add", "one", "--kind", NOTE, "--work", "code")
        self.todo("-C", self.a, "add", "two", "--kind", OTHER_KIND)
        self.todo("-C", self.b, "add", "three", "--kind", NOTE)

    def test_a_planted_tag_changes_what_find_returns(self):
        self.assertEqual(found(self.todo("-C", self.a, "find", PLAN).stdout), [])
        self.todo("-C", self.b, "edit", "bb-1", "--tags", PLAN, "origin:jacob")
        self.assertEqual(found(self.todo("-C", self.a, "find", PLAN).stdout), ["todo:bb-1"])
        self.assertEqual(found(self.todo("-C", self.a, "find", PLAN, "origin:model").stdout), [])
        self.todo("-C", self.b, "edit", "bb-1", "--tags")
        self.assertIsNone(self.store(self.b)["items"][0]["tags"])
        self.assertEqual(found(self.todo("-C", self.a, "find", PLAN).stdout), [])

    def test_derived_tags_follow_the_fields_and_every_tag_named_must_hold(self):
        self.assertEqual(found(self.todo("-C", self.a, "find", f"kind:{NOTE}").stdout), ["todo:aa-1", "todo:bb-1"])
        self.assertEqual(found(self.todo("-C", self.a, "find", f"kind:{NOTE}", "repo:b").stdout), ["todo:bb-1"])
        self.assertEqual(found(self.todo("-C", self.a, "find", "todo.work:code").stdout), ["todo:aa-1"])
        self.todo("-C", self.a, "edit", "aa-2", "--kind", NOTE)
        self.assertEqual(found(self.todo("-C", self.a, "find", f"kind:{NOTE}", "repo:a").stdout), ["todo:aa-1", "todo:aa-2"])

    def test_find_reads_history_unless_open_and_json_carries_the_tags(self):
        self.todo("-C", self.a, "done", "aa-1", "--resolution", "r")
        out = self.todo("-C", self.a, "find", f"status:{VOCAB.closed}").stdout
        self.assertEqual(found(out), ["todo:aa-1"])
        self.assertIn("(closed)", out)
        self.assertEqual(found(self.todo("-C", self.a, "find", "repo:a", "--open").stdout), ["todo:aa-2"])
        recs = json.loads(self.todo("-C", self.a, "find", "repo:a", "--json").stdout)["records"]
        one = next(r for r in recs if r["id"] == "todo:aa-1")
        self.assertTrue(one["closed"])
        self.assertIn("todo.work:code", one["tags"])

    def test_find_refuses_a_tag_outside_the_vocabulary(self):
        for bad in ("nonamespace:x", "notatag", "trust:trusted"):
            with self.subTest(tag=bad):
                self.todo("-C", self.a, "find", bad, ok=False)


class Refs(Case):
    def test_refs_lists_parents_blockers_and_tags_naming_the_id(self):
        a, b = self.repo("a", "aa"), self.repo("b", "bb")
        self.todo("-C", a, "add", "target", "--kind", NOTE)
        self.todo("-C", b, "add", "child", "--kind", NOTE, "--parent", "aa-1")
        self.todo("-C", b, "add", "waits", "--kind", NOTE, "--blocked-by", "aa-1")
        self.todo("-C", b, "add", "cites", "--kind", NOTE, "--tags", "ref:todo:aa-1", "ref:kb:hooks#sessionstart")
        self.todo("-C", b, "add", "unrelated", "--kind", NOTE)
        self.assertEqual(found(self.todo("-C", a, "refs", "todo:aa-1").stdout), ["todo:bb-1", "todo:bb-2", "todo:bb-3"])
        self.assertEqual(found(self.todo("-C", a, "refs", "aa-1").stdout), ["todo:bb-1", "todo:bb-2", "todo:bb-3"])
        self.assertEqual(found(self.todo("-C", a, "refs", "kb:hooks#sessionstart").stdout), ["todo:bb-3"])
        self.assertEqual(found(self.todo("-C", a, "refs", "bb-4").stdout), [])
        self.assertEqual(self.todo("-C", a, "refs", "aa-9", ok=None).returncode, 1)


class Get(Case):
    def test_get_one_record_dangling_and_unchecked(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE, "--work", "code", "--tags", PLAN)
        got = json.loads(self.todo("-C", a, "get", "aa-1").stdout)
        self.assertEqual((got["id"], got["closed"], got["record"]["title"]), ("todo:aa-1", False, "one"))
        self.assertEqual(got["tags"], ["repo:a", f"kind:{NOTE}", f"status:{VOCAB.role('default_status')}", "todo.work:code", PLAN])
        r = self.todo("-C", a, "get", "aa-7", ok=None)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("dangling", r.stderr)
        for unjudged in ("zz-1", "kb:hooks#sessionstart"):
            with self.subTest(id=unjudged):
                r = self.todo("-C", a, "get", unjudged, ok=None)
                self.assertEqual(r.returncode, 3, r.stderr)
                self.assertIn("UNCHECKED", r.stderr)


class Gate(Case):
    def test_add_and_edit_refuse_what_check_would_fail(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE)
        for bad, why in (("nonamespace:x", "no namespace"), (f"kind:{NOTE}", "derived from the item's kind"),
                         ("trust:trusted", "closed to untrusted"), ("plan:notaplan", "not PLAN-<name>.md"),
                         ("ref:aa-1", "not <service>:<id>"), ("ref:todo:aa-9", "aa-9 resolves in no")):
            with self.subTest(tag=bad):
                r = self.todo("-C", a, "edit", "aa-1", "--tags", bad, ok=False)
                self.assertIn(why, r.stderr)
        self.assertIsNone(self.store(a)["items"][0]["tags"])

    def test_check_fails_a_bad_or_dangling_tag_and_counts_a_foreign_ref(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", NOTE, "--tags", "ref:kb:x")
        out = self.check(a).stdout
        self.assertIn("1 ref: tag(s) name another service's record: unchecked", out)
        data = self.store(a)
        for bad, why in ((["ref:todo:aa-5"], "dangling"), (["status:open"], "derived"), (["origin:nobody"], "closed to")):
            with self.subTest(tags=bad):
                data["items"][0]["tags"] = bad
                self.write_json(a / "todo.json", data)
                self.assertFails(a, "tags", why)
        data["items"][0]["tags"] = "plan:PLAN-x.md"
        self.write_json(a / "todo.json", data)
        self.assertFails(a, "schema", "tags must be a non-empty list")


class Vocabulary(unittest.TestCase):
    def test_the_service_prefix_is_the_name_in_services_json(self):
        self.assertEqual(json.loads((ROOT / "services.json").read_text())["name"], VOCAB.service)

    @unittest.skipUnless(SERVICES_PLAN, "the plan lives in the workspace, not in a fresh clone")
    def test_the_shared_namespaces_are_the_plans_table(self):
        """The local copy of PLAN-services.md §3's table, until the architecture
        service holds it (TODO.md): the same namespaces, in the same order."""
        text = SERVICES_PLAN.read_text().split("### Every record a service holds has an id and tags", 1)[1]
        table = text.split("| namespace |", 1)[1].split("\n\n", 1)[0]
        plan = re.findall(r"^\s*\| `([a-z]+):` \|", table, re.M)
        self.assertEqual(plan, VOCAB.shared_namespaces)
