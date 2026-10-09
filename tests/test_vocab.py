"""Vocabulary both ways: every name the code uses is declared in vocab.json, and
every declared name is handled (parsed, rendered) and documented in README.md."""
import ast
import json
import re
import tempfile
from pathlib import Path

from tests.helpers import ROOT, Case
from todolib import cli, render
from todolib.vocab import VOCAB, Vocab

RAW = json.loads((ROOT / "vocab.json").read_text())


def readme_table(name):
    """Names in README.md's `<!-- vocab:NAME -->` table: the first cell of each row."""
    text = (ROOT / "README.md").read_text()
    m = re.search(r"<!-- vocab:%s -->\n(.*?)\n\n" % name, text, re.S)
    if not m:
        return None
    rows = [ln for ln in m.group(1).splitlines() if ln.startswith("|")][2:]
    return [re.sub(r"[`*]", "", r.split("|")[1]).strip() for r in rows]


class Declared(Case):
    def test_no_bare_vocabulary_literal_in_todolib(self):
        """A kind, status or work named in code goes through VOCAB; a literal would
        silently stop matching when vocab.json is renamed. Field names and command
        names are allowed where they act as such: a key, a .get() argument, a tuple of
        field names, a COMMANDS key."""
        names = set(VOCAB.kinds) | set(VOCAB.statuses) | set(VOCAB.works) | set(VOCAB.resolutions)
        fields = set(VOCAB.field_names())
        commands = set(cli.COMMANDS)
        hits = []
        for f in sorted((ROOT / "todolib").glob("*.py")):
            tree = ast.parse(f.read_text())
            allowed = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                    allowed.add(id(node.slice))
                elif isinstance(node, ast.Call) and getattr(node.func, "attr", None) in ("get", "add_parser") and node.args:
                    allowed.add(id(node.args[0]))
                elif isinstance(node, ast.Dict):
                    allowed.update(id(k) for k in node.keys if k is not None)
                elif isinstance(node, (ast.Tuple, ast.List)):
                    vals = [e.value for e in node.elts if isinstance(e, ast.Constant)]
                    if vals and len(vals) == len(node.elts) and all(v in fields for v in vals):
                        allowed.update(id(e) for e in node.elts)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or node.value not in names:
                    continue
                if id(node) in allowed and (node.value in fields or node.value in commands):
                    continue
                hits.append(f"{f.name}:{node.lineno}: {node.value!r}")
        self.assertEqual(hits, [], "name kinds/statuses/works through VOCAB, never as literals")

    def test_parser_choices_are_the_declared_names(self):
        ap = cli.build_parser()
        sub = next(a for a in ap._actions if a.dest == "command").choices
        for cmd, dest, declared in (("add", "kind", VOCAB.kinds), ("add", "status", VOCAB.statuses),
                                    ("add", "work", VOCAB.works), ("list", "kind", VOCAB.kinds),
                                    ("history", "kind", VOCAB.kinds), ("ready", "work", VOCAB.works)):
            act = next(a for a in sub[cmd]._actions if a.dest == dest)
            self.assertEqual(list(act.choices), list(declared), f"{cmd} --{dest}")

    def test_roles_and_import_rules_name_declared_values(self):
        for rule in VOCAB.import_rules:
            self.assertIn(rule.get("kind", VOCAB.role("default_kind")), VOCAB.kinds)
            self.assertIn(rule.get("status", VOCAB.role("default_status")), VOCAB.statuses)
        bad = dict(RAW, roles=dict(RAW["roles"], closed_status="finished"))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(bad, fh)
        with self.assertRaises(ValueError):
            Vocab(Path(fh.name))
        Path(fh.name).unlink()

    def test_every_resolution_is_named_by_a_role_and_every_role_is_declared(self):
        """A declared resolution no role names would be set and guarded by nothing; a
        role naming an undeclared one would set a value check cannot recognise."""
        self.assertTrue(VOCAB.resolutions)
        for bad in (dict(RAW, resolutions=dict(RAW["resolutions"], **{"done-other": {"doc": "x"}})),
                    dict(RAW, roles=dict(RAW["roles"], import_resolution="done-undeclared"))):
            with self.subTest(bad=sorted(bad["resolutions"]) + [bad["roles"]["import_resolution"]]):
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                    json.dump(bad, fh)
                with self.assertRaises(ValueError):
                    Vocab(Path(fh.name))
                Path(fh.name).unlink()

    def test_every_declared_requirement_is_a_field(self):
        for group in (VOCAB.kinds, VOCAB.statuses):
            for name, spec in group.items():
                for f in spec["requires"]:
                    self.assertIn(f, VOCAB.fields, f"{name} requires undeclared field {f}")

    def test_check_is_red_on_an_undeclared_kind_status_or_work(self):
        a = self.repo("a", "aa")
        self.todo("-C", a, "add", "one", "--kind", VOCAB.role("default_kind"))
        for field in ("kind", "status", "work"):
            with self.subTest(field=field):
                data = self.store(a)
                saved = data["items"][0][field]
                data["items"][0][field] = "undeclared-name"
                self.write_json(a / "todo.json", data)
                self.assertFails(a, "vocab", f"{field} 'undeclared-name' is not declared")
                data["items"][0][field] = saved
                self.write_json(a / "todo.json", data)


class Handled(Case):
    def test_every_kind_status_work_and_field_renders(self):
        a = self.repo("a", "aa")
        extra = {"suspicion": ["--probe", "p"], "temp": ["--retire", "r"]}
        for kind in VOCAB.kinds:
            if kind == VOCAB.role("report_kind"):
                continue
            self.todo("-C", a, "add", f"a {kind}", "--kind", kind, *extra.get(kind, []))
        self.todo("-C", a, "report", "aa-1", "--to", "elsewhere")
        works = list(VOCAB.works)
        for i, status in enumerate(VOCAB.open_statuses()):
            self.todo("-C", a, "add", f"s {status}", "--kind", VOCAB.role("default_kind"), "--parent", "aa-1", "--blocked-by", "aa-1", "--tags", "origin:tool",
                      "--status", status, "--work", works[i % len(works)], "--files", "x.py", "--done-when", "dw",
                      "--repo", "other", "--evidence", "ev")
        for w in works:
            self.todo("-C", a, "add", f"w {w}", "--kind", VOCAB.role("default_kind"), "--work", w)
        md = (a / "TODO.md").read_text()
        for kind, spec in VOCAB.kinds.items():
            self.assertIn(f"## {spec['heading']}", md, kind)
        for status in VOCAB.open_statuses():
            if status != VOCAB.role("default_status"):
                self.assertIn(f"· status: {status}", md)
        for w in works:
            self.assertIn(f"· work: {w}", md)
        self.todo("-C", a, "done", "aa-2", "--resolution", "fixed")
        self.todo("-C", a, "render", "--history")
        hist = (a / "TODO-HISTORY.md").read_text()
        self.assertIn(f"· status: {VOCAB.closed}", hist)
        shown = md + hist
        for name, spec in VOCAB.fields.items():
            if name in render.NOT_FIELD_LINES:
                continue
            self.assertIn(f"· {spec['label']}: ", shown, f"field {name} never renders")

    def test_every_field_has_a_label_or_is_rendered_otherwise(self):
        for name, spec in VOCAB.fields.items():
            self.assertTrue(spec["label"] or name in render.NOT_FIELD_LINES, name)
        self.assertLessEqual(render.NOT_FIELD_LINES, set(VOCAB.fields))


class Documented(Case):
    def test_readme_vocab_tables_equal_vocab_json(self):
        for name, declared in (("kinds", VOCAB.kinds), ("statuses", VOCAB.statuses),
                               ("works", VOCAB.works), ("resolutions", VOCAB.resolutions),
                               ("fields", VOCAB.fields), ("tags", VOCAB.namespaces)):
            doc = readme_table(name)
            self.assertIsNotNone(doc, f"README.md has no <!-- vocab:{name} --> table")
            self.assertEqual(doc, list(declared), f"README vocab:{name} vs vocab.json")
