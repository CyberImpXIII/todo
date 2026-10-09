"""Ids and tags (PLAN-services.md §3; PLAN-todo-tool.md §9 step 4).

Outside this tool an item's id is `todo:<id>` (todo:td-3). Its tags are
`<namespace>:<value>` in the namespaces vocab.json `tags` declares. Most are
derived from the item's fields, so they cannot disagree with them: `repo:`,
`kind:`, `status:`, `todo.work:`, and a `ref:todo:<id>` for its parent, its
blocked_by ids and its report's counterpart. The rest (`plan:`, `origin:`,
`trust:`, a `ref:` to any other record) are set by hand in the `tags` field.

One function, `problem()`, judges a tag, so `add`/`edit`, `find` and `check`
cannot disagree about what a tag may be.
"""
import re

from .store import ID_RE
from .vocab import VOCAB

TAG_RE = re.compile(r"^([a-z][a-z0-9.]*):(\S+)$")
PLAN_RE = re.compile(r"^PLAN-[A-Za-z0-9._-]+\.md(§[0-9A-Za-z.-]+)?$")
# A global id: a service prefix, then that service's own id (which may hold ':', '/', '#').
GLOBAL_RE = re.compile(r"^([a-z][a-z0-9.-]*):(\S+)$")
PREFIX = VOCAB.service + ":"


def local_id(text):
    """td-3 for todo:td-3 or td-3; any other text unchanged (a foreign id stays foreign)."""
    if text and text.startswith(PREFIX):
        return text[len(PREFIX):]
    return text


def global_id(local):
    return PREFIX + local


def derived(item, store_repo=None):
    """The tags an item's fields give it, in namespace order."""
    out = []
    for ns, spec in VOCAB.namespaces.items():
        field = spec.get("from")
        if not field:
            continue
        value = item.get(field) or (store_repo if field == "repo" else None)
        if value:
            out.append(f"{ns}:{value}")
    refs = [item.get("parent")] + list(item.get("blocked_by") or [])
    refs.append((item.get("reported_to") or {}).get("their_id"))
    out += [f"ref:{global_id(r)}" for r in dict.fromkeys(r for r in refs if r)]
    return out


def all_tags(item, store_repo=None):
    return list(dict.fromkeys(derived(item, store_repo) + list(item.get("tags") or [])))


def problem(tag, stored=False):
    """Why `tag` is not a tag of this vocabulary, or None. With stored=True, also
    refuse a namespace that is derived from a field (it would be a second copy)."""
    m = TAG_RE.match(tag or "")
    if not m:
        return f"{tag!r} is not <namespace>:<value>"
    ns, value = m.groups()
    spec = VOCAB.namespaces.get(ns)
    if spec is None:
        return f"{ns}: is no namespace here (shared: {', '.join(VOCAB.shared_namespaces)}; own: " + \
               ", ".join(n for n in VOCAB.namespaces if n not in VOCAB.shared_namespaces) + ")"
    if stored and "from" in spec:
        return f"{ns}: is derived from the item's {spec['from']} field; set the field, not a tag"
    if "values" in spec and value not in spec["values"]:
        return f"{ns}: is closed to {', '.join(spec['values'])}; {value!r} is not one"
    if spec.get("rule") == "plan" and not PLAN_RE.match(value):
        return f"plan:{value} is not PLAN-<name>.md or PLAN-<name>.md§<section>"
    if spec.get("rule") == "ref" and not GLOBAL_RE.match(value):
        return f"ref:{value} is not <service>:<id>"
    return None


def ref_target(tag):
    """The local id a `ref:todo:<id>` tag names, or None for any other tag."""
    if tag.startswith("ref:" + PREFIX):
        return tag[len("ref:" + PREFIX):]
    return None


def is_foreign_ref(tag):
    return tag.startswith("ref:") and not tag.startswith("ref:" + PREFIX)


def well_formed_local(text):
    return bool(ID_RE.match(text or ""))
