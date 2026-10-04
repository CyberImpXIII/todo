<!-- rendered by todo from todo.json (9 open, 2 closed in todo-history.json): do not edit by hand, `todo check` fails on a hand edit. Change items with the todo CLI; a hand edit is recovered with `todo import`. -->
# todo TODO

## Own bugs

- **td-10 · A change to the render format reads as a hand edit in every store**
  render_state (todolib/checks.py) calls a TODO.md clean only when it equals the current render, and hand-edited when it differs but starts with the header. So any change to render.py's output turns every store holding an affected item red in check (WARN during the import grace, FAIL after), and every mutating command there refuses until 'todo render --force', which records a hand edit that never happened.
  Seen 2026-10-04 on this repo: td-3 changed the reported_to line for a hidden repo; todo check then said 'TODO.md is edited by hand since it was rendered' for td-8, and render --force wrote a hand_edits entry for an edit nobody made. One store exists today, so it was re-rendered in the same commit; once other repos migrate, a format change lands in stores this repo does not commit.
  · work: code
  · files: todolib/checks.py, todolib/render.py
  · done when: a store rendered by an older render format is told so (stale render, re-render) rather than hand-edited, or the README says a format change needs every store re-rendered
  · added: 2026-10-04

## Open decisions

- **td-1 · Imported closed items may lack a resolution, which PLAN §5 says is red**
  PLAN-todo-tool.md §5 says a done without a resolution is red in check for imported items. A DONE bullet carries a date but no resolution field, and history is append-only with no edit command, so a red there could never be cleared. Built instead: check counts them as INFO and their evidence keeps the bullet text. Hinges on: accept the INFO (recommend), or let import copy the bullet text into resolution (a guess, which the rules prefer null over).
  · status: waiting-jacob
  · work: decision
  · done when: PLAN §5 records the choice and check follows it
  · added: 2026-10-04

- **td-2 · The shared hooks are not live in this repo until settings.json exists**
  tools/setup wrote .claude/settings.proposed.json and never touches settings.json. Jacob's step, in tools/todo: cp .claude/settings.proposed.json .claude/settings.json. ./dev.sh hooks prints a NOTE until then, and requires registration once the file exists.
  · status: waiting-jacob
  · work: decision
  · done when: ./dev.sh hooks prints 'registered'
  · added: 2026-10-04

## Unconfirmed suspicions

- **td-4 · The roster-name copy in devtools/audit.json can go stale**
  The direction audit bans roster names that are not repo names, from a copy taken 2026-10-04. This repo may not read the roster to refresh it, so a new agent name would pass the audit unnoticed.
  · probe: from the delegation layer (its owner runs it, this repo may not): list the roster's agent names, drop those that are also repo names, and diff the rest against roster_names in tools/todo/devtools/audit.json; a name present in the roster and missing there settles it as stale
  · work: audit
  · files: devtools/audit.json
  · done when: the probe shows no missing name, or a check outside this repo runs it
  · added: 2026-10-04

## Reported to other owners

- **td-7 · The hook-copy check does not cover this repo's copies**
  The top-level CLAUDE.md says the site-scrapers hook-copy check covers eight copies, not addon-bench or tools/setup. tools/todo carries a further copy of no-inline-blobs.sh, prefer-recipes.sh and troubleshooting.sh, installed by setup, so a drifted copy here goes unreported.
  · reported to: site-scrapers on 2026-10-04 (no counterpart yet)
  · work: audit
  · done when: site-scrapers ./dev.sh check fails when a hook copy in tools/todo differs
  · added: 2026-10-04

- **td-8 · This repo needs a roster entry**
  Proposed entry: name todo, dir tools/todo, repo github.com/CyberImpXIII/todo, start_here tools/todo/CLAUDE.md, precommit ./dev.sh check. The top-level CLAUDE.md tool table and its rules-sync list need a row for tools/todo too (top-level prose, no repo: relayed in the build report).
  · reported to: .claude on 2026-10-04 (relayed by hand; never pairs)
  · work: tooling
  · done when: a session can dispatch work in tools/todo to its own owner
  · added: 2026-10-04

- **td-9 · devtools/mutate.py duplicates the setup repo's mutant runner**
  Copied from tools/setup/devtools/mutate.py on 2026-10-04 and extended with an edits list (a gate guarded in two places needs both broken). Two copies will drift. Candidate for a shared component that setup installs.
  · reported to: setup on 2026-10-04 (no counterpart yet)
  · work: tooling
  · files: devtools/mutate.py
  · done when: one copy, installed by setup, with the edits list
  · added: 2026-10-04

## Notes

- **td-5 · The append-only audit sees committed versions and the working copy only**
  check_history compares todo-history.json with every version in git log plus the file on disk. An entry appended and removed again between two commits leaves no trace to compare with. Accepted for now: todo done is the only writer and no command removes an entry.
  · work: audit
  · files: todolib/checks.py
  · added: 2026-10-04

- **td-11 · The self gate and the check-nesting guard have no mutant**
  Carried from td-6. The self gate (./dev.sh self, todo check on this store) has none: in a mutant copy under .mutants/ the scan root is still the workspace, so the copy shares this repo's prefix and is red at baseline. The nesting guard in cmd_check (TODO_DEV_CHECK: a check inside a check refuses the test and mutants gates) has none either: with it broken, its own test runs the test gate, which runs that test again without end. Seen 2026-10-04: tests/test_dev.py run against the previous dev.sh (which ignored the gate list) did exactly that and had to be stopped. The guard is held by tests/test_dev.py only.
  · work: test
  · files: dev.sh, devtools/mutate.py, tests/test_dev.py
  · done when: a mutant breaks the self gate and goes red without a red baseline, or the README says why it cannot
  · added: 2026-10-04
