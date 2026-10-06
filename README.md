# todo

Structured TODO items per repo. Each repo keeps its open items in `todo.json` and
every closed item in `todo-history.json`, both committed with the repo; `TODO.md`
is **rendered** from `todo.json`, read-only, and the CLI is the only way in.
Python 3 standard library only.

Why: a hand-kept `TODO.md` cannot be checked. A suspicion without its probe, a
report whose owner never heard of it, a "done" with no record of how: each looked
fine as prose. Here each of those is a field, and `todo check` fails when one is
missing or points nowhere.

## Use

```
./todo -C ../some-repo init --prefix sr        # once per repo: todo.json, todo-history.json, TODO.md
./todo -C ../some-repo import TODO.md          # a hand-written TODO.md into items (re-runnable)
./todo add "parser drops tabs" --kind bug --evidence "ran X, saw Y" --work code --done-when "suite passes"
./todo report sr-4 --to other-repo             # marks it reported; writes the counterpart in other-repo's store
./todo done sr-4 --resolution "fixed in 1a2b3c"  # moves it to todo-history.json
./todo check                                   # every gate; non-zero on a failure
```

Every command acts on the repo holding the working directory, or on the one
`-C DIR` names (a relative file argument is then read from DIR, as with `git -C`).
`--root DIR` sets where other repos' stores are looked for (below); without it,
the environment variable `TODO_ROOT` does.

## Commands

<!-- commands -->
| usage | what it does |
|---|---|
| `todo init --prefix P [--repo NAME]` | start a store: `todo.json`, `todo-history.json`, and `TODO.md` unless one exists (then import it). Ids are `P-1`, `P-2`, ... |
| `todo add TITLE --kind K [--status S] [--evidence E] [--probe P] [--parent ID] [--repo R] [--work W] [--files F ...] [--done-when D] [--retire C]` | add an open item; refused when its kind or status requires a field it lacks |
| `todo edit ID [--title T] [--kind K] [--status S] [--evidence E] [--append-evidence E] [--probe P] [--parent ID] [--repo R] [--work W] [--files F ...] [--done-when D] [--retire C]` | change fields of an open item (`""` clears one); never closes it, never touches history. `--append-evidence` adds a line after the evidence inside the store's lock, so no caller reads, changes and rewrites it (not with `--evidence`) |
| `todo done ID --resolution R` | close an item: it moves, every field intact, to `todo-history.json` with today's date. Refused for an id already in history. Also finishes a close that was interrupted between the two writes |
| `todo report ID --to REPO [--kind K]` | mark an item reported to REPO and write its counterpart in REPO's store (`parent` pointing back). If REPO already holds an item with that parent, open or closed, it pairs with that one instead of reporting again. With no store for REPO yet, the report stays unpaired (a warning) until it has one |
| `todo list [--kind K] [--status S] [--repo R] [--mine] [--all]` | open items, one line each; `--all` or `--repo` across every scanned store |
| `todo show ID` | one item in full, any repo; a closed id is read from history, and says so |
| `todo render [--all] [--history] [--force]` | write `TODO.md` from the store. Refused over a hand edit unless `--force`, which keeps the diff in `todo.json` `hand_edits`. `--history` writes `TODO-HISTORY.md` instead: read-only, gitignored, never checked |
| `todo tree [ID]` | items and their children across repos, closed ones marked |
| `todo check [--all]` | every gate below over this store (`--all`: every scanned store); exit 1 on a FAIL |
| `todo import FILE [--dry-run]` | a hand-written or hand-edited `TODO.md` into items (below) |
| `todo repos` | every store the scan finds, with its counts |
| `todo ready [--repo R] [--work W]` | open items with `repo`, `work` and `done_when` set: ready to hand to whoever does that work |
| `todo brief ID` | an item as a work brief: what, why (its evidence), probe, files, done-when, parent, and the exact `todo done` command that closes it. Exit 1 when it is not ready |
| `todo history [ID] [--since DATE] [--repo R] [--kind K] [--grep TEXT]` | closed items, newest first, with their resolutions; with no arguments the last ten |

`tests/test_docs.py` holds this table equal to the parser, command by command and
flag by flag, and the command list in `PLAN-todo-tool.md` §3 equal to it too
(when the plan is present).

## Items

One item is one JSON object with every field below, unset ones `null`.
`vocab.json` is the one source for kinds, statuses, works, reserved resolutions and fields: the parser,
the renderer, the importer, the checks and these tables all follow it, and
`tests/test_vocab.py` fails when any of them disagree, in either direction.

<!-- vocab:kinds -->
| kind | meaning | `TODO.md` section | requires |
|---|---|---|---|
| `bug` | a bug of this repo's own, including one you caused and worked around | Own bugs | |
| `decision` | an open decision, with what it hinges on | Open decisions | |
| `suspicion` | an unconfirmed suspicion, with the probe that would settle it | Unconfirmed suspicions | `probe` |
| `report` | a problem reported to another repo's owner; its counterpart lives in their store | Reported to other owners | `reported_to` (set by `todo report`) |
| `temp` | an interim rule, with the check that retires it | Interim rules | `retire` |
| `note` | anything else worth keeping; the import default | Notes | |

<!-- vocab:statuses -->
| status | meaning | requires |
|---|---|---|
| `open` | workable now (the default; not shown in the render) | |
| `waiting-jacob` | needs Jacob's answer before anyone can move it | |
| `blocked` | waits on something other than Jacob; the evidence says what | |
| `done` | closed; the item lives in `todo-history.json` from then on | `done`, `resolution` |

<!-- vocab:works -->
| work | meaning |
|---|---|
| `code` | a change to the tool's own code |
| `test` | a test or a fixture |
| `audit` | an audit or a check over the repo |
| `tooling` | helpers, dev.sh subcommands, scripts around the tool |
| `docs` | README, CLAUDE.md, comments |
| `decision` | nothing to build until someone decides |
| `research` | finding something out (reading, searching, comparing) before anything is built, filed or sent |
| `labour` | work done by hand outside any code: driving, filing, sorting, a scan run once |
| `outreach` | contacting a person or an organisation: a proposal, an appeal, a message (sending needs Jacob's yes first) |

A resolution is free text written by `todo done`, except the values below, which
each have one setter and are refused everywhere else:

<!-- vocab:resolutions -->
| resolution | meaning |
|---|---|
| `done-deprecated` | an imported closed bullet (DONE marker or Resolved heading) that carried no resolution: set by `todo import` only, refused by `todo done`, and a FAIL (`vocab`) in check on an item that was not imported |

<!-- vocab:fields -->
| field | meaning |
|---|---|
| `id` | repo prefix + counter, stable, never reused (`todo:td-3` points at it) |
| `title` | one line, no `**` |
| `kind` | one of the kinds |
| `status` | one of the statuses |
| `evidence` | what you ran, what you saw, what you concluded; may span lines |
| `probe` | the run that would settle a suspicion |
| `reported_to` | `{repo, date, their_id}`: whom it was reported to, and the counterpart's id there |
| `parent` | any item's id, in any scanned repo, open or closed |
| `repo` | where the work lives: a repo name, never a person or an agent |
| `work` | one of the works |
| `files` | paths the work touches |
| `done_when` | the observable that closes it |
| `retire` | the check that retires an interim rule |
| `added` | date added |
| `done` | date closed; null while open |
| `resolution` | how it closed; null while open |
| `imported` | `{sha, section, title_from, sep}`, set by `todo import` |

## The rendered file

`TODO.md` is a pure function of `todo.json`: a header line, the repo's name, then
one section per kind in the order above (the first four always, even when empty).
An item renders as

```
- **td-3 · Title**
  evidence, verbatim, two spaces in
  · probe: ...
  · added: 2026-10-04
```

It is written read-only. A hand edit is not lost: `todo check` fails on it,
every mutating command refuses to overwrite it, `todo import TODO.md` takes the
new bullets in as items (and refuses if a rendered item itself was changed), and
`todo render --force` keeps the diff in `todo.json` before rewriting. The first
week after a repo's first import, a hand edit is a counted warning, not a failure
(`render_gate_from` in `todo.json`).

The header carries a **seal**: a digest of the file with the seal left out. A
file whose seal matches is exactly what some render wrote, so when it differs
from today's render it is a **stale render**, not a hand edit: the render format
changed (a new version of this tool), or `todo.json` changed without a
re-render (a merge, say). `check` fails it as stale, `todo render` (no
`--force`) and every mutating command rewrite it, and nothing goes into
`hand_edits`, since nothing was typed. So a format change turns other repos'
checks red with that message, and `todo render --all` clears every stale store
at once while still refusing hand-edited ones. An edit anywhere, the header and
the seal included, breaks the seal and reads as a hand edit. A file from before
seals reads as stale when it equals today's render without its seal, and as a
hand edit otherwise (td-10, `tests/test_render.py`).

## History

Closed items leave `todo.json` and are appended to `todo-history.json`, so
`TODO.md` stays trim and nothing is lost by closing:

- `todo done` moves the item in one locked write: history first, then the store,
  so an interruption leaves the id in both files (which `check` names and
  `todo done ID` finishes), never in neither.
- History is **append-only**: no command edits or removes an entry, and `check`
  compares the file with every committed version of it (`git log`), failing when
  an entry was removed or changed, committed or not.
- `todo history`, `todo show` and `todo tree` read it; `todo check` reads it to
  pair a report whose counterpart the owner already closed (an `INFO` line saying
  so, so it is closed here rather than reported again).
- `todo import` sends a bullet whose text starts `DONE 2026-10-03` (bold or
  struck-through markers allowed) to history with that date; a bullet under a
  "Resolved" heading goes there with no date. A bullet carries no resolution, so
  every imported closed item gets the resolution `done-deprecated` (Jacob, td-1),
  shown as such by `todo history`, `show` and `render --history`; its evidence
  holds the bullet text. A closed item without a resolution is a FAIL wherever it
  came from (PLAN §5). An imported one may still lack a date; `check` counts those
  (`INFO`).

## Import

`todo import FILE` turns a hand-written `TODO.md` into items without dropping a
word: one top-level bullet or paragraph is one item. Kind and status come from
the headings above it (`vocab.json` `import`: "Needs Jacob" or "Waiting on Jacob"
→ decision waiting on Jacob, "Unconfirmed" → suspicion, "Reported" → report,
"Bug" → bug, "Resolved" → done; `note` otherwise). A bold lead becomes the title
and the rest the evidence; otherwise the title is the first sentence and the
evidence the whole text. Each item records its block's sha, so re-running the
import adds nothing. Items whose kind requires a field the bullet cannot supply (a
suspicion's probe) are imported anyway and named by `check` until filled with
`todo edit`.

`tests/test_import.py` proves it lossless on three real `TODO.md` files: every
word comes back from the render, and every block comes back whole.

## Across repos

Nothing is configured. The scan root is `--root DIR`; else `TODO_ROOT`; else, for a store outside
any git repo, its own folder; else the nearest folder above the repo that is in
no git repo and holds a `todo.json` or a `CLAUDE.md`; else the repo's parent.
Under it, every git repo with a `todo.json`, three levels down, is a store. Hidden
folders, `node_modules`, `venv` and test fixtures are never entered. A prefix or
a repo name used twice is a failure.

So a report to a hidden folder **never pairs**, and that is by design: the
delegation layer (`.claude`) is one, and todo never reads it (PLAN-todo-tool.md
§8 decision 4). `todo report ID --to .claude` still records whom it went to; the
command, `check` (an `INFO` line, not the "not migrated yet" warning) and the
render (`(relayed by hand; never pairs)`) all say it never pairs. Relay it by
hand and close it by its `done_when`. No store may take a hidden repo name, so
"never" holds (`tests/test_reports.py`).

## Checks

`todo check` prints one line per finding and an `ok` line per clean gate, so a
gate that stopped running shows as a missing line:

| gate | fails when |
|---|---|
| schema | a key or field differs from `vocab.json`, a date is not `YYYY-MM-DD`, a one-line field spans lines, a closed item sits in the store |
| vocab | a kind, status or work is not declared, or a reserved resolution is on an item its setter did not write |
| required | an item lacks a field its kind or status requires (an imported closed item may lack only its date) |
| ids | an id lacks the repo's prefix, appears twice (or in both files), or is not below the counter |
| parents | a parent resolves in no scanned store or history, or the chain loops. A well-formed parent whose prefix no scanned store holds is a `WARN` (unchecked), not a failure: that scan cannot judge it, as with an unpaired report (td-15) |
| reports | a report's owner has a store but no counterpart, or the counterpart's parent points elsewhere |
| workspace | two stores share a prefix or a repo name |
| render | `TODO.md` is not the render of `todo.json`: missing, stale (an unedited render of another store or format), hand-edited or hand-written |
| history | the file is missing or malformed, or an entry was removed or changed since a commit |

## Development

`./dev.sh check` is the one pre-commit command: the unit tests, the hook copies,
the files the tool needs, the direction audit (`devtools/audit.py`: no file here
reads the delegation layer's files or names a roster agent; the shared copies
installed in `.claude/hooks/` and its sibling `lib/` are skipped, being the hooks
tool's files gated by its `hooks copies`, td-16), `todo check` on this
repo's own store, and the mutants (`devtools/mutate.py`: each gate broken once
in a throwaway copy, which must turn its test red).

`./dev.sh check [--json] [GATE ...]` runs only the named gates, in the order
given; `--json` prints `{"ok": bool, "gates": {gate: bool}}` and nothing else.
`tests/test_dev.py` holds that contract on the cheap gates. A check run inside
another check refuses the `test` and `mutants` gates, since either would run that
test again without end; the test of that guard runs in a copy whose tests are one
stub and whose mutants are none, so a broken guard goes red instead of recursing
(mutant `check-nesting-unguarded`). The `self` gate's mutant plants a bad store
and runs `./dev.sh self` with `TODO_ROOT=.`: `TODO_ROOT` is the scan root when
`--root` is not given, and keeps a copy under `.mutants/` from scanning the
workspace and colliding with this repo's own prefix. Under that narrow root an
item that arrived by `todo report` from another repo has its parent outside the
scan, which the `parents` gate reports as unchecked rather than red.

`checks.json` is read by tools/checks (`checks run .`): its `no-roster` check
skips `devtools/audit.json` and `devtools/mutants.json`, which hold the direction
audit's own terms and planted violations. `tests/test_audit.py` holds every
exclusion there to a file that exists and that `devtools/audit.py` skips too, so
`checks.json` never widens the exemptions beyond the ones `audit.json` documents.
