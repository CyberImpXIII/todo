<!-- rendered by todo from todo.json (10 open, 5 closed in todo-history.json; seal 498129ae394e): do not edit by hand, `todo check` fails on a hand edit. Change items with the todo CLI; a hand edit is recovered with `todo import`. -->
# todo TODO

## Own bugs

## Open decisions

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

- **td-14 · The reinstalled test-no-inline-blobs.sh names roster agents, so the direction audit is red**
  After reinstalling from tools/hooks/source on 2026-10-04 (533f484), ./dev.sh check: audit FAIL .claude/hooks/test-no-inline-blobs.sh:107 and :108, a provenance comment in the source naming two roster agents as reporters of the heredoc false positives. That turns 3 unit tests red (test_audit this_repo_is_clean, test_dev CheckJson x2) and 2 mutant baselines. The copy may not be hand-edited. Fix A (hooks owner): reword the source comment without the agent names, then reinstall here. Fix B (this repo's decision): skip roster_names, not patterns, under .claude/hooks/ in devtools/audit.json, with a test and a mutant.
  · reported to: hooks on 2026-10-04 (no counterpart yet)
  · work: audit
  · files: .claude/hooks/test-no-inline-blobs.sh, devtools/audit.json
  · done when: ./dev.sh check passes the audit gate with the copies still byte-identical to tools/hooks/source
  · added: 2026-10-04

## Notes

- **td-5 · The append-only audit sees committed versions and the working copy only**
  check_history compares todo-history.json with every version in git log plus the file on disk. An entry appended and removed again between two commits leaves no trace to compare with. Accepted for now: todo done is the only writer and no command removes an entry.
  · work: audit
  · files: todolib/checks.py
  · added: 2026-10-04

- **td-12 · dev.sh check does not run tools/checks on this repo**
  tools/checks' CLAUDE.md says a repo's ./dev.sh check calls 'checks run .'. This one does not: checks.json is held by tests/test_audit.py (exclusions are files devtools/audit.py also skips), but whether no-roster is green here was seen only by hand on 2026-10-04 (cd ../checks && ./checks run ../todo --names <the roster copy in devtools/audit.json>: no-roster OK; without --names it is UNCHECKED by that tool's design). Wiring it needs the sibling path and roster names passed in, which this repo may not read.
  · work: tooling
  · files: dev.sh, checks.json
  · done when: ./dev.sh check runs checks run . (or the README says why not) and fails when no-roster is red
  · added: 2026-10-04

- **td-13 · check cannot tell done-deprecated set by hand on an imported item**
  The vocab gate fails done-deprecated only on an item with imported null. An item imported open (imported set) and later given done-deprecated by a hand edit of todo-history.json passes check; todo done refuses the value, so only a hand edit reaches it, and the history append-only audit catches that edit once a version is committed. Accepted for now.
  · work: audit
  · files: todolib/checks.py
  · added: 2026-10-04

- **td-15 · Report to the todo repo: the work vocabulary has no kind for research, labour or outreach**
  Observed 2026-10-05 while seeding this store: works are code, test, audit, tooling, docs, decision. Gig driving, an appeal filing, a client proposal and a mail scan all had to be filed as tooling or docs. The local session runs todo report with --to todo so the counterpart lands in that store.
  · parent: inc-50
  · work: docs
  · done when: the counterpart item exists in the todo repo's store
  · added: 2026-10-05
