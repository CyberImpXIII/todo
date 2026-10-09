<!-- rendered by todo from todo.json (15 open, 14 closed in todo-history.json; seal 66f5647b06c1): do not edit by hand, `todo check` fails on a hand edit. Change items with the todo CLI; a hand edit is recovered with `todo import`. -->
# todo TODO

## Own bugs

## Open decisions

- **td-2 · The shared hooks setup installed are not registered in settings.json**
  settings.json is tracked since 8523dd8 but predates the 2026-10-05 setup run (tools/setup 32aeaa9), which installed ask-first, git-stamp, no-secrets, primary-guard, push-gate, settings-guard and write-ledger. settings.proposed.json registers all seven, settings.json none, so ./dev.sh hooks fails 7 registrations (each hook's own test passes) and the mutants gate is BASELINE-RED from it. settings.json is Jacob's: he applies the proposal himself (setup prints the step).
  · status: waiting-jacob
  · work: decision
  · done when: ./dev.sh hooks prints 'registered'
  · added: 2026-10-04

- **td-22 · A Confirmed heading imports as open notes, not closed items**
  Dry run on a copy of the top-level TODO.md (2026-10-09): 168 to the store, 33 to history. The 24 blocks under '## Confirmed (2026-10-01, by probe unless stated)' go to the store as note/open, but PLAN-todo-tool.md §9 step 1 says a confirmed finding becomes a closed item. One vocab.json import rule ({match: confirmed, status: done}; the \b match keeps 'Unconfirmed' out) would close them with done-deprecated. Hinges on a yes from the top level's owner: it changes every repo's import, and done-deprecated's meaning (DONE marker or Resolved heading) would widen. Also: 'Needs Jacob' bullets with DONE mid-text (e.g. 'knowledge-base sweep DONE') stay open by rule.
  · work: decision
  · done when: the top level's owner says yes or no; a yes lands as the rule with its test
  · added: 2026-10-09

- **td-26 · repo: tags here are repo names (repo:todo); PLAN-services.md §3's example is a path (repo:tools/todo)**
  todolib/tags.py derives repo: from the item's repo field, which is a repo name everywhere in this tool. The plan's example table writes repo:tools/todo. find repo:tools/todo returns nothing here. Hinges on S3's rule for repo: values (a repo that exists: by name or by path).
  · work: decision
  · tags: plan:PLAN-services.md§3
  · added: 2026-10-09

- **td-29 · cli.json declares the stores, so tools/checks' stores-exported now wants a verify verb**
  ./dev.sh check, 2026-10-09, after cli.json was added for the seal (PLAN-todo-tool.md §9): checks gate FAIL stores-exported: 'cli.json: declares no `verify` verb: nothing shows the store's export is current'. That check (tools/checks source/stores-exported.py, PLAN-repo-setup.md §7.11) runs `todo verify --json` against an export in DATA_REPO. This tool has no export and no plan for one; the brief did not ask for it. Hinges on: whether todo stores get an export in the data repo at all (the top level's owner decides), and then `todo export` + `todo verify --json` per schema/verify.schema.json.
  · work: decision
  · added: 2026-10-09

## Unconfirmed suspicions

## Reported to other owners

- **td-4 · The roster-name copy in devtools/audit.json can go stale**
  The direction audit bans roster names that are not repo names, from a copy taken 2026-10-04. This repo may not read the roster to refresh it, so a new agent name would pass the audit unnoticed.
  2026-10-06: the checks gate (td-12) passes this same copy to tools/checks' no-roster, so a stale copy now weakens two gates. Relayed to the delegation layer's owner by hand in the sweep report.
  · probe: from the delegation layer (its owner runs it, this repo may not): list the roster's agent names, drop those that are also repo names, and diff the rest against roster_names in tools/todo/devtools/audit.json; a name present in the roster and missing there settles it as stale
  · reported to: .claude on 2026-10-06 (relayed by hand; never pairs)
  · work: audit
  · files: devtools/audit.json
  · done when: the probe shows no missing name, or a check outside this repo runs it
  · added: 2026-10-04

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

- **td-25 · get, find and refs cannot be declared in services.json: its schema allows service check or write only**
  tools/checks schema/services.schema.json (commit 96ceef9) has service enum [check, write]; get/find/refs are reads, so declaring them as write would mislabel them. Not declared; README says so. context-hygiene hit the same wall on 2026-10-09. Needs tools/checks to add a read service (or a verbs-only entry) to the schema.
  · reported to: checks on 2026-10-09 (no counterpart yet)
  · work: decision
  · tags: plan:PLAN-services.md§3
  · added: 2026-10-09

## Interim rules

- **td-24 · The tag table in vocab.json is a local copy; read it from the architecture service once it exists**
  PLAN-services.md §3: the vocabulary lives in the architecture service (S3), which does not exist yet. vocab.json tags.shared copies its seven namespaces; tests/test_tags.py holds them equal to the plan's table (mutant shared-namespaces-drift). Closed values (origin: jacob, model, tool; trust: untrusted) are the plan's examples, not a ruling: S3 decides closed values.
  · work: code
  · files: vocab.json, todolib/tags.py
  · retire: the architecture service (S3) serves the shared vocabulary and todolib reads it from there; tests/test_tags.py Vocabulary then compares against S3, not the plan
  · tags: plan:PLAN-services.md§3
  · added: 2026-10-09

## Notes

- **td-5 · The append-only audit sees committed versions and the working copy only**
  check_history compares todo-history.json with every version in git log plus the file on disk. An entry appended and removed again between two commits leaves no trace to compare with. Accepted for now: todo done is the only writer and no command removes an entry.
  · work: audit
  · files: todolib/checks.py
  · added: 2026-10-04

- **td-13 · check cannot tell done-deprecated set by hand on an imported item**
  The vocab gate fails done-deprecated only on an item with imported null. An item imported open (imported set) and later given done-deprecated by a hand edit of todo-history.json passes check; todo done refuses the value, so only a hand edit reaches it, and the history append-only audit catches that edit once a version is committed. Accepted for now.
  · work: audit
  · files: todolib/checks.py
  · added: 2026-10-04

- **td-23 · Outside git the history append-only audit is skipped and history still prints ok**
  check_history adds an INFO 'not a git repo: the append-only audit ... is skipped here' and the gate prints ok. The top-level store (PLAN §9 step 1) is never in git, so its history would never be audited. The store seal (PLAN §9 'The gap his question found', queued next) is the candidate guard; until then it is visible only as INFO.
  · work: audit
  · files: todolib/checks.py
  · added: 2026-10-09

- **td-27 · PLAN-todo-tool.md §3's command list does not name get, find and refs**
  tests/test_docs.py BEYOND_PLAN declares them with a reason so the plan-equals-commands test stays green. Asked of the plan's owner in the 2026-10-09 report; when §3 lists them, drop them from BEYOND_PLAN (the test then fails until you do).
  · work: docs
  · done when: PLAN-todo-tool.md §3 lists todo get, find and refs and BEYOND_PLAN holds init only
  · tags: plan:PLAN-todo-tool.md§3
  · added: 2026-10-09

- **td-28 · Other repos' stores are declared in no cli.json and still format 1**
  The seal and the 0444 mode now apply wherever this CLI writes (2026-10-09), but cli.json declares only tools/todo's own todo.json and todo-history.json. Every other store (the top level, income, and each repo that runs todo init) is format 1 until its next CLI write, a WARN in its check till then, and no hook or accessor knows it is a store. unverified: no other repo has a cli.json naming todo.json -- settle: grep -l todo.json ../*/cli.json ../../cli.json
  · added: 2026-10-09
