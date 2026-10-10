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

A read that names its record (`show`, `get`, `find`, `refs`, `brief`, `tree ID`,
`history ID`), and `dispatchable`, which reads every store, needs no store of its own. Run from a folder with none, without
`-C` (the workspace root, or a repo not migrated yet), it answers from every
store scanned from there: `--root`, else `TODO_ROOT`, else the folder itself when
it is in no git repo. A write still needs its store, and `-C` naming a folder
without one stays an error rather than borrowing another store's answer.

## Commands

<!-- commands -->
| usage | what it does |
|---|---|
| `todo init --prefix P [--repo NAME]` | start a store: `todo.json`, `todo-history.json`, and `TODO.md` unless one exists (then import it). Ids are `P-1`, `P-2`, ... |
| `todo add TITLE --kind K [--status S] [--evidence E] [--probe P] [--parent ID] [--blocked-by ID ...] [--repo R] [--work W] [--size S] [--files F ...] [--done-when D] [--retire C] [--tags T ...]` | add an open item; refused when its kind or status requires a field it lacks, or when a `--blocked-by` id resolves in no scanned store or history or would make a cycle |
| `todo edit ID [--title T] [--kind K] [--status S] [--evidence E] [--append-evidence E] [--probe P] [--parent ID] [--blocked-by [ID ...]] [--repo R] [--work W] [--size S] [--files F ...] [--done-when D] [--retire C] [--tags [T ...]] [--handoff NOTE]` | change fields of an open item (`""` clears one); never closes it, never touches history. `--blocked-by` with no ids clears the list; ids are checked as for `add`. `--tags` with no tags clears them; tags are checked as `check` does (below). `--append-evidence` adds a line after the evidence inside the store's lock, so no caller reads, changes and rewrites it (not with `--evidence`). `--handoff` records, at a checkpoint, one line (done; next; how to verify) with today's date and the work repo's `HEAD` (below) |
| `todo done ID --resolution R` | close an item: it moves, every field intact, to `todo-history.json` with today's date. Refused for an id already in history. Also finishes a close that was interrupted between the two writes |
| `todo report ID --to REPO [--kind K]` | mark an item reported to REPO and write its counterpart in REPO's store (`parent` pointing back). If REPO already holds an item with that parent, open or closed, it pairs with that one instead of reporting again. With no store for REPO yet, the report stays unpaired (a warning) until it has one |
| `todo list [--kind K] [--status S] [--repo R] [--mine] [--all] [--ready] [--blocked]` | open items, one line each; `--all` or `--repo` across every scanned store. `--ready` (not with `--blocked`) keeps the items whose `blocked_by` ids are all closed (or that have none), `--blocked` the rest |
| `todo show ID` | one item in full, any repo; a closed id is read from history, and says so |
| `todo render [--all] [--history] [--force]` | write `TODO.md` from the store. Refused over a hand edit unless `--force`, which keeps the diff in `todo.json` `hand_edits`. `--history` writes `TODO-HISTORY.md` instead: read-only, gitignored, never checked |
| `todo tree [ID]` | items and their children across repos, closed ones marked |
| `todo check [--all]` | every gate below over this store (`--all`: every scanned store); exit 1 on a FAIL |
| `todo import FILE [--dry-run]` | a hand-written or hand-edited `TODO.md` into items (below) |
| `todo repos` | every store the scan finds, with its counts |
| `todo ready [--repo R] [--work W]` | open items with `repo`, `work` and `done_when` set, size S or M, and every `blocked_by` id closed: ready to hand to whoever does that work. An item ready but for its size is refused by name, below the list: unsized (`todo edit ID --size`), or L (`todo split` it) |
| `todo brief ID` | an item as a work brief: what, why (its evidence), probe, files, done-when, parent, what it is blocked by, its last handoff and the commit it was written at (and `HEAD` when the repo has moved on since), the exact `todo edit --handoff` and `todo done` commands, and the stop rule (below). Exit 1 when it is not ready (a field missing, a status other than open, a `blocked_by` id still open, or its size) |
| `todo history [ID] [--since DATE] [--repo R] [--kind K] [--grep TEXT]` | closed items, newest first, with their resolutions; with no arguments the last ten |
| `todo get ID` | one record as JSON: `{id, closed, tags, record}`, `id` in the form `todo:td-3`, `tags` every tag it holds (derived and set). Exit 1 for an id no scanned store or history holds (dangling), exit 3 (`UNCHECKED`) for a prefix no scanned store holds or another service's id |
| `todo find TAG ... [--open] [--json]` | `todo:<id>  title` of every record, open or closed (`(closed)`), in every scanned store, that holds every tag named; `--open` leaves history out. A tag outside the vocabulary is refused |
| `todo refs ID [--open] [--json]` | the records whose `ref:` names ID: `todo:<id>` (as a parent, a `blocked_by` id, a report's counterpart or a `ref:` tag), or another service's id such as `kb:hooks#sessionstart`. Exit codes as for `get` for a todo id |
| `todo split ID TITLE ... --size SIZE` | one child per title under `parent`, each a checkpoint of its own: SIZE is S or M; it copies the parent's kind, repo, work, files, `blocked_by`, tags and any field its kind requires, and gets its own `done_when` with `todo edit`. The parent becomes L, so `ready` never lists it, and `todo done` on its last open child closes it too |
| `todo reseal --reason R` | accept a store file changed around the CLI (its seal broken), after reading the diff: seals it again and records `{date, via: reseal, files, reason}` in `hand_edits`. The one way to write over a broken seal; refused when every seal matches |
| `todo approve ID --source S [--date D] [--clear]` | record Jacob's approval on an open item: `approved` `{by, date, source}`, `by` from `vocab.json` `approval`, `--date` (default today) no later than today, `--source` one line saying where he gave it. `--clear` removes it, refused while the item is dispatched |
| `todo dispatch ID [--note N] [--clear]` | mark an approved open item handed out: `dispatched` `{date, text}`. Refused on an unapproved item or one already dispatched; says so, but still marks it, when `todo brief` would call it NOT READY. `--clear` when it comes back unfinished, so it is listed again |
| `todo dispatchable [--repo R] [--json]` | what can be dispatched now, across every scanned store (below): the open items Jacob approved, not dispatched, and ready as `todo brief` judges it, each with its `todo:` id, repo, work, size, approval, the brief command and the `dispatch` command that marks it. Then the approved items held back and why, the dispatched ones, and the count of open items with no approval. Exit 3 (`UNCHECKED`) when a store could not be read |
| `todo help` | the commands, one per line: what tools/checks reads to hold `cli.json`'s verbs to this CLI |

`tests/test_docs.py` holds this table equal to the parser, command by command and
flag by flag, and the command list in `PLAN-todo-tool.md` §3 equal to it too
(when the plan is present).

## Items

One item is one JSON object with every field below, unset ones `null`. A field
added after items existed is optional in `vocab.json` (`blocked_by`, `size`, `handoff`, `tags`): an item
written before it may lack the key, which reads as `null`; history is
append-only, so its old entries never gain it.
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

An item's `size` is its estimate (PLAN-small-tasks.md §2): a dispatch is one
checkpoint, so `todo ready` lists only S and M, and an L item is split into
children first (`todo split`). tools/usage reads the same field for its
`usage gate` estimate.

<!-- vocab:sizes -->
| size | meaning |
|---|---|
| `S` | one step: one change, its test, one commit |
| `M` | a few steps, still one checkpoint: one done_when, one commit, one report |
| `L` | more than one checkpoint: `todo split` it into S and M children before anyone starts it |

A usage limit ends a session mid-turn, with no chance to write anything
(PLAN-small-tasks.md §4). So at each checkpoint, next to its commit, the agent
runs `todo edit ID --handoff "done; next; how to verify"`; the item keeps the note,
the date and the work repo's `HEAD` (its `repo` is this store's, or a scanned
store's; otherwise the commit is null, never guessed). `todo brief` prints the
handoff with that commit's subject, and says so when `HEAD` has moved on since, so
the next dispatch resumes there. Every brief also carries the stop rule,
`vocab.json` `brief.stop_rule`, in PLAN-small-tasks.md §2.3's words: "Commit after
each step that passes. If the full check fails twice, stop and report what passed,
what failed and where. Do not start the suite a third time."

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
| `blocked_by` | ids of the items that must close first, in any scanned repo; `todo ready` leaves the item out until every one is in history |
| `repo` | where the work lives: a repo name, never a person or an agent |
| `work` | one of the works |
| `size` | one of the sizes, the estimate `todo ready` and tools/usage read; null until someone sizes it, and an unsized item is never ready |
| `files` | paths the work touches |
| `done_when` | the observable that closes it |
| `handoff` | `{date, text, commit}`: the last checkpoint's note (done; next; how to verify), the day it was written and the work repo's commit then (null when that repo is not found); set by `todo edit ID --handoff`, carried by `todo brief` |
| `approved` | `{by, date, source}`: Jacob's go-ahead, the day he gave it and where; set by `todo approve` only, read by `todo dispatchable` |
| `dispatched` | `{date, text}`: the day it was handed out, and a one-line note that never names who; set and cleared by `todo dispatch` only |
| `retire` | the check that retires an interim rule |
| `tags` | the tags set by hand, `<namespace>:<value>`: `plan:`, `origin:`, `trust:` and `ref:` (below); the rest are derived from the fields and never stored |
| `added` | date added |
| `done` | date closed; null while open |
| `resolution` | how it closed; null while open |
| `imported` | `{sha, section, title_from, sep}`, set by `todo import` |

## Ids and tags

Outside this tool an item's id is `todo:<id>` (`todo:td-3`; PLAN-services.md §3),
and every command that takes an id takes that form too. The store keeps the bare
`td-3`. Every record carries tags, `<namespace>:<value>`, in the namespaces below
(`vocab.json` `tags`). A namespace with a field is derived from that field, so a
tag can never disagree with the item; the others are set by hand with `--tags`.
Every `parent`, `blocked_by` id and report counterpart also gives a
`ref:todo:<id>`, so `todo refs` finds them.

<!-- vocab:tags -->
| namespace | says | from |
|---|---|---|
| `repo` | which repo it concerns | the `repo` field |
| `plan` | which plan section it serves: `PLAN-<name>.md`, optionally `§<section>` | set by hand |
| `kind` | what sort of thing it is | the `kind` field |
| `origin` | who produced it: `jacob`, `model` or `tool` (closed) | set by hand |
| `trust` | whether its text may be read as instructions: `untrusted` (closed) | set by hand |
| `status` | its state in its owner's vocabulary | the `status` field |
| `ref` | another record it points at, by id: `<service>:<id>` | set by hand, and from `parent`, `blocked_by`, `reported_to` |
| `todo.work` | the item's work (this service's own namespace) | the `work` field |

The first seven are a local copy of PLAN-services.md §3's shared table:
`tests/test_tags.py` holds them equal to it, in order, when the plan is present.
The shared vocabulary belongs to the architecture service, which does not exist
yet; once it does, this table is read from there (TODO.md). `get`, `find` and
`refs` are not declared in `services.json`: its schema (tools/checks) allows a
service of `check` or `write` only, and these are reads (TODO.md).

## Dispatch

`todo ready` answers "what is well-formed enough to hand out"; `todo dispatchable`
answers "what may be handed out now" (Jacob, 2026-10-09). It adds two facts this
tool records itself, each with one setter:

- **`approved`**, by `todo approve ID --source "..."`: Jacob's go-ahead, with the
  day and where he gave it. Nothing else counts as approval: not the kind, not a
  plan section, not an `origin:jacob` tag. `todo dispatch` refuses an item without
  it, and `check` fails an `approved` of another shape or approver, or a
  `dispatched` mark on an item with none.
- **`dispatched`**, by `todo dispatch ID`: the item was handed to someone, so it is
  in flight and left out. "In flight" is this mark alone: todo reads no roster and
  no ledger, and the note never names who (items name repos). When the work comes
  back unfinished, `todo dispatch ID --clear` lists it again; when it is finished,
  `todo done` closes it.

An item is listed when it is open (status `open`, not a report), approved, not
dispatched, and `todo brief` would not call it NOT READY (repo, work, done_when,
size S or M, every `blocked_by` id closed: one function, `not_ready_reasons`,
answers both). An approved item failing any of that is listed under "held back"
with the reason; a split item (size L with children) is left to its children,
which carry its approval. Open items with no approval are counted. Its pointer for
a Dispatch line is the `todo:` id: `todo brief todo:<id>` prints the work brief from
any folder. Like the other reads that need no store of their own, it runs from
the workspace root and scans from there (tests/test_dispatch.py).

Items in a hand-kept `TODO.md` are not in any store, so this command cannot see
them until that file is imported (`todo import`).

## The store files

`todo.json` and `todo-history.json` are written by this CLI alone, and three
things hold every other writer off them:

- **`cli.json` declares them** (`store`), with the CLI and its verbs, for
  tools/checks: `accessor` fails a file outside `todolib/` that names them,
  `stores-readonly` fails a store file with a write bit, and a shared hook refuses
  a session's write to them. `tests/test_seal.py` holds `store` to the files the
  CLI writes and `verbs` to its commands.
- **They sit read-only (0444) between writes.** The CLI writes a temp file and
  renames it over the old one, so it never needs the write bit and leaves none.
- **Each carries a seal**, `seal`: a digest of its content (canonical JSON, the
  seal left out) that every CLI write recomputes. A file changed around the CLI
  no longer matches, and `todo check` fails it (gate `seal`), however well-formed
  the change. Every mutating command refuses to write over a broken seal, so the
  next write never launders a hand edit; restore the file from git and make the
  change with the CLI, or read the diff and `todo reseal --reason R`, which
  records it. Removing the seal fails too: a format-2 file with no seal is a hand
  edit, and so is a format-1 file whose last git commit was sealed. A file from
  before seals (`format` 1, never sealed) is a `WARN` until the next CLI write
  seals it.

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

A store need not be in a git repo: the workspace top level is one (PLAN-todo-tool.md
§9 step 1). `todo init` and `todo import TODO.md --dry-run` run there with no `-C`,
the dry run writes nothing and its counts are what the import then does, and the
top-level store and each repo's see each other in the scan (`tests/test_toplevel.py`,
mutants `toplevel-needs-git` and `dry-run-writes`). Outside git, history's
append-only audit cannot run and `check` says so (`INFO`; td-23).

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
| schema | a key or field differs from `vocab.json`, a date is not `YYYY-MM-DD`, a one-line field spans lines, a closed item sits in the store, a `handoff` is not `{date, text, commit}` |
| seal | a store file's seal does not match its content, or was removed: changed around the CLI (above). A file written before seals is a `WARN` until the next CLI write |
| vocab | a kind, status or work is not declared, or a reserved resolution is on an item its setter did not write |
| required | an item lacks a field its kind or status requires (an imported closed item may lack only its date) |
| ids | an id lacks the repo's prefix, appears twice (or in both files), or is not below the counter |
| parents | a parent resolves in no scanned store or history, or the chain loops. A well-formed parent whose prefix no scanned store holds is a `WARN` (unchecked), not a failure: that scan cannot judge it, as with an unpaired report (td-15) |
| sizes | an open L item has no children (`todo split` it); an unsized open item is counted (`INFO`), since it is never ready |
| blockers | a `blocked_by` that is not a non-empty list of ids (`schema`), an id that resolves in no scanned store or history, or a chain of `blocked_by` that leads an open item back to itself (nothing in a cycle can ever be ready). A prefix no scanned store holds is a `WARN`, as for parents |
| tags | a stored tag outside the vocabulary, in a namespace derived from a field, with a value a closed namespace does not hold, or of the wrong form; a `ref:todo:<id>` that resolves nowhere (dangling). A `ref:` to another service's record is counted (`INFO`), unchecked until a registry resolves it; a `ref:todo:` prefix no scanned store holds is a `WARN`, as for parents |
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
repo's own store, tools/checks' `checks run .` (below), and the mutants (`devtools/mutate.py`: each gate broken once
in a throwaway copy, which must turn its test red).

The `hooks` gate reads each hook test's exit code as a gate: 0 pass, 3 UNCHECKED
(the test could not run here, e.g. no site-scrapers above a lone clone; named with
its reason), anything else FAIL. An UNCHECKED test makes the gate exit 3, never 0;
a FAIL anywhere makes it 1. `./dev.sh check` exits 1 if any gate failed, else 3 if
any was UNCHECKED, and its summary counts the two apart (`tests/test_hooks_gate.py`,
mutants `hooks-unchecked-*`, `check-unchecked-is-green` and `check-json-unchecked-ok`).

`./dev.sh check [--json] [GATE ...]` runs only the named gates, in the order
given; `--json` prints `{"ok": bool, "gates": {gate: bool}}` and nothing else
(an UNCHECKED gate is `false` there; the exit code, 3, tells it from a FAIL).
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

The `checks` gate (td-12) runs `checks run . --json --names <roster_names from
devtools/audit.json>` with the sibling repo's CLI (`../checks/checks`, resolved
once to an absolute path and exported, so copies reach it; `CHECKS_CLI` names
another). `devtools/checks_gate.py` judges the report: red on any fail or
error, on an exit code that disagrees with the report, and when `no-roster` did
not run or ran without the names (UNCHECKED, which `checks` itself counts as
green). No CLI is red, never a skip. The names are this repo's own copy, never
the roster, so a stale copy stays td-4's problem. `tests/test_checks_gate.py`
runs the real CLI in a throwaway workspace with a planted roster name; its
mutants (`checks-gate-*`) inherit `CHECKS_CLI` from `./dev.sh`, so run them
through `./dev.sh mutants`, not `devtools/mutate.py` alone.
