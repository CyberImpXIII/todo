"""Import is lossless, deterministic and sends DONE bullets to history.

Lossless is checked two ways on three real TODO.md files (site-scrapers, setup,
hub, all public repos): every word of the source outside headings, rules and
list markers comes back from the rendered TODO.md + TODO-HISTORY.md (a word
count, by a filter written here, independent of the importer's own parser), and
every source block comes back whole from exactly one rendered item.
"""
import json
import re
import shutil
from collections import Counter

from tests.helpers import FIXTURES, Case
from todolib.importer import md_blocks, reconstruct
from todolib.render import parse_blocks, unseal
from todolib.vocab import VOCAB, VOCAB_PATH, Vocab

REAL = ["site-scrapers", "setup", "hub"]
FENCE = re.compile(r"^\s*(```+|~~~+)")
HEADING = re.compile(r"^#{1,6}\s")
RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
MARKER = re.compile(r"^([-*+]|\d+[.)])\s+")


def source_words(text):
    """Words of a hand-written TODO.md that belong to items: outside fences, a
    heading or a rule line is structure, and a top-level list marker is not text."""
    words, fence = [], None
    for line in text.expandtabs(4).split("\n"):
        if fence:
            words += line.split()
            if line.strip().startswith(fence) and not line.strip().strip(fence[0]):
                fence = None
            continue
        m = FENCE.match(line)
        if m:
            fence = m.group(1)
        if HEADING.match(line) or RULE.match(line):
            continue
        words += MARKER.sub("", line, count=1).split()
    return words


def norm(s):
    return " ".join(s.split())


class Lossless(Case):
    def imported(self, name):
        d = self.ws / name
        d.mkdir()
        shutil.copy(FIXTURES / f"{name}.TODO.md", d / "TODO.md")
        self.todo("-C", d, "init", "--prefix", "xx")
        self.todo("-C", d, "import", "TODO.md")
        self.todo("-C", d, "render", "--history")
        return d

    def rendered_items(self, d):
        """(item text rebuilt from the render, store entry) for every item, open or closed."""
        by_id = {it["id"]: it for it in self.store(d)["items"] + self.history(d)["items"]}
        out = []
        for f in ("TODO.md", "TODO-HISTORY.md"):
            for blk in parse_blocks((d / f).read_text()):
                it = by_id.pop(blk["id"])
                out.append(reconstruct(it, title=blk["title"], evidence=blk["evidence"]))
        self.assertEqual(by_id, {}, "items the render never shows")
        return out

    def test_every_source_word_comes_back(self):
        for name in REAL + ["done"]:
            with self.subTest(fixture=name):
                d = self.imported(name)
                back = Counter(w for text in self.rendered_items(d) for w in text.split())
                src = Counter(source_words((FIXTURES / f"{name}.TODO.md").read_text()))
                self.assertEqual(src - back, Counter(), "words lost")
                self.assertEqual(back - src, Counter(), "words invented")

    def test_every_source_block_comes_back_whole(self):
        for name in REAL + ["done"]:
            with self.subTest(fixture=name):
                d = self.imported(name)
                blocks, _ = md_blocks((FIXTURES / f"{name}.TODO.md").read_text())
                src = Counter(norm(b.text()) for b in blocks if b.text().strip())
                back = Counter(norm(t) for t in self.rendered_items(d))
                self.assertEqual(src, back)

    def test_a_second_import_adds_nothing(self):
        for name in REAL:
            with self.subTest(fixture=name):
                d = self.imported(name)
                before = (self.store(d), self.history(d))
                out = self.todo("-C", d, "import", FIXTURES / f"{name}.TODO.md").stdout
                self.assertIn("0 new open, 0 new closed", out)
                self.assertEqual((self.store(d), self.history(d)), before)
                out = self.todo("-C", d, "import", "TODO.md").stdout
                self.assertIn("0 new open, 0 new closed", out)

    def test_the_import_is_deterministic(self):
        one, two = self.imported("setup"), self.ws / "two"
        two.mkdir()
        shutil.copy(FIXTURES / "setup.TODO.md", two / "TODO.md")
        self.todo("-C", two, "init", "--prefix", "xx")
        self.todo("-C", two, "import", "TODO.md")
        strip = lambda d: [dict(it, repo=None) for it in self.store(d)["items"]]  # noqa: E731
        self.assertEqual(strip(one), strip(two))
        # The seal digests the whole file, repo name included, so it is left out here.
        self.assertEqual(unseal((one / "TODO.md").read_text()).replace("# setup TODO", "# two TODO"),
                         unseal((two / "TODO.md").read_text()))


class DoneBullets(Case):
    def test_done_bullets_go_to_history_with_their_dates_and_the_store_stays_trim(self):
        d = self.ws / "d"
        d.mkdir()
        shutil.copy(FIXTURES / "done.TODO.md", d / "TODO.md")
        self.todo("-C", d, "init", "--prefix", "dd")
        out = self.todo("-C", d, "import", "TODO.md").stdout
        self.assertIn("4 new open, 4 new closed", out)
        hist = {it["title"][:24]: it for it in self.history(d)["items"]}
        self.assertEqual({k: (v["done"], v["kind"]) for k, v in hist.items()}, {
            "DONE 2026-10-02: the two": ("2026-10-02", "decision"),
            "DONE 2026-10-03: hooks w": ("2026-10-03", "decision"),
            "DONE 2026-09-29 the rend": ("2026-09-29", "bug"),
            "fixed the importer's fen": (None, "note"),
        })
        self.assertTrue(all(it["status"] == "done" for it in hist.values()))
        store = self.store(d)["items"]
        self.assertEqual(sorted(it["title"][:12] for it in store),
                         ["A synthetic ", "Still open: ", "The parser d", "~~an old ide"])
        self.assertNotIn("DONE 2026-10-02", (d / "TODO.md").read_text())
        out = self.check(d).stdout
        self.assertIn("4 open, 4 closed", out)
        self.assertIn("ok    required", out)
        self.assertIn("1 imported closed item(s) carry no date", out)

    def test_a_closed_bullet_gets_the_import_resolution_and_an_open_one_none(self):
        """td-1 (PLAN-todo-tool.md, end): a bullet carries no resolution, so a closed
        one gets done-deprecated, shown as such; the same text without the DONE
        marker stays open with none. The marker is the input that changes it."""
        deprecated = VOCAB.role("import_resolution")
        self.assertEqual(deprecated, "done-deprecated")
        for marker, where, resolution in (("DONE 2026-10-02: ", "history", deprecated), ("", "store", None)):
            with self.subTest(marker=marker):
                d = self.ws / f"m{len(marker)}"
                d.mkdir()
                (d / "TODO.md").write_text(f"# m\n\n## Own bugs\n\n- {marker}the parser drops tabs\n")
                self.todo("-C", d, "init", "--prefix", "mm")
                self.todo("-C", d, "import", "TODO.md")
                got = {"history": self.history(d)["items"], "store": self.store(d)["items"]}
                self.assertEqual(len(got[where]), 1)
                self.assertEqual(got[where][0]["resolution"], resolution)
                self.check(d)
        d = self.ws / "d"
        d.mkdir()
        shutil.copy(FIXTURES / "done.TODO.md", d / "TODO.md")
        self.todo("-C", d, "init", "--prefix", "dd")
        self.todo("-C", d, "import", "TODO.md")
        self.assertEqual({it["resolution"] for it in self.history(d)["items"]}, {deprecated})
        self.assertEqual({it["resolution"] for it in self.store(d)["items"]}, {None})
        shown = self.todo("-C", d, "history").stdout
        self.assertEqual(shown.count(f"-> {deprecated}"), 4)
        self.todo("-C", d, "render", "--history")
        self.assertEqual((d / "TODO-HISTORY.md").read_text().count(f"· resolution: {deprecated}"), 4)


class ConfirmedHeading(Case):
    """td-22 (PLAN-todo-tool.md §9 step 1, Jacob 2026-10-09): a block under a
    Confirmed heading is settled work and imports closed; one under Unconfirmed
    stays open. The vocab rule is the input that changes it."""
    CONFIRMED = "Confirmed (2026-10-01, by probe unless stated)"
    UNCONFIRMED = "Unconfirmed suspicions"

    def test_confirmed_imports_done_and_unconfirmed_stays_open(self):
        d = self.ws / "c"
        d.mkdir()
        (d / "TODO.md").write_text(f"# c\n\n## {self.CONFIRMED}\n\n- **a settled finding** probed and true\n\n"
                                   f"## {self.UNCONFIRMED}\n\n- **maybe this** not probed yet\n")
        self.todo("-C", d, "init", "--prefix", "cc")
        self.todo("-C", d, "import", "TODO.md")
        closed, open_ = self.history(d)["items"], self.store(d)["items"]
        self.assertEqual([(it["title"], it["status"], it["resolution"]) for it in closed],
                         [("a settled finding", VOCAB.role("closed_status"), VOCAB.role("import_resolution"))])
        self.assertEqual([(it["title"], it["kind"], it["status"]) for it in open_],
                         [("maybe this", "suspicion", VOCAB.role("default_status"))])

    def test_removing_the_rule_leaves_confirmed_open(self):
        raw = json.loads(VOCAB_PATH.read_text())
        rules = raw["import"]["headings"]
        self.assertEqual(sum(r["match"] == "confirmed" for r in rules), 1)
        raw["import"]["headings"] = [r for r in rules if r["match"] != "confirmed"]
        path = self.tmp / "vocab.json"
        path.write_text(json.dumps(raw))
        without = Vocab(path)
        done, open_ = VOCAB.role("closed_status"), VOCAB.role("default_status")
        note = VOCAB.role("default_kind")
        self.assertEqual(VOCAB.heading_rule(["c", self.CONFIRMED]), (note, done))
        self.assertEqual(without.heading_rule(["c", self.CONFIRMED]), (note, open_))
        for v in (VOCAB, without):  # the word-start match keeps Unconfirmed out, rule or no rule
            self.assertEqual(v.heading_rule(["c", self.UNCONFIRMED]), ("suspicion", open_))
