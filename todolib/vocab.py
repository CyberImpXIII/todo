"""The vocabulary (vocab.json): kinds, statuses, works, sizes, the brief's two rules,
fields, roles, import rules.

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
        self.sizes = {k: v for k, v in data["sizes"].items() if not k.startswith("_")}
        too_big = [k for k, v in self.sizes.items() if not v["ready"]]
        if len(too_big) != 1:
            raise ValueError(f"vocab.json: exactly one size is `ready: false` (the one split first), not {too_big}")
        self.split_size = too_big[0]
        self.ready_sizes = [k for k, v in self.sizes.items() if v["ready"]]
        self.brief = {k: v for k, v in data["brief"].items() if not k.startswith("_")}
        for rule in ("stop_rule", "iterate_rule"):
            if not str(self.brief.get(rule) or "").strip():
                raise ValueError(f"vocab.json: brief.{rule} is empty; every brief carries it")
        self.fields = {k: v for k, v in data["fields"].items() if not k.startswith("_")}
        self.approval_by = str(data["approval"].get("by") or "").strip()
        if not self.approval_by:
            raise ValueError("vocab.json: approval.by is empty; `todo approve` records who approved")
        self.waits_on = {k: v for k, v in data["waits_on"].items() if not k.startswith("_")}
        self.waits_on_arg = {}
        for name, spec in self.waits_on.items():
            if ":" in name or not str(spec.get("clears") or "").strip():
                raise ValueError(f"vocab.json: waits_on {name!r} needs a name without ':' and a `clears` pointer")
            self.waits_on_arg[name] = re.compile(spec["argument"]) if spec["argument"] is not None else None
        self.resolutions = {k: v for k, v in data["resolutions"].items() if not k.startswith("_")}
        self.roles = data["roles"]
        self.service = data["tags"]["service"]
        self.namespaces = {**data["tags"]["shared"], **data["tags"]["own"]}
        self.shared_namespaces = list(data["tags"]["shared"])
        for ns, spec in self.namespaces.items():
            if "from" in spec and spec["from"] not in self.fields:
                raise ValueError(f"vocab.json: tag namespace {ns} derives from {spec['from']!r}, which is no field")
        self.import_rules = data["import"]["headings"]
        self.done_marker = re.compile(data["import"]["done_marker"])
        b = data["blockers"]
        self.blocker_roots = list(b["roots"])
        self.blocker_bounds = {k: b[k] for k in ("max_roots", "max_ids", "dispatchable_lines")}
        for k, v in self.blocker_bounds.items():
            if not (isinstance(v, int) and not isinstance(v, bool) and v > 0):
                raise ValueError(f"vocab.json: blockers.{k} is {v!r}, not a positive whole number")
        for name, value in self.roles.items():
            pool = (self.statuses if name.endswith("_status") else
                    self.resolutions if name.endswith("_resolution") else
                    self.waits_on if name.endswith("_waits_on") else self.kinds)
            if value not in pool:
                raise ValueError(f"vocab.json: role {name} names {value!r}, which is not declared")
        unnamed = set(self.resolutions) - {v for k, v in self.roles.items() if k.endswith("_resolution")}
        if unnamed:
            raise ValueError(f"vocab.json: resolution(s) {sorted(unnamed)} named by no role: nothing would set or guard them")

    def role(self, name):
        return self.roles[name]

    @property
    def closed(self):
        return self.roles["closed_status"]

    @property
    def jacob_status(self):
        return self.roles["jacob_status"]

    def waits_on_problem(self, value):
        """Why `value` is not a declared waits_on (`<value>` or `<value>:<argument>`), or None."""
        if not isinstance(value, str) or not value.strip():
            return f"waits_on {value!r} is not a string"
        name, sep, arg = value.partition(":")
        if name not in self.waits_on:
            return f"waits_on {value!r}: {name!r} is not one of {', '.join(self.waits_on)}"
        rx = self.waits_on_arg[name]
        if rx is None and sep:
            return f"waits_on {value!r}: {name} takes no argument"
        if rx is not None and not rx.match(arg):
            return f"waits_on {value!r}: {name} takes an argument matching {rx.pattern} ({name}:<argument>)"
        return None

    def waits_on_forms(self):
        """The forms a waits_on takes, for a message: wizard:<argument>, settings, ..."""
        return ", ".join(n + (":<argument>" if self.waits_on_arg[n] else "") for n in self.waits_on)

    def open_statuses(self):
        return [s for s in self.statuses if s != self.closed]

    def field_names(self):
        return list(self.fields)

    def optional_fields(self):
        """Fields an item written before they existed may lack (read as null)."""
        return [name for name, spec in self.fields.items() if spec.get("optional")]

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
