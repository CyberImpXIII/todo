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

`--repo R` on `list`, `ready`, `dispatchable`, `blockers` and `stale-plans` names a
repo the scan knows: a readable store's own, or one an open or closed item names.
Any other is refused (exit 1) with the known repos listed, never answered "0
items"; with a store unreadable it is `UNCHECKED` (exit 3), since that store may
hold it (tests/test_repo_filter.py). `history --repo` names a store.

## Commands

<!-- commands -->
| usage | what it does |
|---|---|
| `todo init --prefix P [--repo NAME]` | start a store: `todo.json`, `todo-history.json`, and `TODO.md` unless one exists (then import it). Ids are `P-1`, `P-2`, ... |
| `todo add TITLE --kind K [--status S] [--evidence E] [--probe P] [--parent ID] [--blocked-by ID ...] [--waits-on W] [--repo R] [--work W] [--size S] [--files F ...] [--research RS_ID ...] [--done-when D] [--done-check C] [--retire C] [--tags T ...] [--pointer 'FILE §n'] [--hinges-on H] [--recommend A] [--option NAME=TEXT ...] [--reported-to REPO] [--pin-plan] [--plans-dir D] [--plans-cli P]` | add an open item; a `decision` needs `--pointer` (a plan section the plans CLI reads), `--hinges-on` and `--recommend` (yes, no or an `--option`'s name), is added `waiting-jacob` on `approval`, and no other kind takes those flags (Decisions, below); refused when its kind or status requires a field it lacks, or when a `--blocked-by` id resolves in no scanned store or history or would make a cycle. A `waiting-jacob` item needs `--waits-on` (below), and only it may carry one. An open report needs `--reported-to REPO`, its owner (no `:THEIR_ID`: a counterpart is paired later by `edit` or `todo report`); it writes no other store. `--pin-plan` records each `plan:FILE§n` tag's section as it reads now (Plan pins, below), and refuses the item when one cannot be read |
| `todo edit ID [--title T] [--kind K] [--status S] [--evidence E] [--append-evidence E] [--probe P] [--parent ID] [--blocked-by [ID ...]] [--waits-on W] [--repo R] [--work W] [--size S] [--files F ...] [--research RS_ID ...] [--done-when D] [--done-check C] [--retire C] [--tags [T ...]] [--pointer 'FILE §n'] [--hinges-on H] [--recommend A] [--option NAME=TEXT ...] [--handoff NOTE] [--reported-to REPO[:THEIR_ID]] [--pin-plan] [--plans-dir D] [--plans-cli P]` | change fields of an open item (`""` clears one; `--option` replaces a decision's options, `--option ''` clears them, and a changed pointer is read again); never closes it, never touches history. `--blocked-by` with no ids clears the list; ids are checked as for `add`. Leaving `waiting-jacob` clears `waits_on` and says so (an explicit value with another status is refused), and entering it needs a value; an item written before `waits_on` existed still takes other edits without one. `--tags` with no tags clears them; tags are checked as `check` does (below). `--append-evidence` adds a line after the evidence inside the store's lock, so no caller reads, changes and rewrites it (not with `--evidence`). `--handoff` records, at a checkpoint, one line (done; next; how to verify) with today's date and the work repo's `HEAD` (below). `--pin-plan` pins (again) every `plan:FILE§n` section as it reads today; a tag taken off with `--tags` takes its pin with it. `--reported-to` sets a report's owner and writes no other store (`todo report` does): `THEIR_ID` only when that store holds it with `parent` ID, a counterpart it holds pairs without one, and the date stays while the repo does |
| `todo done ID [--resolution R] [--as rejected --reason R]` | close an item, with exactly one of `--resolution` and `--as`: it moves, every field intact, to `todo-history.json` with today's date. Refused for an id already in history. Also finishes a close that was interrupted between the two writes. `--as rejected` closes a decision Jacob said no to, and puts every open item it blocks, in any scanned store, back to `waiting-jacob` on `decision:<its pointer>` with the reason in its evidence (Decisions, below) |
| `todo report ID --to REPO [--kind K]` | mark an item reported to REPO and write its counterpart in REPO's store (`parent` pointing back). If REPO already holds an item with that parent, open or closed, it pairs with that one instead of reporting again. With no store for REPO yet, the report stays unpaired (a warning) until it has one; if the scan finds exactly one git repo named REPO, the report is also filed in its hand-written `TODO.md`: one bullet marked `todo:ID` under the heading `report_fallback.heading` (vocab.json), written once however often it is re-run, and recorded in the item's evidence (PLAN-architecture.md §11 S4). That file is left uncommitted in REPO for its owner to commit; two repos of that name, or none, get nothing |
| `todo list [--kind K] [--status S] [--repo R] [--mine] [--all] [--ready] [--blocked] [--cites C]` | open items, one line each; `--all` or `--repo` across every scanned store. `--ready` (not with `--blocked`) keeps the items whose `blocked_by` ids are all closed (or that have none), `--blocked` the rest. `--cites "FILE §n"` keeps, across every scanned store, the items citing that plan section or one inside it (§3 holds §3.1): by a `plan:` tag, a `plan-step`'s `plan_step`, or a decision's `pointer`; `--cites FILE` any section of it |
| `todo show ID` | one item in full, any repo; a closed id is read from history, and says so |
| `todo render [--all] [--history] [--force]` | write `TODO.md` from the store. Refused over a hand edit unless `--force`, which keeps the diff in `todo.json` `hand_edits`. `--history` writes `TODO-HISTORY.md` instead: read-only, gitignored, never checked |
| `todo tree [ID]` | items and their children across repos, closed ones marked |
| `todo check [--all] [--json]` | every gate below over this store (`--all`: every scanned store); exit 1 on a FAIL. `--json` prints one document instead, `{ok, failed, warnings, stores}`, each store `{repo, dir, open_items, closed_items, ok, failed, warnings, gates, findings}`: `gates` names every gate with its worst level (`ok`, `WARN`, `FAIL`), `findings` each line as `{level, gate, where, message}`; same exit code |
| `todo import FILE [--dry-run] [--waits-on VALUE] [--plans-dir D] [--plans-cli P]` | a hand-written or hand-edited `TODO.md` into items (below). It prints the blocks it read as no item and what a rule could not read; `--waits-on` is the `waits_on` of each `waiting-jacob` item whose text names none, and without it a real import with such an item writes nothing. `--plans-dir`/`--plans-cli` read a `PLAN` pointer as `--pin-plan` does |
| `todo repos [--status] [--json]` | every store the scan finds, with its counts. `--status`: every git repo under the root, with a store or not, sorted by path: its open items (null with no store), last commit (short sha, date, subject; null with none), uncommitted files (a count and the first ten), and `whose`, always null (who left them is the stamp ledger's to say, which todo never reads); `--json` gives `{root, repos}`. Needs no store of its own |
| `todo ready [--repo R] [--work W]` | open items with `repo`, `work` and `done_when` set, size S or M, and every `blocked_by` id closed: ready to hand to whoever does that work. One already handed out stays listed, flagged `[dispatched DATE]` before its title (`todo dispatchable` leaves it out). An item ready but for its size is refused by name, below the list: unsized (`todo edit ID --size`), or L (`todo split` it) |
| `todo brief ID` | an item as a work brief: what, why (its evidence), probe, files, done-when, parent, what it is blocked by, its last handoff and the commit it was written at (and `HEAD` when the repo has moved on since), the exact `todo edit --handoff` and `todo done` commands, the iterate rule and the stop rule (below). With no `done_when` it writes no brief at all: exit 1, nothing on stdout, and a message naming the item and the field. Exit 1 also when it is not ready otherwise (a field missing, a status other than open, a `blocked_by` id still open, or its size), the brief printed and marked NOT READY |
| `todo history [ID] [--since DATE] [--repo R] [--kind K] [--grep TEXT]` | closed items, newest first, with their resolutions; with no arguments the last ten |
| `todo get ID` | one record as JSON: `{id, closed, tags, record}`, `id` in the form `todo:td-3`, `tags` every tag it holds (derived and set). Exit 1 for an id no scanned store or history holds (dangling), exit 3 (`UNCHECKED`) for a prefix no scanned store holds or another service's id |
| `todo find TAG ... [--open] [--json]` | `todo:<id>  title` of every record, open or closed (`(closed)`), in every scanned store, that holds every tag named; `--open` leaves history out. A tag outside the vocabulary is refused |
| `todo refs ID [--open] [--json]` | the records whose `ref:` names ID: `todo:<id>` (as a parent, a `blocked_by` id, a report's counterpart or a `ref:` tag), or another service's id such as `kb:hooks#sessionstart`. Exit codes as for `get` for a todo id |
| `todo split ID TITLE ... --size SIZE` | one child per title under `parent`, each a checkpoint of its own: SIZE is S or M; it copies the parent's kind, repo, work, files, `blocked_by`, tags and any field its kind requires, and gets its own `done_when` with `todo edit`. The parent becomes L, so `ready` never lists it, and `todo done` on its last open child closes it too |
| `todo reseal --reason R` | accept a store file changed around the CLI (its seal broken), after reading the diff: seals it again and records `{date, via: reseal, files, reason}` in `hand_edits`. The one way to write over a broken seal; refused when every seal matches |
| `todo approve ID --source S [--date D] [--option NAME] [--clear]` | record Jacob's approval on an open item: `approved` `{by, date, source}`, `by` from `vocab.json` `approval`, `--date` (default today) no later than today, `--source` one line saying where he gave it. `--clear` removes it, refused while the item is dispatched. On a decision the approval is its answer: it closes `accepted`, or `option-chosen` on `--option NAME` (a plain yes to a decision recommending an option chooses that one), and what it blocked is free |
| `todo dispatch ID [--note N] [--clear]` | mark an approved open item handed out: `dispatched` `{date, text}`; an item approved by rule TD-B1 (Approval by rule, below) gets the rule's `approved` too. Refused on an item neither Jacob nor the rule approves, naming the rule's misses, or one already dispatched; says so, but still marks it, when `todo brief` would call it NOT READY. `--clear` when it comes back unfinished, so it is listed again |
| `todo dispatchable [--repo R] [--json]` | what can be dispatched now, across every scanned store (below): the open items Jacob approved, not dispatched, and ready as `todo brief` judges it, each with its `todo:` id, repo, work, size, approval, the brief command and the `dispatch` command that marks it; then, under their own heading (`by_rule` in `--json`), the ones approved by rule TD-B1 and not by him. Then the approved items held back and why, the dispatched ones, and the count of open items with no approval; with nothing dispatchable, the top roots of `todo blockers` (below) in place of that count. Exit 3 (`UNCHECKED`) when a store could not be read |
| `todo blockers [--repo R] [--json]` | every open item, across every scanned store, that is not dispatchable, grouped by its root blocker (Blockers, below): one line per root, most items freed first, with what clears it, the count and the first ids; bounded, and `--json` gives every root and id. Exit 3 (`UNCHECKED`) when a store could not be read |
| `todo stale-plans [--repo R] [--plans-dir D] [--plans-cli P] [--json]` | the open items, across every scanned store, whose plan section is not what they were made from (Plan pins, below): `changed`, `section gone`, or `never pinned` (a `plan:` tag with no pin, or one naming no section), each with its `todo:` id, repo, `FILE §n` and the day it last matched. Exit 3 (`UNCHECKED`) when a section could not be read (no plans CLI, an ambiguous section) or a store could not be read: such a section is never counted fresh |
| `todo steps [--run] [--findings] [--json]` | this store's open `jacob-step` items, numbered, each with its `done_check` (Jacob's steps, below). `--run` runs every check in the store's folder first, then closes each step whose check exited 0 (resolution `done-checked`); a step whose check exited otherwise stays open with the exit and the start of its output; a check that timed out or could not start is `UNCHECKED` (exit 3) after the rest are closed. `--findings` is the S7 detector's command (Detectors, below): every scanned store's open steps whose `done_check` exits 0, as a JSON list of findings; with `--run` it closes them first, store by store, and lists only one it could not close (its `TODO.md` hand-edited) |
| `todo decisions [--from TABLE] [--json]` | the open, complete decisions of every scanned store as a `## Decisions` table, `\| # \| decision \| hinges on \| recommend \|`, numbered 1..n, the one freeing most items first; recorded in this store as table `dt-N` (the same rows as an earlier table give its id). `--from dt-N` tables only that table's rows still open, recording which row each supersedes. Incomplete decisions are named under it, never tabled. Exit 3 (`UNCHECKED`) when a store could not be read |
| `todo answer REPLY [--table TABLE]` | apply Jacob's reply to a decisions table, `"1) yes 2) no 3) b 4) <words>"`, read against the table named (`dt-N:` leading the reply, or `--table`), else the latest: a yes approves, a no rejects, an option's name chooses it; any other answer is kept in `jacob_words`, status unchanged. Refused whole, nothing applied, on a row the table lacks, a row named twice, or a row whose decision is closed |
| `todo sync-plans [FILE ...] [--dry-run] [--json] [--plans-dir D] [--plans-cli P]` | make and keep the `plan-step` items of each plan's steps (Plan steps, below): `new`, `new-decision`, `updated`, `renumbered`, `stale`, `flagged` (dispatched, so unchanged), `gone`, `listed` (a step it gives no item). No FILE reads every `PLAN-*.md` in the plans folder and also judges the items of a plan file no longer there. `--dry-run` writes nothing. Each kind of change names at most `sync_plans.max_listed` steps; `--json` gives `{dry_run, plans, steps, actions, notices, counts}`, every action. Fails open: no plans CLI, an unreadable plan or store, a hand-edited `TODO.md` is a `NOTICE` line on stderr, exit 0 |
| `todo detect [--id D] [--json]` | run the detectors (Detectors, below), each outside any lock, then file, update and close their `stall` and `lag` items under the lock of every scanned store, and record each run in this store's `todo-records.json`: `new`, `seen` (count, evidence or last-seen changed), `cleared` (closed `done-detected`). `--id D` runs one detector and judges its items alone. `--json` gives `{runs, actions, notices}`. Exit 1 when a detector failed (filed as a stall, its items unjudged) |
| `todo help` | the commands, one per line: what tools/checks reads to hold `cli.json`'s verbs to this CLI |

`tests/test_docs.py` holds this table equal to the parser, command by command and
flag by flag, and the command list in `PLAN-todo-tool.md` §3 equal to it too
(when the plan is present).

### Exit codes

| exit | means |
|---|---|
| 0 | done, or the answer was printed |
| 1 | refused: a missing (dangling) id, a field a kind requires, a `FAIL` from `check`, an item `brief` calls not ready |
| 2 | a flag or argument the parser does not take |
| 3 | `UNCHECKED`: not this scan's to judge (another service's id, a prefix no scanned store holds, a store or plan section that could not be read) |
| 4 | no store: no `todo.json` where the command needs one (a write, or `-C DIR` naming a folder without one), or none anywhere a read by id scans |

A missing id and a repo with no store never share a code, so a caller can tell
"ask elsewhere" from "set this repo up first" without reading stderr
(`tests/test_exit_codes.py`).

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
| `decision` | an open decision, with what it hinges on; a new one carries `pointer`, `hinges_on` and `recommend` and waits on Jacob's approval (Decisions, below) | Open decisions | |
| `suspicion` | an unconfirmed suspicion, with the probe that would settle it | Unconfirmed suspicions | `probe` |
| `report` | a problem reported to another repo's owner; its counterpart lives in their store | Reported to other owners | `reported_to` (set by `todo report`) |
| `temp` | an interim rule, with the check that retires it | Interim rules | `retire` |
| `jacob-step` | a step only Jacob takes, with the command that shows it taken (PLAN-architecture.md §11 S7); never ready or dispatchable; `todo steps` numbers them and `todo steps --run` closes each whose `done_check` exits 0 | Jacob's steps | `done_check` |
| `research` | a question of fact the research service holds (PLAN-services.md §3 S7): the item points at its `rs-` ids and never restates the answer | Research | `research` |
| `stall` | something stuck that nobody has to find (PLAN-todo-tool.md §10.5): filed, updated and closed by `todo detect` from a detector's finding, one per repo and cause; `todo add` never makes one, `edit --kind` never changes one, and `todo done` refuses while its detector still reports it (Detectors, below) | Stalls | `detector` (set by `todo detect`) |
| `lag` | a practice a repo has not caught up with yet (PLAN-todo-tool.md §10.5, PLAN-architecture.md §10): filed and closed by `todo detect` like a stall | Lags | `detector` (set by `todo detect`) |
| `plan-step` | a step of a plan, made and kept by `todo sync-plans` from the plan's own text (PLAN-services.md §3 G6, which calls it `step`; `plan-step` here, as `todo steps` and `jacob-step` already use the word); `todo add` never makes one, and `edit --kind` never turns an item into one or one into another kind | Plan steps | `plan_step` (set by `todo sync-plans`) |
| `note` | anything else worth keeping; the import default | Notes | |

<!-- vocab:statuses -->
| status | meaning | requires |
|---|---|---|
| `open` | workable now (the default; not shown in the render) | |
| `waiting-jacob` | needs Jacob's answer before anyone can move it; `add`, `edit` and `import` refuse one without `waits_on` (below), and check lists one written before that field | |
| `blocked` | waits on something other than Jacob; the evidence says what | |
| `done` | closed; the item lives in `todo-history.json` from then on | `done`, `resolution` |

What a `waiting-jacob` item waits on (`waits_on`, `--waits-on W`): one of these,
with its argument after a colon where it takes one. `todo blockers` groups the
items by it and prints what clears each group; it never reads the prose.

<!-- vocab:waits_on -->
| waits_on | what it waits on | argument | cleared by |
|---|---|---|---|
| `wizard` | his answer to a question in a wizard definition | the definition (`wizard:intake`) | `wizard run <definition>` |
| `settings` | a settings step only he takes, such as applying a proposed settings file; the evidence says which | none | that step |
| `approval` | his yes to start the work | none | `todo approve ID --source ...` |
| `decision` | his answer to a decision written in a plan section | `FILE §n` (`decision:PLAN-x.md §3`) | his answer |

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

Every brief carries the iterate rule too, `vocab.json` `brief.iterate_rule`:
PLAN-small-tasks.md §3.5 worded to the shared runner's real commands
(tools/checks `checkslib/parts.py`, installed by setup as `devtools/parts.py`),
not the plan's sketch where it names a command that does not exist: "Iterate small, then run whole once. While fixing one thing, run only what it touches: where dev.sh hands its parts to the shared runner (parts.py), `./dev.sh test <part>` runs that one part, and `./dev.sh check --resume` re-runs only the parts whose files changed since they passed or that did not pass; where it does not, run the one test you changed by itself. Run the full suite once, before the commit: `./dev.sh check`, without --resume. The plan's check --quick does not exist: --resume is the runner's nearest."
`tests/test_handoff.py` `IterateRule` holds each backticked command in it to
`./dev.sh check` plus options of the runner's `run`, or `./dev.sh test <part>`
(which the reference dev.sh turns into `check --only <part>`), read from the
runner's `parts.py usage --json` (`run.options`, pinned in the test and compared
with the runner itself when tools/checks is beside this repo). Each command the
plan sketches must be used in backticks when the runner runs it and named as
absent when it does not, so the wording fails its test when an option is added,
removed or renamed on either side.

A resolution is free text written by `todo done`, except the values below, which
each have one setter and are refused everywhere else:

<!-- vocab:resolutions -->
| resolution | meaning |
|---|---|
| `done-deprecated` | an imported closed bullet (DONE marker, or a Resolved or Confirmed heading) that carried no resolution: set by `todo import` only, refused by `todo done`, and a FAIL (`vocab`) in check on an item that was not imported |
| `done-checked` | a `jacob-step` closed because its `done_check` exited 0: set by `todo steps --run` only, refused by `todo done`, and a FAIL (`vocab`) in check on an item that is not a `jacob-step` with a `done_check` |
| `accepted` | a decision Jacob said yes to: set by `todo approve` and `todo answer` only (with `approved`), refused by `todo done --resolution`, and a FAIL (`vocab`) in check on an item that is not a decision or carries no approval |
| `option-chosen` | a decision closed on the option Jacob chose (`chosen`): set by `todo approve --option` and `todo answer` only, refused by `todo done --resolution`, and a FAIL in check without an approval or with a `chosen` naming none of its options |
| `rejected` | a decision Jacob said no to: set by `todo done --as rejected --reason R` and `todo answer` only, which put each open item it blocks back to waiting on it; a FAIL in check on an item that is not a decision |
| `done-detected` | a `stall` or `lag` closed because its detector no longer reports the finding: set by `todo detect` only, refused by `todo done`, and a FAIL (`vocab`) in check on an item with no `detector` |

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
| `waits_on` | what a `waiting-jacob` item waits on: `<value>` or `<value>:<argument>`, a value of the table below; set by `--waits-on` or by `todo import`, on a `waiting-jacob` item only; `todo blockers` groups by it |
| `pointer` | a decision's plan section, `FILE §n` (stored with the space), read by the plans CLI when set; the table's decision cell starts with it |
| `hinges_on` | what a decision hinges on, one line: the table's hinges-on cell |
| `recommend` | the answer recommended to Jacob: yes, no, or one of the decision's options by name |
| `options` | `[{name, text}]`: a decision's options, a short name (`decisions.option_name`, never an answer word) and one line each; set by `--option NAME=TEXT`, repeated |
| `chosen` | the option Jacob chose, by name; set only as a decision closes `option-chosen` |
| `jacob_words` | `[{date, table, row, text}]`: what Jacob answered on a decision's row that was no yes, no or option name, kept and applying nothing; appended by `todo answer` only |
| `repo` | where the work lives: a repo name, never a person or an agent |
| `work` | one of the works |
| `size` | one of the sizes, the estimate `todo ready` and tools/usage read; null until someone sizes it, and an unsized item is never ready |
| `files` | paths the work touches |
| `research` | the research service's questions this item rests on, by id (`rs-<n>`, PLAN-services.md §3 S7 R1); required on a `research` item; each gives the item a `ref:research:rs-<n>` tag, so `todo find` and `todo refs` reach it; set by `todo add/edit --research`. `check` counts them (`INFO`), unchecked until a registry resolves that service's ids |
| `done_when` | the observable that closes it |
| `done_check` | a shell command that exits 0 once the step is taken: run by `todo steps --run` under `steps.shell` (vocab.json) in the store's folder, stdin closed, killed after `steps.timeout_s`; required on a `jacob-step`; one line; set by `todo add/edit --done-check` |
| `handoff` | `{date, text, commit}`: the last checkpoint's note (done; next; how to verify), the day it was written and the work repo's commit then (null when that repo is not found); set by `todo edit ID --handoff`, carried by `todo brief` |
| `approved` | `{by, date, source}`: Jacob's go-ahead, the day he gave it and where; set by `todo approve`, or by `todo import` from "approved: Jacob <date>" in an item's lead, read by `todo dispatchable`. While an item is dispatched it may hold rule TD-B1's approval instead (its `source` the rule's), written by `todo dispatch` only |
| `dispatched` | `{date, text}`: the day it was handed out, and a one-line note that never names who; set and cleared by `todo dispatch` only |
| `retire` | the check that retires an interim rule |
| `tags` | the tags set by hand, `<namespace>:<value>`: `plan:`, `origin:`, `trust:`, `ref:` and `todo.group:` (below); the rest are derived from the fields and never stored |
| `plan_pins` | `[{plan, digest, date}]`: for each `plan:FILE§n` tag, the sha256 of that section's text and the day it was read; set by `--pin-plan` only, read by `todo stale-plans` |
| `detector` | `{id, subject, count, clears_with, seen}`: the finding a `stall` or `lag` item stands for, keyed `detector:<id>:<repo>:<subject>` with the item's `repo`; set, updated and cleared by `todo detect` only; `seen` is the last day a run reported it (Detectors, below) |
| `plan_step` | `{file, section, step, hash, text}`: the plan step a `plan-step` item was made from, as `setup plans steps --json` read it; set and kept by `todo sync-plans` only (Plan steps, below) |
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
| `todo.group` | a group the item belongs to, by name (lowercase letters, digits, `.`, `_`, `-`), such as the id of the heading it replaced; this service's own namespace, so a group outlives its heading | set by hand |

A namespace of this service's own is under its prefix (`todo.`), as PLAN-services.md
§3 row 2 says, so the plan's `group:` (PLAN-todo-tool.md §10.2 step 4) is
`todo.group:` here; `vocab.json` refuses an own namespace outside the prefix.
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
  day and where he gave it (or by `todo import`, from his dated "approved: Jacob
  YYYY-MM-DD" already written in an item's lead; Import, below). Nothing else counts
  as approval but the one rule he approved (Approval by rule, below): not a plan
  section, not an `origin:jacob` tag. `todo dispatch` refuses an item neither
  approves, and `check` fails an `approved` of another shape or approver, or a
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

### Approval by rule (TD-B1)

Jacob approved one rule in place of a yes per item (PLAN-todo-tool.md §10.1 cause 1,
2026-10-12). Its conditions are `vocab.json` `approval.rule`, read by
`todolib/approval.py` alone: an open item with no approval of its own counts as
approved when its kind is one of `kinds` (bug, suspicion, temp), its size one of
`sizes` (S, M), its `repo` is its store's own, it has every field in `needs`
(work, done_when), its status is `open`, its work is none of `exclude_works`
(outreach, decision, labour) and none of its `files` matches `exclude_files`
(settings files, `.git/config`). Jacob's own `approved` always wins.

- `todo dispatchable` lists rule-approved items under their own heading,
  "approved by rule TD-B1, not by Jacob", and `--json` under `by_rule` (never in
  `dispatchable`); held and dispatched entries carry `by_rule` true or false.
- `todo dispatch` stores the rule's approval (its `source` is the rule's) while
  the item is dispatched, and says so; `dispatch --clear` removes it. On an item
  the rule does not cover, it refuses and names each miss.
- The rule is judged afresh at every other read, so an item edited out of its
  reach loses it. `todo check` fails a stored rule approval on an open item that
  is not dispatched: only `todo dispatch` writes one.
- `todo show` prints the rule approval, or why the rule does not cover the item;
  `todo blockers` roots a ready item at `jacob` only when the rule does not cover it.
- What the rule cannot see: a push to a new remote, or an irreversible or
  outward act, except through `work` and `files`. An item naming neither is
  judged by its kind, size and repo (tests/test_approval_rule.py).

## Blockers

`todo blockers` answers "why is nothing moving" (PLAN-todo-tool.md §10.2): every
open item that is not dispatchable, across every scanned store, under the one root
that holds it, the roots ranked by how many items wait behind each. An item's root
is the first of these that holds it, since a later one cannot free an item an
earlier one holds: a report waits on its owner; an item blocked by another waits on
the open item at the end of that chain (followed to its end; a cycle, or an id no
store holds, is a root of its own and is never looped on); a `waiting-jacob` item
waits on Jacob, grouped by its `waits_on` (one naming none is grouped as such);
an item lacking what `todo brief` needs waits on its store's owner to triage it; an
item ready but for approval waits on his `todo approve`. Dispatched items and split
items are not held. `todo dispatchable` judges the same items: every open item is
in exactly one of the two (tests/test_blockers.py).

The kinds of root, their tie-break order, and the bounds (roots shown, ids per root,
lines under `dispatchable`) are `vocab.json` `blockers`:

<!-- vocab:blockers -->
| root | what holds the item |
|---|---|
| `jacob` | his answer, approval or settings step: the item's `waits_on`, one of his own steps (every `jacob-step`, as one root: `todo steps`), or his yes on an item otherwise ready |
| `item` | the open item at the end of a `blocked_by` chain; an id no store holds, or a cycle |
| `owner` | a report: its counterpart in the owner's store, by id (or the report not yet written) |
| `field` | what `todo brief` needs and the item lacks (repo, work, done_when, a size it can be dispatched at), or a `blocked` status naming no `blocked_by` |

## Decisions

A decision is generated and answered, not written up by hand (PLAN-todo-tool.md
§10.3, §10.3a, §10.3b). A new one carries three fields, `decisions.requires` in
`vocab.json`: `pointer`, the plan section it comes from (`FILE §n`, read by the
plans CLI as `--pin-plan` reads one; refused when it cannot be read), `hinges_on`
and `recommend` (yes, no, or one of its `--option NAME=TEXT` by name). It is added
`waiting-jacob` on `approval`, and the items it holds name it in `blocked_by`.

`todo decisions` tables every open, complete decision across the scanned stores:

    ## Decisions

    | # | decision | hinges on | recommend |
    |---|---|---|---|
    | 1 | PLAN-x.md §3: <title> | <hinges_on> | yes |

(a line above the table names its id and how to answer; `--json` gives each row's
item id). The workspace's own parser of a `## Decisions` section reads it with no
problem (checked once by hand, 2026-10-15; no test holds that seam here, because
that parser lives in the delegation layer, which this repo never reads)

numbered 1..n, the one whose answer frees most open items (counted back
through `blocked_by`, transitively, open items only) first. The table is recorded once in
`todo-records.json` as `dt-N`, with its date, its rows (number to item id) and the
answers it got; asking again with the same rows gives the same id, and
`--from dt-N` tables only that table's rows still open, recording which old row
each new row supersedes. A decision lacking a field is named under the table,
never tabled, and `check` lists it (`INFO`).

Jacob replies `1) yes 2) no 3) b 4) after the move`; `todo answer` reads it
against the table it names (`dt-N:` first in the reply, or `--table`), else the
latest. A yes closes the decision `accepted` with his approval, a no closes it
`rejected` and puts every open item it blocked back to `waiting-jacob` on
`decision:<its pointer>`, an option's name closes it `option-chosen` with
`chosen`, and anything else is kept in `jacob_words`, applying nothing. A reply
naming a row the table lacks, a row twice, or a closed decision is refused whole:
nothing is applied in part. `todo approve` (with `--option`) and `todo done --as
rejected --reason R` do the same for one decision outside a table.

`todo-records.json` is sealed like the store and append-only: check fails a table
or an answer removed or changed since its last commit (`records`).

## Jacob's steps

A step only Jacob can take (apply a settings file, answer a wizard, sign in
somewhere) is an item of kind `jacob-step` with a `done_check`: a one-line shell
command that exits 0 once the step is taken (PLAN-architecture.md §11 S7). It
replaces a numbered list of his steps written in prose, which goes stale the day
he takes one.

    todo add "apply settings.proposed.json" --kind jacob-step \
      --done-check "cmp -s .claude/settings.json .claude/settings.proposed.json"
    todo steps          # numbered, with each check
    todo steps --run    # closes each step whose check exits 0

- A step is never ready, dispatchable or briefable, and `todo blockers` groups
  every open step under one `jacob` root.
- The check runs as `steps.shell -c CHECK` (vocab.json) in the store's folder,
  stdin closed, killed after `steps.timeout_s`. Exit 0 closes the step with the
  resolution `done-checked`; another exit leaves it open; a timeout or a shell
  that cannot start is `UNCHECKED` (exit 3), never read as done or not done.
- The checks run before the store is locked, so a check may call `todo`; a step
  edited while its check ran is left for the next run.
- `todo steps --run` executes what the store holds: anyone who can commit a
  `done_check` can run a command on the machine of whoever runs it. Read new
  checks (`todo steps`) before `--run`, as you would a script you pull.

## Plan pins

An item made from a plan section goes stale when the section changes (Jacob,
2026-10-09). `--pin-plan` on `add` or `edit` records, for each `plan:FILE§n` tag,
the sha256 of the section's text as it reads that day (`plan_pins`), and
`todo stale-plans` lists every open item, in every scanned store, whose section
now reads differently (`changed`), is no longer there (`section gone`: the
section or its file), or was never pinned (a `plan:` tag with no pin, or one naming
no section: never read as fresh). "Last matched" is the day of the pin. Once the
item is brought up to date, `todo edit ID --pin-plan` pins the section again.

The section is read by the setup tool, `setup plans show FILE §n`, never parsed
here: what a section is belongs to that tool. Its own `digest` line is of the whole
file, so the pin hashes the section text it prints instead, and an edit to another
section of the plan leaves the pin fresh. The tool is found as `setup/setup` in the
first folder above this repo holding one, or named with `--plans-cli`; the plan
files are read from the scan root, or `--plans-dir`. A section that tool cannot
answer for (it is missing, the number is ambiguous, its output is in a form this
tool does not know) is `UNCHECKED`, exit 3, never fresh and never gone
(tests/test_plan_pins.py runs the real tool, so the seam itself is tested).

## Plan steps

Plans generate their items (PLAN-services.md §3 G6, §4 step 6.3). `todo sync-plans`
reads each plan's steps through `setup plans steps FILE --json`, the one parser of
the step grammar (never parsed here), and compares them with the `plan-step` items
made before, in every scanned store:

- **A new step** gets an item in the store of each repo it names as owner: titled
  from its bold lead or first sentence, tagged `plan:FILE§n` and pinned (Plan pins,
  above), `plan_step` holding the step. It is `open` with `approved` set when the
  plan records `approved: Jacob DATE` on the step or a step above it (the source
  names where), else `waiting-jacob` on `approval`; a step tracked `needs-yes FILE
  §n` waits on `decision:FILE §n` instead, and the sync makes that decision once, in
  the store it runs from, unless a store already holds one with that pointer.
- **A step is matched by its text hash first**, then by section and number, so an
  inserted step re-points nothing: a moved step's item is `renumbered`. A **changed**
  step's item takes the new title, step, tag and pin, gets an evidence line with the
  old text, and is listed `stale` with both: its judgement fields (`done_when`,
  size, files) are its owner's to redo. Only a status the sync set (waiting on
  approval or a decision) is moved by it.
- **An item already dispatched is never changed**: it is listed `flagged` with what
  would change. A closed item is never touched, and its step gets no new item.
- **A removed step's item is listed `gone`**, never closed: a person says whether
  the work is still wanted.
- **A step it gives no item is `listed`** with why: tracked in a hand-written
  `TODO.md`, naming no owner repo, naming one no scanned store has, or tracked
  `needs-yes` at a section no decision pointer takes. A step tracked `todo:`,
  `superseded-by` or `done` gets nothing (`vocab.json` `sync_plans.track`).
- It sets no `blocked_by`, and it fails open: a plan it cannot read is one notice
  and its items are judged neither changed nor gone; a store whose `TODO.md` was
  edited by hand keeps all its changes back, said in a notice.

`todo list --cites "FILE §n"` finds what cites a section, across every store.
tests/test_syncplans.py runs the real setup tool on fixture plans, one passing and
one failing case per kind of change.

## Detectors

A stall becomes an item without anyone finding it (PLAN-todo-tool.md §10.5,
approved by Jacob 2026-10-12). A detector is data: `vocab.json` `detectors.list`,
each `{id, doc, command, kind, waits_on, cadence_hours}`. The command is an argv
whose `{todo}` is this tool's `todo`, `{store}` the folder of the store detect runs
from and `{root}` the scan root; it prints a JSON list of findings, one per repo and
cause, each `{repo, subject, count, evidence, clears_with}`. todo reads no roster:
findings name repos.

- **`todo detect` reconciles, and is idempotent.** Each finding is one item of the
  detector's `kind`, keyed `detector:<id>:<repo>:<subject>`: a new one is filed in
  the store of its repo when the scan finds it (else here, naming the repo), titled
  `<id>: <subject>` with ` (count)` above one, `open`, or `waiting-jacob` on the
  detector's `waits_on`. One seen again updates its count, evidence and `seen`,
  never a second item. One gone closes its item `done-detected`.
- **Rolled up, never flooded.** More than `detectors.cap` findings is a failed run.
- **A failed run judges nothing.** A command that exits non-zero, times out
  (`timeout_s`), cannot start or prints anything but a findings list files one
  `stall` under the reserved id `failed_id` (`detect`), subject `detector D failed`,
  with the last `digest_lines` lines of its stderr; D's next good run from the same
  store closes it. `todo detect` exits 1.
- **A detector that does not run is a finding.** Each run is recorded in the store's
  `todo-records.json` `runs`, `{at, exit, ok, findings, why}`, `at` in UTC
  (`TODO_NOW`, else midnight of `TODO_TODAY`, else the clock); `todo check` fails a
  detector not run within `stale_factor` times its `cadence_hours`, in a store where
  any detector has run (the stores that host detect).
- **`todo done` on a stall or lag runs its detector first**, outside the lock: it
  refuses, naming the detector and what clears it, while the finding is reported or
  the detector cannot run; it closes once the finding is gone or the detector is no
  longer registered.
- **`TODO_DETECTORS=FILE`** replaces the list with the one in FILE, checked the same
  way, and says so on stderr every time: for fixtures and trial runs.

Registered now: S7 (`todo steps --run --findings`: a `jacob-step` whose
`done_check` passes is closed, and only one that could not be closed is a stall).
S2-S5 join when their commands exist, and S1/S6 as `lag` detectors from a
practices list; nothing here runs `todo detect` on a schedule yet. The
`vocab.json` section is checked both ways on load (todolib/vocab.py), and
tests/test_detect.py holds the plan's gates: a planted cause files one item and a
second run none, removing it closes the item, `done` refuses while it is reported,
a failing command files the failed item, a stale run is reported, and `blockers`
ranks a stall with its dependents.

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
  edit, and so is a format-1 file whose last git commit was sealed, or that sits
  beside a store file written since seals (every CLI write seals them all), in git
  or out of it. A file from before seals (`format` 1, never sealed, as is every
  file beside it) is a `WARN` until the next CLI write seals it. Outside git, both
  files set back to format 1 together, with no records file, cannot be told from
  that: nothing there remembers them sealed.

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
  "Resolved" or "Confirmed" heading goes there with no date. A bullet carries no resolution, so
  every imported closed item gets the resolution `done-deprecated` (Jacob, td-1),
  shown as such by `todo history`, `show` and `render --history`; its evidence
  holds the bullet text. A closed item without a resolution is a FAIL wherever it
  came from (PLAN §5). An imported one may still lack a date; `check` counts those
  (`INFO`).

## Import

`todo import FILE` turns a hand-written `TODO.md` into items without dropping a
word unseen: one top-level bullet or paragraph is one item. Kind and status come from
the headings above it (`vocab.json` `import`: "Needs Jacob" or "Waiting on Jacob"
→ decision waiting on Jacob, "Unconfirmed" → suspicion, "Reported" → report,
"Bug" → bug, "Resolved" or "Confirmed" → done; `note` otherwise; a rule matches
from a word start, so "Unconfirmed" is not "Confirmed"). A bold lead becomes the title
and the rest the evidence; otherwise the title is the first sentence and the
evidence the whole text. Each item records its block's sha, so re-running the
import adds nothing.

It also reads what the text already says (PLAN-todo-tool.md §10.2 step 6), each rule
a knob in `vocab.json` `import`, and never guesses: a rule that reads nothing sets
nothing, and the item is listed in the output instead.

| rule | reads | sets |
|---|---|---|
| `approval` | "approved: Jacob YYYY-MM-DD", in the lead (the text up to its first blank line or nested list line), with any quoted words after it | `approved` {by, date, source: the quoted words, else the matched text}, and a `waiting-jacob` item becomes `open`. A date after today is listed, not applied |
| `waits_on` | the earliest match of its rules in a still-waiting item: "waits on PLAN-x.md §n" (only when that section reads, through the plans CLI), "`wizard run DEF`", "waits on settings", "waits on his approval" | `waits_on`. A pointer no rule resolves ("waits on W-1"; `waits_on_mention` finds it) is listed; a real import then needs `--waits-on` |
| `probe` | for a kind requiring `probe`, the text after "Probe:" or "settle:", to the first sentence end outside backticks | `probe` |
| `report_owner`, `report_date` | for a report, the lead's first word when it is the whole owner and a repo the scan finds (a store's repo, or a git repo with no store yet), never this store's own; the first `(YYYY-MM-DD` on its first line, else today | `reported_to` {repo, date, their_id: null}; `check` then says how to pair it |
| `skip` | `intro`: a paragraph above a section's first bullet, in a section holding bullets, and a paragraph under the top heading alone in a file with deeper ones; `heading_only`: a block that is only a heading (`**Group:**`) | nothing: not an item, printed as skipped |

A kind whose required field no rule reads (a suspicion with no probe marker, a
report naming two owners or none) imports as `note`, records the kind it would have
had in `imported.wanted`, and is listed with the `todo edit` that completes it, so
`check` passes on the result. A closed (DONE) block is held to the same rule and
goes to history as a closed `note`, listed as kept as it is: history is never
edited, so a closed report with no `reported_to` would fail `check` for good (td-47). `tests/test_import_rules.py` holds a passing and a
failing fixture for each rule and shows each knob changes the output.

`tests/test_import.py` proves it lossless on three real `TODO.md` files: every
word comes back from the render, but for the skipped blocks it printed, and every
block comes back whole.

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

A report read by `todo import` from a hand-written `TODO.md` names its owner but
no counterpart: the owner may hold it under any id, or never have had it. Its
`their_id` stays null, and `check` warns (never fails) while the owner has a
store: `todo edit ID --reported-to REPO:THEIR_ID` records the counterpart once
someone confirms it (the edit refuses an id whose `parent` is not ID), or
`todo report ID --to REPO` writes one. A report made in this store and left
unpaired is still a failure.

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
| groups | a `WARN`, never red: an open item with no `work` (split or not), not a report, that open items use as a group (as their `parent`, or by a `todo.group:<its id>` tag). A heading is not an item (PLAN-todo-tool.md §10.2 step 4): tag its children `todo.group:<name>` and close it |
| reports | a report's owner has a store but no counterpart, or the counterpart's parent points elsewhere |
| workspace | two stores share a prefix or a repo name |
| render | `TODO.md` is not the render of `todo.json`: missing, stale (an unedited render of another store or format), hand-edited or hand-written |
| history | the file is missing or malformed, or an entry was removed or changed since a commit |
| records | `todo-records.json` is malformed, or a decision table committed was removed or changed, or an answer to it changed |
| detectors | a detector's recorded run is malformed; a registered detector has not run within `stale_factor` times its cadence (or never) in a store where any detector has run; two open items hold one detector key |

## Development

`./dev.sh check` is the one pre-commit command. It hands `check.parts.json` to
`devtools/parts.py`, the shared parts runner (tools/checks' runner, installed by
setup's `parts` component; PLAN-small-tasks.md §5): one part per `tests/test_*.py`
module, then the gates (`./dev.sh hooks`, `files`, `audit`, `self`, `checks`,
`mutants`), each with its own timeout and recorded as it ends in `$PROGRESS_FILE`
(default `.progress/check.json`, gitignored). The runner's options pass through:
`--json` (one check-json document, one check per part), `--resume` (re-run only
what did not pass or whose files changed), `--only PART` (repeatable). A part that
reads outside this repo says `always` and `--resume` never skips it.
`./dev.sh test PART ...` is `check --only PART ...`; `./dev.sh test` alone is the
whole unittest suite in one process. `tests/test_parts_file.py` holds the parts
file to the test modules and to dev.sh's gates, and runs tools/checks'
`check-partial` and `check-json` contracts on this repo.

The parts are: the unit tests, the hook copies,
the files the tool needs, the direction audit (`devtools/audit.py`: no file here
reads the delegation layer's files or names a roster agent; the shared copies
installed in `.claude/hooks/` and its sibling `lib/` are skipped, being the hooks
tool's files gated by its `hooks copies`, td-16), `todo check` on this
repo's own store, tools/checks' `checks run .` (below), and the mutants (`devtools/mutate.py`: each gate broken once
in a throwaway copy, which must turn its test red). The copies live under
`.mutants/run-*/` (gitignored) and are removed however the run ends, SIGTERM
included (its commands are stopped first); only SIGKILL leaves one behind. An
argument `mutate.py` does not know is refused with its usage (exit 2), never a
full run (`tests/test_mutate.py`).

The `hooks` gate reads each hook test's exit code as a gate: 0 pass, 3 UNCHECKED
(the test could not run here, e.g. no site-scrapers above a lone clone; named with
its reason), anything else FAIL. An UNCHECKED test makes the gate exit 3, never 0;
a FAIL anywhere makes it 1. `./dev.sh check` exits 1 if any part failed, else 3 if
any said UNCHECKED (its exit 3), else 0. The runner alone exits 0 on an UNCHECKED
part, so dev.sh reads the run (the `UNCHK` line, or in `--json` a check
`unchecked` for `exit 3: ...`) and exits 3 itself; a part `--only` left out is
`unchecked` with `not run` and does not count (`tests/test_hooks_gate.py`,
`tests/test_parts_file.py` Unchecked, mutants `hooks-unchecked-*`,
`check-unchecked-is-green`, `check-*-unchecked-unread`, `check-json-not-run-is-unchecked`).

`tests/test_dev.py` holds the check-json document on the cheap parts (`files`,
`audit`): named parts `ok`, the rest `unchecked`; a red part `fail` and exit 1; an
unknown part refused (exit 2). A check run inside another check (`TODO_DEV_CHECK`
set) runs only parts named with `--only`, and never a `test.*` part or `mutants`,
since either would run that test again without end (exit 2, nothing on stdout);
a foreign parts file (`CHECK_PARTS`) is left alone. The test of that guard runs in
a copy whose parts are one stub test, `files` and one stub mutant, so a broken
guard goes red instead of recursing (mutants `check-nesting-*`). The `self` gate's mutant plants a bad store
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
`accepted` in `audit.json` exempts single lines that hit a term and cannot change,
each by file and exact text with its reason: today one append-only history entry
(td-28's resolution names the installed `lib/extra-stores.sh`). An entry whose line
is gone, or whose line hits no term, fails the audit (mutants `audit-*`).

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
