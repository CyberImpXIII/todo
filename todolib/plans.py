"""The plan sections items were made from (README "Plan pins"). An item tagged
`plan:PLAN-x.md§n` can pin that section: `todo add/edit --pin-plan` records the
sha256 of the section's text and the day, and `todo stale-plans` lists the open
items whose section has changed since, or is gone, or was never pinned.

The section is read through the setup tool's `setup plans show <file> §<n>`,
never parsed here: what a section is (its heading, where it ends) is that tool's
definition, and a second copy would drift. That command's own `digest` line is of
the whole file (what `plans edit --digest` takes), so a pin hashes the section
text it prints instead: an edit to another section leaves this one's pin fresh.

Every answer is ok, gone or error. An error (no plans CLI, an ambiguous section,
output in a form this module does not know) is never read as fresh or as gone:
`stale-plans` reports it UNCHECKED."""
import hashlib
import re
import subprocess
from pathlib import Path

from .vocab import VOCAB

PLANS_CLI_NAME = ("setup", "setup")  # <dir>/setup/setup: the setup tool, a sibling of this one
SHOW = ("plans", "show")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
SHOW_DIGEST_LINE = re.compile(r"^digest [0-9a-f]{64}\n?$")
NO_SECTION = re.compile(r"^plans show: .*: no section §\S+\n?$")
TIMEOUT = 60

OK, GONE, ERROR = "ok", "gone", "error"


def namespace():
    """The tag namespace whose rule is `plan` (vocab.json tags), e.g. `plan`."""
    found = [ns for ns, spec in VOCAB.namespaces.items() if spec.get("rule") == "plan"]
    if len(found) != 1:
        raise ValueError(f"vocab.json: {len(found)} tag namespaces carry rule plan; one is needed")
    return found[0]


def refs(item):
    """The values of the item's plan tags, in order: `PLAN-x.md§3` or `PLAN-x.md`."""
    head = namespace() + ":"
    return [t[len(head):] for t in (item.get("tags") or []) if t.startswith(head)]


def split(ref):
    """(file, section) of `PLAN-x.md§3`; section is None when the tag names none."""
    file, mark, section = ref.partition("§")
    return file, (section if mark else None)


def shown(ref):
    """How stale-plans shows a ref: `PLAN-x.md §3`."""
    file, section = split(ref)
    return f"{file} §{section}" if section else file


def default_cli(start=None):
    """The setup tool beside this one: <ancestor>/setup/setup for the first ancestor
    of this repo holding it (an ancestor walk, not a fixed `../`, so a copy of the
    repo deeper down -- devtools/mutate.py runs one -- finds it too). None when no
    ancestor holds it."""
    here = Path(start or __file__).resolve().parent.parent
    for d in here.parents:
        p = d.joinpath(*PLANS_CLI_NAME)
        if p.is_file():
            return p
    return None


def resolve_cli(given):
    """(path, None) for the plans CLI to call, or (None, why)."""
    p = Path(given) if given else default_cli()
    if p is None:
        return None, ("no plans CLI: no setup/setup above " + str(Path(__file__).resolve().parent.parent)
                      + " (--plans-cli names one)")
    if not p.is_file():
        return None, f"no plans CLI at {p} (--plans-cli names another)"
    return p, None


def section_digest(text):
    return hashlib.sha256(text).hexdigest()


def show(cli, plans_dir, ref):
    """(OK, digest of the section's text) | (GONE, why) | (ERROR, why) for one
    `PLAN-x.md§n`, read by `<cli> plans show <plans_dir>/<file> §<n>`."""
    file, section = split(ref)
    if section is None:
        return ERROR, f"{ref} names no section (a pin needs PLAN-<name>.md§<n>)"
    path = Path(plans_dir) / file
    if not path.is_file():
        return GONE, f"{file} is not in {plans_dir}"
    try:
        r = subprocess.run([str(cli), *SHOW, str(path), "§" + section], capture_output=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return ERROR, f"{cli} {' '.join(SHOW)} could not run: {e}"
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode == 0 and r.stdout and SHOW_DIGEST_LINE.match(err):
        return OK, section_digest(r.stdout)
    if r.returncode == 1 and not r.stdout and NO_SECTION.match(err):
        return GONE, err.strip().removeprefix("plans show: ")
    first = (err.strip().splitlines() or ["(no stderr)"])[0]
    return ERROR, f"{' '.join(SHOW)} {file} §{section}: exit {r.returncode}, {first}"
