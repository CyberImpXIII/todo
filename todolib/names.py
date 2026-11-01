"""The names file (PLAN-architecture.md §13.1 G4): one record per location, rendered
by the roster's owner from its manifest (its `names` verb) and handed to todo as
`--names FILE` or TODO_NAMES. todo never looks for it: with none handed, a report's
target is judged by the scan alone, as before. With one, a report's target must be
a location's `name` in it, never a path or an old spelling (external audit ra-19.3,
Jacob 2026-10-31: "hand todo the file"; ra-21.1: todo still never enters `.claude`).

The file: {"locations": [{"name", "dir", "store", "remote", "agent"}, ...]}.
Every answer is a Names or a TodoError naming the file: a file that cannot be read
is never read as "no rule", because a guessed target is what G4 exists to refuse."""
import json
import os
from pathlib import Path

from .store import TodoError

ENV = "TODO_NAMES"
CURRENT = None   # the Names the running command was handed, set by cli.main; None when none was
KEYS = ("name", "dir", "store", "remote", "agent")


class Names:
    def __init__(self, path, locations):
        self.path = Path(path)
        self.locations = locations
        self.by_name = {loc["name"]: loc for loc in locations}

    def location(self, name):
        return self.by_name.get(name)

    def target_problem(self, name):
        """Why `name` is no report target under this file, or None."""
        if name in self.by_name:
            return None
        hit = [loc["name"] for loc in self.locations
               if name in (loc.get("dir"), loc.get("store"), loc.get("agent"))
               or (loc.get("remote") or "").split("/")[-1] == name]
        if hit:
            return (f"{name!r} is not a location's name in {self.path}: the location is named {hit[0]!r} "
                    "(one name per location; a path, a store key or a remote is not the name)")
        return f"{name!r} is no location in {self.path} ({len(self.locations)} location(s); the roster owner's `names` verb lists them)"


def load(given):
    """Names from --names FILE, else TODO_NAMES, else None (no file handed)."""
    path = given or os.environ.get(ENV)
    if not path:
        return None
    p = Path(path)
    try:
        doc = json.loads(p.read_text())
    except FileNotFoundError:
        raise TodoError(f"--names {p}: no such file (the roster owner's `names` verb renders it)")
    except (OSError, ValueError) as e:
        raise TodoError(f"--names {p}: cannot be read as JSON ({e})")
    locs = doc.get("locations") if isinstance(doc, dict) else None
    if not isinstance(locs, list) or not locs:
        raise TodoError(f"--names {p}: no `locations` list (the roster owner's `names` verb renders one)")
    for i, loc in enumerate(locs):
        if not isinstance(loc, dict) or set(KEYS) - set(loc) or not isinstance(loc.get("name"), str) or not loc["name"]:
            raise TodoError(f"--names {p}: location #{i} is not {{{', '.join(KEYS)}}} with a name")
    names = [loc["name"] for loc in locs]
    if len(set(names)) != len(names):
        raise TodoError(f"--names {p}: a name appears twice")
    return Names(p, locs)
