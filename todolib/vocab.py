"""The vocabulary (vocab.json): kinds, statuses, works, fields, roles, import rules.

Code names a kind or a status only through `role()` or by iterating the
declared names; tests/test_vocab.py audits todolib/ for a bare literal, so a
name used in code is always a declared one.
"""
import json
import re
from pathlib import Path

VOCAB_PATH = Path(__file__).resolve().parent.parent / "vocab.json"


class Vocab:
    def __init__(self, path=VOCAB_PATH):
        data = json.loads(Path(path).read_text())
        self.kinds = data["kinds"]
        self.statuses = data["statuses"]
        self.works = data["works"]
        self.fields = data["fields"]
        self.roles = data["roles"]
        self.import_rules = data["import"]["headings"]
        self.done_marker = re.compile(data["import"]["done_marker"])
        for name, value in self.roles.items():
            pool = self.statuses if name.endswith("_status") else self.kinds
            if value not in pool:
                raise ValueError(f"vocab.json: role {name} names {value!r}, which is not declared")

    def role(self, name):
        return self.roles[name]

    @property
    def closed(self):
        return self.roles["closed_status"]

    def open_statuses(self):
        return [s for s in self.statuses if s != self.closed]

    def field_names(self):
        return list(self.fields)

    def required(self, item):
        """Fields this item must carry, from its kind and its status."""
        need = list(self.kinds.get(item.get("kind"), {}).get("requires", []))
        need += self.statuses.get(item.get("status"), {}).get("requires", [])
        return need

    def heading_rule(self, headings):
        """(kind, status) for a block under these headings (outermost first)."""
        kind = status = None
        for heading in reversed(headings):
            for rule in self.import_rules:
                if not re.search(r"\b" + re.escape(rule["match"]), heading, re.I):
                    continue
                if kind is None and "kind" in rule:
                    kind = rule["kind"]
                if status is None and "status" in rule:
                    status = rule["status"]
        return kind or self.role("default_kind"), status or self.role("default_status")


VOCAB = Vocab()
