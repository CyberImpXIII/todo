<!-- rendered by todo from todo.json (52 open, 46 closed in todo-history.json; seal 24c94cb9923d): do not edit by hand, `todo check` fails on a hand edit. Change items with the todo CLI; a hand edit is recovered with `todo import`. -->
# todo TODO

## Own bugs

- **td-48 · `todo repos` skips .claude (hidden dir) -- input: tools/todo/todo repos -- expected: hx listed. A...**
  reported to todo in dispatch toolu_01LWiD7eKj8CV3V6FQsyVKxE by the delegation layer's owner, filed from its dispatch ledger (names of that layer taken out: this repo names none, devtools/audit.py): `todo repos` skips .claude (hidden dir) -- input: tools/todo/todo repos -- expected: hx listed. Also no `todo detect` (needed by PLAN-todo-tool §10.5). 2026-10-16 todo: by design today: a hidden folder is never scanned (PLAN-todo-tool.md §8 decision 4: todo never reads the delegation layer), so listing it needs Jacob to change that decision.
  · parent: tl-219
  · added: 2026-10-15

- **td-49 · `add --kind decision` now needs --pointer/--hinges-on/--recommend, and cli.json now has `sync-pla...**
  reported to todo in dispatch toolu_01LWiD7eKj8CV3V6FQsyVKxE by the delegation layer's owner, filed from its dispatch ledger (names of that layer taken out: this repo names none, devtools/audit.py): `add --kind decision` now needs --pointer/--hinges-on/--recommend, and cli.json now has `sync-plans`, both uncommitted -- input: todo add "Which source" --kind decision --work code -- expected: when it commits, tell that owner so its test-offload and todo-verbs.json follow.
  · parent: tl-220
  · added: 2026-10-15

- **td-56 · `todo -C S edit ID --append-evidence=X --status=open` on a waiting-jacob item that has waits_on e...**
  reported from tools/wizard to tools/todo in dispatch toolu_01N3MUz4nghChG9gh9gg4dPG, filed from the dispatch ledger by the delegation layer's report filer: `todo -C S edit ID --append-evidence=X --status=open` on a waiting-jacob item that has waits_on exits 1 ("clear it with --waits-on ''") -- input: a scratch store, `add --status waiting-jacob --waits-on wizard:x Pick`, then that edit -- expected: leaving waiting-jacob clears waits_on.
  · parent: tl-244
  · added: 2026-10-16

- **td-57 · importing a "Reported to other owners" section gives report items with no `reported_to`, which fa...**
  reported from tools/checks to tools/todo in dispatch toolu_01UsoP3YSofAzhSbJhhJbU2p, filed from the dispatch ledger by the delegation layer's report filer: importing a "Reported to other owners" section gives report items with no `reported_to`, which fail `todo check` -- input: `todo -C tools/checks init --prefix ck; todo -C tools/checks import TODO.md; todo -C tools/checks check` -- expected: an import that passes its own check, e.g. the owner read from the start of the bullet, or `edit --reported-to` without writing into the owner's store. Suspi...
  · parent: tl-250
  · added: 2026-10-16

- **td-76 · TODO.md's header says it is rendered from todo.json when the store is on todo.db**
  the render header is fixed text; on todo.db the data comes from todo.db
  · work: code
  · added: 2026-10-19

- **td-85 · the TODO.md renders are not declared as cli.json renders, so any subagent can write them -- input...**
  reported from tools/research to tools/todo in dispatch toolu_01UN1CyFQG8Z7QD9MeEmRrBq, filed from the dispatch ledger by the delegation layer's report filer: the TODO.md renders are not declared as cli.json renders, so any subagent can write them -- input: ownership_probe.py, render rows, persona "other" -- expected: enforced (G4; the same for the delegation layer's agent files). Reworded 2026-10-20 (tl-502): the filed text named a roster agent and the delegation layer's folder, which this repo's audit refuses
  · parent: tl-476
  · added: 2026-10-20

- **td-86 · td-9 can close (su-74 done); tools/todo/tests/test_mutate.py tests the rendered copy, a subset of...**
  reported from tools/setup to tools/todo in dispatch toolu_01EBMeUPeGmdDova1f6umY6W, filed from the dispatch ledger by the delegation layer's report filer: td-9 can close (su-74 done); tools/todo/tests/test_mutate.py tests the rendered copy, a subset of setup's tests/test_mutate.py; .mutants/run-z9ahy1dy (Oct 13, 288 dirs) is left over -- input: `./setup todo --only mutate --dry-run` -- expected: todo deletes the duplicate test and the leftover run
  · parent: tl-477
  · added: 2026-10-20

- **td-87 · the brief's iterate rule (vocab.json) says `./dev.sh test <part>` runs one part; in tools/setup i...**
  reported from tools/setup to tools/todo in dispatch toolu_01EBMeUPeGmdDova1f6umY6W, filed from the dispatch ledger by the delegation layer's report filer: the brief's iterate rule (vocab.json) says `./dev.sh test <part>` runs one part; in tools/setup it ran the whole suite -- input: `./dev.sh test test.mutate_component` -- expected: the rule names `./dev.sh check --only <part>`
  · parent: tl-478
  · added: 2026-10-20

- **td-88 · §10 step 2 needs a `todo resolve <id>...` command that takes many ids -- input: dispatch-section....**
  reported from .claude to tools/todo in dispatch toolu_01GyQX8T9jq49RnqsSutbtXV, filed from the dispatch ledger by the delegation layer's report filer: §10 step 2 needs a `todo resolve <id>...` command that takes many ids -- input: dispatch-section.sh resolving every todo: pointer of one message -- expected: one call that resolves them all.
  · parent: tl-487
  · added: 2026-10-20

- **td-91 · there is no CLI read for which dt-N row holds an item -- input: `todo -C /Users/Specter/Desktop/c...**
  reported from .claude to tools/todo in dispatch toolu_01Nzpy2Hpfd9RyJ9kQ8hn1TB, filed from the dispatch ledger by the delegation layer's report filer: there is no CLI read for which dt-N row holds an item -- input: `todo -C /Users/Specter/Desktop/claudeTest get dt-36` gives exit 3 (UNCHECKED) -- expected: a verb (e.g. tl-461 resolve, or `get ID`) that returns that item's tabled rows as [{table,row}].
  · parent: tl-536
  · added: 2026-10-21

- **td-94 · `todo history` has no --json, so the inventory cannot read closed items -- input: `tools/todo/tod...**
  reported from tools/research to tools/todo in dispatch toolu_019FsbVB8CsBmXLifZhcJL3k, filed from the dispatch ledger by the delegation layer's report filer: `todo history` has no --json, so the inventory cannot read closed items -- input: `tools/todo/todo -C /Users/Specter/Desktop/claudeTest history --json` -- expected: JSON (got exit 2, unrecognized arguments).
  2026-10-23: fixed in the tree as top-level tl-560 (history --json), uncommitted until td-90 is decided; close this with tl-560.
  · parent: tl-559
  · added: 2026-10-22

- **td-96 · todo decisions --json records a new dt-N table whenever the open rows change, and todo answer wit...**
  reported from tools/context-hygiene to tools/todo in dispatch toolu_01RMPEvSWQxt1HAVrsA96WMf, filed from the dispatch ledger by the delegation layer's report filer: todo decisions --json records a new dt-N table whenever the open rows change, and todo answer with no dt-N answers the latest table, so a read-only caller (the status line) risks putting Jacob's next answer under a table he never saw -- input: todo decisions --json -- expected: a read-only form (e.g. --no-record) that prints the same rows without recording
  · parent: tl-567
  · added: 2026-10-22

- **td-97 · once tl-564 is pushed, todolib/practices.py can switch ARGS to ("practices", "--rows", "--json") ...**
  reported from tools/checks to tools/todo in dispatch toolu_01RpouMWQvN6PJd7mGUETsvk, filed from the dispatch ledger by the delegation layer's report filer: once tl-564 is pushed, todolib/practices.py can switch ARGS to ("practices", "--rows", "--json") with no stdin report (td-64) -- input: `tools/checks/checks practices --rows --json` -- expected: the same rows as today, without cells.
  · parent: tl-586
  · added: 2026-10-22

## Open decisions

- **td-2 · The shared hooks setup installed are not registered in settings.json**
  settings.json is tracked since 8523dd8 but predates the 2026-10-05 setup run (tools/setup 32aeaa9), which installed ask-first, git-stamp, no-secrets, primary-guard, push-gate, settings-guard and write-ledger. settings.proposed.json registers all seven, settings.json none, so ./dev.sh hooks fails 7 registrations (each hook's own test passes) and the mutants gate is BASELINE-RED from it. settings.json is Jacob's: he applies the proposal himself (setup prints the step).
  2026-10-12, after Jacob's wiring --apply (all 62 requirements in the top-level settings.json): ./dev.sh hooks in tools/todo still prints 'FAIL  store-guard.sh is not registered in .claude/settings.json', exit 1; this repo's .claude/settings.json (uncommitted, not this tool's to edit) registers the other seven. Not closed.
  2026-10-15: .claude/settings.json is byte-equal to .claude/settings.proposed.json, and neither registers store-guard.sh (installed in .claude/hooks/), so ./dev.sh hooks stays red on 'store-guard.sh is not registered' even once Jacob applies the proposal; the proposal gap is setup's (reported 2026-10-15).
  · status: waiting-jacob
  · waits on: settings
  · work: decision
  · done when: ./dev.sh hooks prints 'registered'
  · added: 2026-10-04

- **td-44 · report fallback leaves a foreign TODO.md uncommitted, in tension with S2**
  e0f6e71: todo report --to a storeless repo appends a bullet to that repo's TODO.md and does not commit it (another owner's tree). PLAN-architecture.md §11 S2 reads a foreign uncommitted file as someone mid-task. Options: commit it there in the same run (S2's renderer rule), or leave it for the owner (now). Also unguarded: a read-modify-write race with the owner editing that TODO.md at the same moment.
  · tags: plan:PLAN-architecture.md§11
  · added: 2026-10-15

## Unconfirmed suspicions

- **td-45 · research ids are unchecked until tools/research has a CLI**
  8cb53f9: check counts research ids as unchecked foreign refs (INFO). Nothing proves an rs- id exists.
  · probe: once tools/research has a 'get rs-N' verb: todo check resolves each research id and fails a dangling one
  · added: 2026-10-15

- **td-46 · jacob-step done_check runs whatever the store holds**
  fa05045: todo steps --run executes each done_check under /bin/sh; anyone who can commit todo.json can run a command on the runner's machine. README says to read checks with todo steps first; nothing enforces it.
  · probe: decide whether todo steps --run needs an allow-list or a confirmation for a done_check added since the last run
  · added: 2026-10-15

- **td-52 · TODO_DETECTORS replaces the registered detector list for any run that sets it**
  c400088: kept for fixtures and trial runs; said on stderr every time (mutant detect-override-silent)
  · probe: TODO_DETECTORS=/tmp/x.json ./todo detect -> a NOTICE on stderr each time and the list checked as vocab.json's; unproven whether a stray env in a scheduled run could hide S7
  · added: 2026-10-16

- **td-66 · unverified: applies all is read as any location, including folders checks all does not walk**
  tl-311: todolib/practices.applies returns true for applies==all at any folder under the scan root; checks' own cells are per location it discovers.
  · probe: brief an item whose repo is a plain non-git folder under the root, and compare with the locations checks practices --json lists cells for
  · added: 2026-10-19

- **td-72 · unverified: items name this repo both todo and tools/todo, so a --repo filter sees two repos**
  2026-10-19 (tl-378): todo -C <root> list --repo tools/todo lists tl-308 and tl-378 (the top-level store names repo tools/todo), while this store's repo and its own items say todo; stale-plans --repo tools/todo printed 0 pinned sections while --repo todo listed td-24/25/42 as changed. known_repo accepts both because an item names each. A wrong-answer shape: a filter that silently splits one repo in two.
  · probe: todo -C <root> list --repo tools/todo and --repo todo: an item in the first is about this repo; decide whether check or add should map a store path to its repo name, or refuse a repo that is a path to a store named otherwise
  · added: 2026-10-19

- **td-74 · unverified: a write that fails between exports leaves the exports mixed**
  store_documents writes the exports before COMMIT; a raise mid-way rolls todo.db back but leaves the exports already renamed, so a later rebuild from exports reads a mix
  · probe: a test that makes write_file raise on the third export inside store_documents, then reads the four exports' headers
  · work: test
  · added: 2026-10-19

- **td-75 · unverified: migrate in the both state discards exports pulled from another clone**
  Store.convert builds from the JSON files whenever they exist
  · probe: a store with todo.json and pulled exports but no todo.db: run todo migrate, compare the exports before and after
  · work: test
  · added: 2026-10-19

- **td-84 · suspicion: a report item naming the delegation layer's own store would turn the direction audit red, since that store's repo name is also on devtools/audit.json's roster_names list**
  2026-10-20, confirmed in another form: td-85, filed into this store by the delegation layer's report filer during this session's ./dev.sh check, quotes a roster name and the delegation layer's agents folder, and turned the audit part red (audit FAIL at TODO.md:40 and todo.json:1568), which also made test.dev's two CheckJson tests and two mutant baselines red. Reported to that layer's owner in the td-67 report; td-85 left as filed.
  · probe: in a scratch copy, add a report item whose --reported-to is the repo name in the top-level .claude store's header, then run python3 devtools/audit.py there; red means repo names and the roster list collide
  · added: 2026-10-20

- **td-90 · Uncommitted td-67 test, mutants and README text, and a settings.json registering two hooks, sit in the tree with no owner**
  2026-10-20: tree holds uncommitted work no session committed: td-67 (closed in store) README.md hunk at line 206, two mutants practices-unchecked-*-not-exit-3 in devtools/mutants.json, tests/test_practices.py test_an_unchecked_block_leaves_the_exit_code_alone (mtime 00:58-00:59); .claude/settings.json (Oct 18) registering git-funnel.sh and store-guard.sh. Left untouched by td-82's dispatch (commits 6dc62a4, 21bb4df staged around them); the full ./dev.sh check passed 62 of 62 with them in the tree.
  2026-10-22 (td-92): README.md (the todo approve row) and devtools/mutants.json (mutants approve-keeps-approval-wait, approve-ends-any-wait) now also hold td-92's uncommitted hunks, gating commit 910405b; commit.sh stages whole files, so they wait on this item's decision. Both passed: ./dev.sh check 62 of 62 with them in the tree.
  2026-10-23 (td-93): README.md (Decisions paragraph, the untabled footer) and devtools/mutants.json (untabled-footer-bare-count, untabled-footer-repos-unordered, each 1 of 1 red) now also hold td-93's uncommitted hunks, gating commit 4b25289; ./dev.sh check 62 of 62 with them in the tree.
  2026-10-23 (tl-560): README.md (the history row, --json) and devtools/mutants.json (history-json-ignored, history-json-last-ten, history-id-json-ignored, each 1 of 1 red; readme-command-drift re-anchored on the new row end) now hold tl-560's hunks; with todolib/cli.py and tests/test_history.py these are NOT committed: HEAD plus cli.py and the test alone fails tests.test_docs test_readme_command_table_equals_the_parser (ran on a git archive of HEAD), so no green commit of tl-560 exists without README.md whole, which carries td-67/td-92/td-93's hunks. ./dev.sh check 62 of 62 with all of them in the tree. Deciding this item unblocks tl-560's commit.
  · probe: ask the session or Jacob whether to commit them; settings.json is Jacob's to copy
  · work: code
  · size: S
  · files: README.md, devtools/mutants.json, tests/test_practices.py, .claude/settings.json
  · done when: the td-67 files are committed or dropped, and Jacob says whether settings.json's two registrations go in
  · added: 2026-10-20

- **td-98 · unverified: history --repo naming a store the scan could not read says 'no store for repo' (exit 1), not UNCHECKED (exit 3)**
  seen reading cmd_history while doing tl-560: it calls ws.by_repo(args.repo) and raises TodoError on None without consulting ws.errors, where list uses known_repo. Not run.
  · probe: break b/todo.json as tests/test_list_json.py test_an_unreadable_store_is_unchecked_in_either_form does, then run todo -C a --root WS history --repo b and read the exit code
  · work: code
  · size: S
  · added: 2026-10-23

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
  · reported to: setup on 2026-10-04 as su-74
  · work: tooling
  · files: devtools/mutate.py
  · done when: one copy, installed by setup, with the edits list
  · added: 2026-10-04

- **td-25 · get, find and refs cannot be declared in services.json: its schema allows service check or write only**
  tools/checks schema/services.schema.json (commit 96ceef9) has service enum [check, write]; get/find/refs are reads, so declaring them as write would mislabel them. Not declared; README says so. context-hygiene hit the same wall on 2026-10-09. Needs tools/checks to add a read service (or a verbs-only entry) to the schema.
  2026-10-15, PLAN-services.md §3 as it reads today: still stands. Lines 154-161 still put a service's verbs (get/find/refs among them) in its services.json contract; tools/checks schema/services.schema.json still has service enum [check, write] (unchanged since 96ceef9). tools/checks keeps no todo store; its hand TODO.md records td-25 as an open decision (a read service), so the report stays unpaired.
  · reported to: checks on 2026-10-09 (no counterpart yet)
  · work: decision
  · tags: plan:PLAN-services.md§3
  · plan pins: PLAN-services.md§3 as of 2026-10-20 (sha256 aafcbd1fba01)
  · added: 2026-10-09

- **td-36 · checks gate: hooks-installed reports drift on four installed .claude/ files**
  ./dev.sh check, 2026-10-09 (commit after 77bce39): checks gate FAIL hooks-installed: extra-stores.sh (the installed hooks' lib folder), .claude/hooks/store-guard.sh and .claude/hooks/test-store-guard.sh 'drift; not covered by user scope (no shared hook of that name there)', .claude/hooks/test-no-inline-blobs.sh 'drift; not covered by user scope (not registered there)'. Last touched by 93532a8 (re-render of the shared hook copies from tools/hooks). Not this tool's files and not changed by td-22/td-27; reported to the hooks tool's owner through the dispatch report. Also live: ./dev.sh hooks FAIL 'store-guard.sh is not registered in .claude/settings.json' (td-2's remainder; the uncommitted settings.json now registers the other seven). 2026-10-12: the lib file's path is named without its folder here, because that folder in this store tripped the direction audit (audit, no-roster and two test_dev tests red).
  2026-10-15: of setup's Q6 render, test-no-inline-blobs.sh and lib/extra-stores.sh agree with source (hooks copies: ok) and are committed (c5f1886); store-guard.sh and test-store-guard.sh drift from hooks bdd932f and stay uncommitted. Also drift/missing at tools/todo: lib/ledger.sh, prefer-recipes.sh and its test, lib/write-targets.sh (drift); bin/commit.sh, git-funnel.sh and its test (missing). Needs a re-render by setup.
  · reported to: setup on 2026-10-15 as su-75
  · work: labour
  · size: S
  · done when: tools/hooks' hooks copies shows no drift or missing row at tools/todo, and the checks gate's hooks-installed passes
  · added: 2026-10-09

- **td-42 · S3 (verbs on tools/checks for now, PLAN-services.md §3 X4) serves no shared tag vocabulary for todolib to read**
  2026-10-15: PLAN-services.md §3 puts the tag vocabulary in the architecture service (S3); §3 X4 places S3 for now as verbs on tools/checks. `tools/checks/checks --help` lists no verb that serves the vocabulary, and PLAN-architecture.md has no row for it. td-24 (this tool's local copy in vocab.json tags.shared) cannot retire until one exists. Not a fault: unbuilt planned work, recorded so td-24's wait has an owner.
  · reported to: checks on 2026-10-15 (no counterpart yet)
  · work: code
  · done when: tools/checks serves the shared tag vocabulary (the seven namespaces and their closed values) by a verb or file todolib can read
  · tags: plan:PLAN-services.md§3
  · plan pins: PLAN-services.md§3 as of 2026-10-20 (sha256 aafcbd1fba01)
  · added: 2026-10-15

- **td-43 · parts.py exits 0 when a part only said UNCHECKED (exit 3); dev.sh turns it into 3 itself**
  devtools/parts.py (runner 1.3.0) header: a part that exits 3 is unchecked and 'does not make the run red'; exit 0 iff no part failed or errored. Proven 2026-10-15 by mutant check-unchecked-is-green (dev.sh's code=3 set to 0 turns tests.test_hooks_gate red: the runner alone exited 0 with the hooks part UNCHECKED). dev.sh cmd_check reads the run (UNCHK line, or --json unchecked with reason 'exit 3') and exits 3 itself.
  · reported to: checks on 2026-10-15 (no counterpart yet)
  · work: code
  · size: S
  · files: dev.sh, devtools/parts.py
  · done when: parts.py exits 3 when a run part said UNCHECKED and none failed, and dev.sh's said_unchecked wrapper is removed with its mutants
  · added: 2026-10-15

- **td-65 · Practice rows in the brief lack the rule text: checks practices --json omits rule**
  tl-311: checks practices --json --from <report> prints id, part, principle, status, held, applies per row (checkslib/cli.py line 336), no rule; a prose row without held.shows prints only its held text (e.g. 'prose (...)'). Expected: each row's rule.
  · reported to: checks on 2026-10-19 (no counterpart yet)
  · added: 2026-10-19

- **td-69 · unverified: the dispatch ledger files items into this store with roster agent names in their evidence, which this repo's direction audit refuses**
  2026-10-19 (tl-311): td-68 (parent tl-343) arrived uncommitted with two roster names in its evidence; devtools/audit.py failed on todo.json and TODO.md until td-68's evidence was reworded with todo edit. Expected: the filer writes no roster name into a tool's store (or the store owner is told which names to avoid).
  · reported to: .claude on 2026-10-19 (relayed by hand; never pairs)
  · added: 2026-10-19

- **td-78 · unverified: checks' accessor counts a .gitignore entry naming the store as an accessor**
  tools/todo .gitignore names todo.db to keep git off it; accessor counts it; worked around with an exclude in checks.json, held by tests/test_audit.py
  · reported to: checks on 2026-10-19 (no counterpart yet)
  · added: 2026-10-19

## Interim rules

- **td-24 · The tag table in vocab.json is a local copy; read it from the architecture service once it exists**
  PLAN-services.md §3: the vocabulary lives in the architecture service (S3), which does not exist yet. vocab.json tags.shared copies its seven namespaces; tests/test_tags.py holds them equal to the plan's table (mutant shared-namespaces-drift). Closed values (origin: jacob, model, tool; trust: untrusted) are the plan's examples, not a ruling: S3 decides closed values.
  2026-10-12, checked against PLAN-services.md §3 as it reads today: the seven namespaces and their order are unchanged; the plan names kind:, trust: and origin: as closed (a new value goes to the architecture service's agent). Its todo example (todo:td-21 with kind:audit, an origin: naming the plan-writing agent, repo:tools/todo) is out of step with this tool: audit is a work here (todo.work:audit), an agent's name is not a declared origin: value (jacob, model, tool), and repo: is td-26.
  2026-10-15, PLAN-services.md §3 as it reads today: the seven namespaces (repo, plan, kind, origin, trust, status, ref) are unchanged; kind/trust/origin stay closed, the architecture service's to extend. §3 X4: S3 lives for now as verbs on tools/checks; `checks --help` lists no tag-vocabulary verb and PLAN-architecture.md has no row for the vocabulary, so there is nothing to read from yet: status blocked (on S3 serving the vocabulary, not on Jacob). The §3 todo example still carries kind:audit and an origin: naming an agent, both out of step here (audit is a work).
  · status: blocked
  · blocked by: td-42
  · work: code
  · size: M
  · files: vocab.json, todolib/tags.py
  · done when: todolib reads the shared tag vocabulary from the architecture service (S3) instead of vocab.json tags.shared, and tests/test_tags.py Vocabulary compares against S3, not the plan
  · retire: the architecture service (S3) serves the shared vocabulary and todolib reads it from there; tests/test_tags.py Vocabulary then compares against S3, not the plan
  · tags: plan:PLAN-services.md§3
  · plan pins: PLAN-services.md§3 as of 2026-10-20 (sha256 aafcbd1fba01)
  · added: 2026-10-09

- **td-54 · Nothing runs `todo detect` on a schedule yet**
  c400088: detect is manual. Do not run it on this store by hand until it is scheduled: check then fails S7 stale (stale_factor x cadence_hours) once the run ages.
  · retire: a session-start run and an hourly entry exist (reported to their owners)
  · added: 2026-10-16

## Notes

- **td-50 · Step items are kind plan-step, where PLAN-services.md step 6.3 says `step`**
  c400088/f444257: `step` read as any step; plan-step names where it comes from (sync-plans). Jacob to confirm or ask for a rename (vocab.json kinds, one place).
  · work: docs
  · added: 2026-10-16

- **td-51 · Generated decisions recommend yes (vocab.json decisions.generated_recommend)**
  fead4ca: a decision sync-plans generates from a plan carries recommend yes; Jacob may prefer no recommendation. One key to change.
  · work: decision
  · added: 2026-10-16

- **td-53 · `todo show` prints plan_step whole while TODO.md shortens it**
  f444257: render.field_value cuts plan_step text; show prints the JSON field. Harmless, but the two disagree.
  · work: code
  · added: 2026-10-16

- **td-55 · The plan's closed_by is resolution done-detected plus the detector field**
  c400088: PLAN-todo-tool.md §10.5 names closed_by; todo records the closing detector in the item's detector field and resolution done-detected (README Detectors). Jacob to confirm.
  · work: docs
  · added: 2026-10-16

- **td-59 · Readers of the JSON stores move to the CLI or the exports before the switch**
  2026-10-18, todo migrate --readers: 95 lines in 30 files outside this tool name todo.json, todo-history.json or todo-records.json (income, knowledge-base, the job importer's scripts, tools/checks, context-hygiene, hooks, setup, usage, wizard); hidden folders are not read, so the .claude layer's readers (dispatch-guard, report-filer, offload, todo-writes, temp-rules) are listed by their owner, not here. Each was reported to its owner in the tl-268 handoff. (2026-10-19: the importer's folder name is now a roster name, which the direction audit refuses here, so it is described.)
  2026-10-19 (tl-383), todo migrate --readers --root <workspace>: 109 lines in 34 files, 1366 files read, 4 skipped (over 2 MB: two wheels in addon-bench, emailTools/bandcamp_digest.html, knowledge-base/data/kb.sqlite). By repo: tools/checks 46 (checkslib/todocheck.py:21 STORE, source/no-roster.py:44 TODO_STORE, todo-store.py, todo-valid.py, fixtures, tests), income 21 (devtools/ask.py:145 opens todo.json; tests test_ask, test_refs, test_wizard; check.parts.json excepts), tools/hooks 16 (lib/extra-stores.sh:33-34 store list, store-guard.sh and its test), tools/hub 9 (devtools/hubcheck.py:48 REQUIRED, tests/test_hubcheck.py), tools/wizard 6 (wizardlib/stores.py:193 opens todo.json, tests/helpers.py:217), scripts 4 (check.parts.json:41, dev.sh, test_parts_file.py:49), tools/context-hygiene 3 and knowledge-base 2 (excludes), tools/usage 1 (a test asserting absence), tools/setup 1 (fake_todo message). Direct opens: income ask.py, wizard stores.py and helpers.py, income tests; the rest are presence checks, guard lists, excludes and fixtures. Hidden layer not read. Not empty, so no store is converted (PLAN-todo-tool.md §10.6: switch only once the list is empty).
  2026-10-20: todo list --json (beff5a9) is the CLI read the direct openers move to: `todo -C DIR list --json [--status S]`, rows {id, local_id, store, record}, each record the item whole, the same document before and after todo migrate (tests/test_list_json.py). Rescan (todo --root <workspace> migrate --readers): still 109 lines in 34 files, so nothing moved yet. Owner items: tl-293..tl-302 and kb-63 in the top-level store; tools/hub (devtools/hubcheck.py:48 REQUIRED lists todo.json, todo-history.json) has none, reported in this handoff.
  · work: outreach
  · size: M
  · done when: todo migrate --readers lists no reader that opens a JSON store directly (excludes and fixtures aside), and each owner's item is closed
  · handoff: done: todo list --json (beff5a9, pushed) gives readers the open items on either backing; next: income ask.py load_items and wizard stores.py items()/tests helpers.py store_items move to `todo -C DIR list --json`, hub drops todo.json from REQUIRED, then rescan; verify: todo --root <workspace> migrate --readers lists no direct open (2026-10-20, at beff5a9)
  · approved: jacob 2026-10-20: Jacob 2026-10-20 via auto-relay (origin jacob), Dispatch lines 270-284
  · tags: plan:PLAN-todo-tool.md§10.6
  · added: 2026-10-18

- **td-63 · To todo: unverified: sync-plans still reports su-87 stale after todo edit --evidence --pin-plan**
  From setup (tl-285). Probe: todo sync-plans --dry-run PLAN-architecture.md (in tools/setup). Expected: a way to refresh plan_step.text/hash.
  · parent: tl-308
  · work: code
  · done when: stale report clears after re-pin, or the cause is documented
  · added: 2026-10-19

- **td-64 · Brief reads practice rows via a synthetic --from report; switch to a rows-only checks verb when one exists**
  tl-311: todolib/practices.py pipes {repos:[{rel:LOC,results:[]}]} to checks practices --json --from /dev/stdin and reads only .rows (a live run takes ~41 s). Reported to checks: no rows-only verb.
  2026-10-22: still no rows-only verb: checks --help lists none; checks practices --row ID prints measured: live (a run); tools/checks HEAD 0be97db (2026-10-19) and its TODO.md hold no request for one. The synthetic --from read took 3 s and printed 53222 bytes, of which only .rows is read. Reported to checks again from this dispatch.
  · work: code
  · size: S
  · done when: practices.rows calls a checks verb that prints the rows without a run, and tests/test_practices.py passes
  · handoff: done: nothing in code, blocked on tools/checks; next: when checks serves the rows by their own verb (e.g. checks practices --rows --json, no run, no cells), point practices.ARGS at it, drop the --from report, keep the UNCHECKED paths; verify: python3 -m unittest tests.test_practices and ./dev.sh check (2026-10-22, at 0bce7b4)
  · approved: jacob 2026-10-20: Jacob 2026-10-20 via auto-relay (origin jacob), Dispatch lines 270-284
  · added: 2026-10-19

- **td-68 · PLAN-architecture.md §9 step 10.3: your services.json registry draft is in RESEARCH-registry-drafts.md, section `tools/todo`; write it in, then checks one registered**
  Draft by a research session 2026-10-19 (tl-322), read-only: description, stores and shapes for tools/todo, written from its CLAUDE.md and cli.json; validated as written there: checks one registered and checks one services-valid both ok on a git-archive copy of the repo with the draft as services.json, other fields unchanged. stores = cli.json's 3 entries (todo.json, todo-history.json, todo-records.json); no shapes. Open point 5 (whether each repo's todo.json counts as that repo's store) is a planning question that touches this repo's files. Reword the description freely; stores must stay equal to cli.json's store (registered holds them equal both ways). (Agent names reworded 2026-10-19: this store's direction audit refuses roster names.)
  · parent: tl-343
  · done when: services.json in tools/todo carries description, stores and (where any) shapes, and 'checks one registered tools/todo' from tools/checks is ok
  · added: 2026-10-19

- **td-73 · devtools/parts.py here is runner 1.3.0; tools/checks' is 1.4.0 (--jobs)**
  2026-10-19 (tl-378): VERSION in devtools/parts.py is 1.3.0, in tools/checks/checkslib/parts.py 1.4.0; python3 devtools/parts.py usage --json lists run options --resume, --only, --json (no --jobs), while tests/test_handoff.py now pins the shared runner's four. ./dev.sh check runs the local copy. The copy is setup's to re-install; nothing here uses --jobs.
  · work: tooling
  · files: devtools/parts.py
  · done when: devtools/parts.py VERSION equals tools/checks/checkslib/parts.py VERSION
  · added: 2026-10-19

- **td-77 · convert's read-back checks have no mutant: no correct implementation trips them**
  fresh_differences and verify_exports inside Store.convert never differ for a correct build, so no mutant of the build shows them red; tests/test_db.py Move exercises the path, not the refusal
  · work: test
  · added: 2026-10-19

- **td-80 · Run todo migrate on each real store once td-59's readers are gone**
  · blocked by: td-59
  · work: labour
  · done when: todo migrate has run in every repo with a store; no todo.json is left; ./dev.sh check green in each
  · added: 2026-10-19

- **td-81 · PLAN-routing-tree.md §25 says todo ready lists only approved items; it lists approved and unapproved alike**
  2026-10-19 (tl-404, e421281): §25 'A cron prompt is never Jacob's' says todo ready lists only items already approved and unblocked; ready has never filtered on approval (todo dispatchable does). ready --json now carries approved/by_rule/dispatched per row, and tests/test_ready.py holds rows with approved set and dispatched null equal to dispatchable --json's ids. On the workspace store ready --json counted 39. Relayed in the tl-404 dispatch report to the release job's owner: count N from dispatchable --json, or filter ready rows on approved and not dispatched.
  · added: 2026-10-19

- **td-83 · td-67's README reason rests on the dispatch guard reading brief exit codes other than 0/1 as 'todo could not answer'; nothing here can gate it**
  Read .claude/hooks/dispatch-guard.sh lines 309-320 on 2026-10-20: rc 0 holds the prompt to the brief text, rc 1 with NOT READY or a todo: error blocks, any other rc falls back to brief_grammar. This repo reads no delegation-layer file (audit), so the README sentence can go stale unseen; asked that layer's owner (via the td-67 report) to pin it in its own dispatch-guard test.
  · added: 2026-10-20

- **td-95 · Decisions count: todo decisions --json writes a table, so the status line shows decisions ? until todo offers a read-only form**
  tl-547: tools/todo/todolib/cli.py cmd_decisions records a new dt-N table (store.tables append + commit) whenever the open rows differ from every recorded table, and cmd_answer with no dt-N and no --table answers decide.latest_table. A status line refresh calling 'todo decisions --json' would therefore record tables Jacob never saw and could put his next bare '1) yes' under one of them. So statusline.counts.sources decisions ships args null and the line shows 'decisions ?'. Reported to todo through the tl-547 hand-back.
  · parent: ch-89
  · work: code
  · files: hygiene.json, hygienelib/counts.py
  · done when: todo offers a read-only form of the decisions table (e.g. todo decisions --json --no-record) that records nothing; then statusline.counts.sources decisions gets those args, files:counts:decisions is ok, and tests/test_statusline.py CountsAsShipped's decisions test is changed to the new args
  · added: 2026-10-22
