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
        rule = {k: v for k, v in data["approval"]["rule"].items() if not k.startswith("_")}
        for key, pool in (("kinds", self.kinds), ("sizes", self.ready_sizes), ("needs", self.fields),
                          ("exclude_works", self.works)):
            bad = [v for v in rule[key] if v not in pool]
            if not rule[key] or bad:
                raise ValueError(f"vocab.json: approval.rule.{key} {rule[key]!r} names {bad or 'nothing'}, not declared (one of {', '.join(pool)})")
        for key in ("id", "source"):
            if not str(rule.get(key) or "").strip():
                raise ValueError(f"vocab.json: approval.rule.{key} is empty")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(rule.get("approved"))):
            raise ValueError("vocab.json: approval.rule.approved is the day Jacob approved the rule, YYYY-MM-DD")
        if not (isinstance(rule.get("exclude_files"), list) and rule["exclude_files"]):
            raise ValueError("vocab.json: approval.rule.exclude_files is a non-empty list of globs")
        self.approval_rule = rule
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
        stray = [ns for ns in data["tags"]["own"] if not ns.startswith(self.service + ".")]
        if stray:
            raise ValueError(f"vocab.json: own tag namespace(s) {stray} are not under the service prefix "
                             f"{self.service}. (PLAN-services.md §3: the shared namespaces are defined once)")
        for ns, spec in self.namespaces.items():
            if "from" in spec and spec["from"] not in self.fields:
                raise ValueError(f"vocab.json: tag namespace {ns} derives from {spec['from']!r}, which is no field")
        rs = data["research"]
        self.research_service = str(rs.get("service") or "").strip()
        if not self.research_service or ":" in self.research_service:
            raise ValueError("vocab.json: research.service is the research service's id prefix, without ':'")
        self.research_id = re.compile(rs["id"])
        rf = data["report_fallback"]
        self.fallback_file = str(rf.get("file") or "")
        self.fallback_heading = str(rf.get("heading") or "").strip()
        if not self.fallback_file or "/" in self.fallback_file or not self.fallback_heading or "\n" in self.fallback_heading:
            raise ValueError("vocab.json: report_fallback names a file in the repo's top folder and a one-line heading")
        st = data["steps"]
        self.step_shell = str(st.get("shell") or "")
        self.step_timeout = st.get("timeout_s")
        if not self.step_shell.startswith("/"):
            raise ValueError("vocab.json: steps.shell is an absolute path to a shell")
        if not (isinstance(self.step_timeout, (int, float)) and not isinstance(self.step_timeout, bool) and self.step_timeout > 0):
            raise ValueError(f"vocab.json: steps.timeout_s is {self.step_timeout!r}, not a positive number of seconds")
        self.import_rules = data["import"]["headings"]
        imp = data["import"]
        self.done_marker = re.compile(imp["done_marker"])
        self.import_approval = re.compile(imp["approval"])
        self.import_waits_on = [{"match": re.compile(r["match"]), "value": r["value"], "plan": r.get("plan")}
                                for r in imp["waits_on"]]
        for r in self.import_waits_on:
            if r["value"].partition(":")[0] not in self.waits_on:
                raise ValueError(f"vocab.json: import.waits_on value {r['value']!r} names no declared waits_on")
        self.import_waits_mention = re.compile(imp["waits_on_mention"])
        self.import_probe = re.compile(imp["probe"])
        self.import_owner = re.compile(imp["report_owner"])
        self.import_report_date = re.compile(imp["report_date"])
        for rx, group in ((self.import_approval, "date"), (self.import_approval, "quote"),
                          (self.import_owner, "repo"), (self.import_report_date, "date")):
            if group not in rx.groupindex:
                raise ValueError(f"vocab.json: import pattern {rx.pattern!r} has no (?P<{group}>...) group")
        skip = imp["skip"]
        if not isinstance(skip["intro"], bool):
            raise ValueError("vocab.json: import.skip.intro is true or false")
        self.import_skip_intro = skip["intro"]
        self.import_heading_only = re.compile(skip["heading_only"])
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
        self.decisions = self._decisions(data["decisions"])
        self.sync_plans = self._sync_plans(data["sync_plans"])
        # A kind a command makes and keeps (`made_by`): add, edit and report refuse it by hand.
        self.made_by = {k: v["made_by"] for k, v in self.kinds.items() if "made_by" in v}
        bad = [k for k, v in self.made_by.items() if not (isinstance(v, str) and v.strip())]
        if bad:
            raise ValueError(f"vocab.json: kinds {bad}: made_by names the command that makes the kind")
        self.detector_kinds = [k for k, v in self.kinds.items() if "detector" in v["requires"]]
        if self.roles["stall_kind"] not in self.detector_kinds or self.roles["lag_kind"] not in self.detector_kinds:
            raise ValueError("vocab.json: roles.stall_kind and roles.lag_kind name kinds that require `detector`")
        self.detectors = self._detectors(data["detectors"])

    SYNC_ACTIONS = ("create", "decide", "list", "skip")
    DETECTOR_KEYS = ("id", "doc", "command", "kind", "waits_on", "cadence_hours")
    DETECTOR_SLOTS = ("{todo}", "{store}", "{root}")
    DETECTOR_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")

    @staticmethod
    def _positive(v, number=False):
        ok = isinstance(v, (int, float) if number else int) and not isinstance(v, bool)
        return ok and v > 0

    def _detectors(self, d):
        """vocab.json `detectors`, every key consumed and checked (todolib/detect.py reads it)."""
        d = {k: v for k, v in d.items() if not k.startswith("_")}
        want = {"cap", "timeout_s", "digest_lines", "evidence_max", "stale_factor", "failed_id", "list"}
        if set(d) != want:
            raise ValueError(f"vocab.json: detectors holds {sorted(d)}, not {sorted(want)}")
        for k in ("cap", "timeout_s", "digest_lines", "evidence_max", "stale_factor"):
            if not self._positive(d[k]):
                raise ValueError(f"vocab.json: detectors.{k} is a positive whole number")
        if not self.DETECTOR_ID.match(str(d["failed_id"])):
            raise ValueError("vocab.json: detectors.failed_id is an id (a letter, then letters, digits, _ . -)")
        why = self.detector_list_problem(d["list"], d["failed_id"])
        if why:
            raise ValueError(f"vocab.json: detectors.list: {why}")
        return d

    def detector_list_problem(self, lst, failed_id):
        """Why a list of detectors is not one todo detect can run, or None."""
        if not isinstance(lst, list):
            return "is not a list"
        seen = set()
        for n, det in enumerate(lst, 1):
            if not (isinstance(det, dict) and set(det) == set(self.DETECTOR_KEYS)):
                return f"detector {n} must hold exactly {', '.join(self.DETECTOR_KEYS)}"
            did = det["id"]
            if not (isinstance(did, str) and self.DETECTOR_ID.match(did)) or did == failed_id or did in seen:
                return (f"detector {n}: id {did!r} is not an id, is the reserved {failed_id!r}, or is used twice")
            seen.add(did)
            cmd = det["command"]
            if not (isinstance(cmd, list) and cmd and all(isinstance(a, str) and a for a in cmd)):
                return f"{did}: command is a non-empty list of arguments"
            slots = {s for a in cmd for s in re.findall(r"\{[^}]*\}", a)} - set(self.DETECTOR_SLOTS)
            if slots:
                return f"{did}: command names {sorted(slots)}; it may name only {', '.join(self.DETECTOR_SLOTS)}"
            if det["kind"] not in self.detector_kinds:
                return f"{did}: kind {det['kind']!r} is not one of {', '.join(self.detector_kinds)}"
            if det["waits_on"] is not None and self.waits_on_problem(det["waits_on"]):
                return f"{did}: {self.waits_on_problem(det['waits_on'])}"
            if not self._positive(det["cadence_hours"], number=True):
                return f"{did}: cadence_hours is a positive number"
            if not (isinstance(det["doc"], str) and det["doc"].strip()):
                return f"{did}: doc says what it finds"
        return None

    def _sync_plans(self, d):
        """vocab.json `sync_plans`, every key consumed and checked (todolib/syncplans.py reads it)."""
        d = {k: v for k, v in d.items() if not k.startswith("_")}
        want = {"track", "untracked", "title_max", "max_listed"}
        if set(d) != want:
            raise ValueError(f"vocab.json: sync_plans holds {sorted(d)}, not {sorted(want)}")
        if not (isinstance(d["track"], dict) and d["track"]):
            raise ValueError("vocab.json: sync_plans.track maps each track kind to an action")
        bad = {k: v for k, v in [*d["track"].items(), ("(untracked)", d["untracked"])] if v not in self.SYNC_ACTIONS}
        if bad:
            raise ValueError(f"vocab.json: sync_plans actions {bad} are not among {', '.join(self.SYNC_ACTIONS)}")
        for k in ("title_max", "max_listed"):
            if not (isinstance(d[k], int) and not isinstance(d[k], bool) and d[k] > 0):
                raise ValueError(f"vocab.json: sync_plans.{k} is a positive whole number")
        return d

    def _decisions(self, d):
        """vocab.json `decisions`, every key consumed and checked (todolib/decisions.py reads it)."""
        d = {k: v for k, v in d.items() if not k.startswith("_")}
        want = {"requires", "pointer", "option_name", "status", "waits_on", "verdicts", "table_prefix",
                "max_listed", "generated_recommend"}
        if set(d) != want:
            raise ValueError(f"vocab.json: decisions holds {sorted(d)}, not {sorted(want)}")
        bad = [f for f in d["requires"] if f not in self.fields]
        if not d["requires"] or bad:
            raise ValueError(f"vocab.json: decisions.requires names {bad or 'nothing'}, not declared fields")
        if d["status"] not in self.statuses or d["status"] == self.roles["closed_status"]:
            raise ValueError(f"vocab.json: decisions.status {d['status']!r} is not an open status")
        if self.waits_on_problem(d["waits_on"]):
            raise ValueError(f"vocab.json: decisions.waits_on: {self.waits_on_problem(d['waits_on'])}")
        out = dict(d, pointer=re.compile(d["pointer"]), option_name=re.compile(d["option_name"]))
        if {"file", "section"} - set(out["pointer"].groupindex):
            raise ValueError("vocab.json: decisions.pointer needs (?P<file>...) and (?P<section>...) groups")
        if set(d["verdicts"]) != {"yes", "no"} or not all(d["verdicts"].values()):
            raise ValueError("vocab.json: decisions.verdicts names the words of yes and of no, each a non-empty list")
        words = [w for ws in d["verdicts"].values() for w in ws]
        if len(words) != len(set(words)) or any(w != w.lower() or out["option_name"].match(w) is None for w in words):
            raise ValueError("vocab.json: decisions.verdicts words are lowercase, distinct, and shaped like an option "
                             "name (so an option can never be named like one)")
        if not re.match(r"^[a-z]{1,8}$", str(d["table_prefix"])):
            raise ValueError("vocab.json: decisions.table_prefix is 1-8 lowercase letters")
        if not (isinstance(d["max_listed"], int) and not isinstance(d["max_listed"], bool) and d["max_listed"] > 0):
            raise ValueError("vocab.json: decisions.max_listed is a positive whole number")
        if d["generated_recommend"] not in d["verdicts"]:
            raise ValueError("vocab.json: decisions.generated_recommend is yes or no")
        return out

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
