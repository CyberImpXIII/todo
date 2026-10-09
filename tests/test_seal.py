"""The stores resist a hand edit (PLAN-todo-tool.md §9, the gap his question
found): both files sit read-only (0444) between CLI writes, carry a seal over
their content that the CLI rewrites on every write, and `todo check` fails a file
whose seal does not match. cli.json declares them, so tools/checks and a shared
hook can hold every writer but this CLI off them."""
import json
import os
import stat
import subprocess
import unittest

from tests.helpers import ROOT, Case, git_commit
from todolib.cli import COMMANDS
from todolib.store import FORMAT, HISTORY_FILE, LEGACY_FORMAT, SEAL_KEY, STORE_FILE, content_seal
from todolib.vocab import VOCAB

NOTE = VOCAB.role("default_kind")
FILES = (STORE_FILE, HISTORY_FILE)


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class Sealed(Case):
    def setUp(self):
        super().setUp()
        self.a = self.repo("a", "aa")
        self.todo("-C", self.a, "add", "one", "--kind", NOTE)
        self.todo("-C", self.a, "add", "two", "--kind", NOTE)

    def hand_edit(self, name, change):
        """What an editor does: make the file writable, change it, save it."""
        path = self.a / name
        data = json.loads(path.read_text())
        change(data)
        self.write_json(path, data, seal=False)

    def test_every_cli_write_leaves_both_files_sealed_and_read_only(self):
        for name in FILES:
            with self.subTest(file=name):
                data = json.loads((self.a / name).read_text())
                self.assertEqual(mode(self.a / name), 0o444)
                self.assertEqual((data["format"], data[SEAL_KEY]), (FORMAT, content_seal(data)))
        out = self.check(self.a).stdout
        self.assertTrue([ln for ln in out.splitlines() if ln.split()[:2] == ["ok", "seal"]], out)

    def test_the_cli_works_on_a_read_only_store(self):
        self.assertEqual([mode(self.a / n) for n in FILES], [0o444, 0o444])
        self.todo("-C", self.a, "edit", "aa-1", "--title", "one, edited")
        self.todo("-C", self.a, "done", "aa-2", "--resolution", "r")
        self.todo("-C", self.a, "add", "three", "--kind", NOTE)
        self.assertEqual([it["title"] for it in self.store(self.a)["items"]], ["one, edited", "three"])
        self.assertEqual([it["id"] for it in self.history(self.a)["items"]], ["aa-2"])
        self.assertEqual([mode(self.a / n) for n in FILES], [0o444, 0o444])
        self.check(self.a)

    def test_a_hand_edit_to_either_file_fails_check(self):
        for name, change in ((STORE_FILE, lambda d: d["items"][0].update(title="edited by hand")),
                             (STORE_FILE, lambda d: d.update(next=d["next"] + 5)),
                             (HISTORY_FILE, lambda d: d["items"].append({"id": "aa-9", "title": "planted"}))):
            with self.subTest(file=name):
                before = (self.a / name).read_text()
                self.hand_edit(name, change)
                self.assertFails(self.a, "seal", f"{name}: its seal does not match its content")
                os.chmod(self.a / name, 0o644)
                (self.a / name).write_text(before)
                self.check(self.a)

    def test_a_reformatted_file_keeps_its_seal(self):
        """The seal judges content, not spacing: a file re-indented, unchanged, passes."""
        data = json.loads((self.a / STORE_FILE).read_text())
        os.chmod(self.a / STORE_FILE, 0o644)
        (self.a / STORE_FILE).write_text(json.dumps(data, indent=4) + "\n")
        self.check(self.a)

    def test_a_mutation_refuses_over_a_broken_seal_and_reseal_records_it(self):
        self.hand_edit(STORE_FILE, lambda d: d["items"][0].update(title="edited by hand"))
        edited = (self.a / STORE_FILE).read_text()
        for args in (("add", "three", "--kind", NOTE), ("edit", "aa-2", "--title", "x"),
                     ("done", "aa-2", "--resolution", "r")):
            with self.subTest(cmd=args[0]):
                r = self.todo("-C", self.a, *args, ok=False)
                self.assertIn("changed around the CLI", r.stderr)
                self.assertEqual((self.a / STORE_FILE).read_text(), edited)
        self.todo("-C", self.a, "reseal", "--reason", "", ok=False)
        out = self.todo("-C", self.a, "reseal", "--reason", "title fixed by hand, diff read").stdout
        self.assertIn(f"resealed {STORE_FILE}", out)
        data = self.store(self.a)
        self.assertEqual(data["items"][0]["title"], "edited by hand")
        self.assertEqual(data["hand_edits"][-1]["via"], "reseal")
        self.assertEqual(data["hand_edits"][-1]["files"], [STORE_FILE])
        self.check(self.a)
        self.todo("-C", self.a, "reseal", "--reason", "again", ok=False)

    def test_removing_the_seal_is_not_a_way_around_it(self):
        self.hand_edit(STORE_FILE, lambda d: d.pop(SEAL_KEY))
        self.assertFails(self.a, "seal", f"{STORE_FILE}: format {FORMAT} with no seal")
        git_commit(self.a, "sealed")
        os.chmod(self.a / STORE_FILE, 0o644)
        self.todo("-C", self.a, "reseal", "--reason", "restore the seal")
        git_commit(self.a, "sealed again")
        self.hand_edit(STORE_FILE, lambda d: (d.pop(SEAL_KEY), d.update(format=LEGACY_FORMAT)))
        self.assertFails(self.a, "seal", "its last git commit was sealed")
        r = self.todo("-C", self.a, "add", "three", "--kind", NOTE, ok=False)
        self.assertIn("changed around the CLI", r.stderr)


class Legacy(Case):
    def test_a_store_written_before_seals_warns_until_the_next_write_seals_it(self):
        a = self.repo("a", "aa", git_init=False)
        self.todo("-C", a, "add", "one", "--kind", NOTE)
        for name in FILES:
            data = json.loads((a / name).read_text())
            data.pop(SEAL_KEY)
            data["format"] = LEGACY_FORMAT
            self.write_json(a / name, data, seal=False)
        out = self.check(a).stdout
        self.assertEqual(sum(1 for ln in out.splitlines() if ln.split()[:2] == ["WARN", "seal"]), 2, out)
        self.todo("-C", a, "edit", "aa-1", "--title", "one, edited")
        out = self.check(a).stdout
        self.assertFalse([ln for ln in out.splitlines() if "seal" in ln.split()[:2] and ln.split()[0] != "ok"], out)
        self.assertEqual(self.store(a)["format"], FORMAT)


class Declared(unittest.TestCase):
    """cli.json is what tools/checks (accessor, stores-readonly) and the shared
    store hook read: it must name exactly the files this CLI writes, and exactly
    the commands it offers, which `todo help` lists."""

    def setUp(self):
        self.cli = json.loads((ROOT / "cli.json").read_text())

    def test_the_store_is_the_files_the_cli_writes(self):
        self.assertEqual(self.cli["store"], [STORE_FILE, HISTORY_FILE])
        self.assertEqual(self.cli["cli"], "todo")

    def test_the_verbs_are_the_commands_and_help_lists_each(self):
        self.assertEqual(self.cli["verbs"], list(COMMANDS))
        out = subprocess.run([str(ROOT / "todo"), "help"], capture_output=True, text=True, check=True).stdout
        listed = [ln.split()[0] for ln in out.splitlines() if ln.startswith("  ") and ln.strip()]
        self.assertEqual(listed, list(COMMANDS))
