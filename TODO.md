<!-- rendered by todo from todo.json (9 open, 0 closed in todo-history.json): do not edit by hand, `todo check` fails on a hand edit. Change items with the todo CLI; a hand edit is recovered with `todo import`. -->
# todo TODO

## Own bugs

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

- **td-3 · A report to the delegation layer stays unpaired forever**
  The scan never enters hidden folders (tests/test_store.py), so a store in .claude/ is never found and todo report --to .claude gives a counterpart-less WARN for good. Hinges on: whether the delegation layer keeps a todo.json at all, and if so whether the scan admits that one folder by name.
  · work: decision
  · done when: a report to that layer pairs, or the README says it never will
  · added: 2026-10-04

## Unconfirmed suspicions

- **td-4 · The roster-name copy in devtools/audit.json can go stale**
  The direction audit bans roster names that are not repo names, from a copy taken 2026-10-04. This repo may not read the roster to refresh it, so a new agent name would pass the audit unnoticed.
  · probe: the delegation layer's owner lists its roster names and diffs them against roster_names in devtools/audit.json
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
  · reported to: .claude on 2026-10-04 (no counterpart yet)
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

- **td-6 · dev.sh check --json has no test of its own**
  A test that runs ./dev.sh check would run the mutants, which copy the repo and run the tests again. The JSON contract ({"ok": bool, "gates": {...}}) is read by eye at each commit. The self gate also has no mutant: in a mutant copy it shares this repo's prefix and is red at baseline.
  · work: test
  · files: dev.sh
  · done when: dev.sh check accepts a gate list, and a test runs it without mutants and parses the JSON
  · added: 2026-10-04
