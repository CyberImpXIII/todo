<!-- rendered by todo from todo.json (25 open, 32 closed in todo-history.json; seal f5ea562a8307): do not edit by hand, `todo check` fails on a hand edit. Change items with the todo CLI; a hand edit is recovered with `todo import`. -->
# todo TODO

## Own bugs

- **td-41 · todo check has no --json; the checks repo's todo-valid gate reads its text output**
  tools/checks/TODO.md lines 65-66 and 539 (2026-10-04) ask for it; ./todo check --help on 2026-10-13 lists no --json. Seen while importing that TODO.md on a temp copy for PLAN-todo-tool.md §10.2's motivating case.
  · work: code
  · size: S
  · done when: todo check --json prints {ok, failed, warnings} and a test shows a failing item changes it
  · added: 2026-10-13

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

- **td-29 · cli.json declares the stores, so tools/checks' stores-exported now wants a verify verb**
  ./dev.sh check, 2026-10-09, after cli.json was added for the seal (PLAN-todo-tool.md §9): checks gate FAIL stores-exported: 'cli.json: declares no `verify` verb: nothing shows the store's export is current'. That check (tools/checks source/stores-exported.py, PLAN-repo-setup.md §7.11) runs `todo verify --json` against an export in DATA_REPO. This tool has no export and no plan for one; the brief did not ask for it. Hinges on: whether todo stores get an export in the data repo at all (the top level's owner decides), and then `todo export` + `todo verify --json` per schema/verify.schema.json.
  2026-10-15: still red in ./dev.sh check (stores-exported: cli.json declares no verify verb; 'a private one goes in not_exported with why'). tools/checks now offers the not_exported opt-out, so the choice is export or opt out; PLAN-repo-setup.md §7.11 (Jacob, 2026-10-05) does not say whether todo stores are exported. Waits on that answer.
  · status: waiting-jacob
  · waits on: decision:PLAN-repo-setup.md §7.11
  · work: decision
  · size: S
  · done when: the checks gate's stores-exported is ok for this repo: either cli.json lists todo.json and todo-history.json under not_exported with why, or todo export and todo verify --json exist per tools/checks schema/verify.schema.json
  · added: 2026-10-09

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
  · plan pins: PLAN-services.md§3 as of 2026-10-15 (sha256 55621f435a82)
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
  · plan pins: PLAN-services.md§3 as of 2026-10-15 (sha256 55621f435a82)
  · added: 2026-10-15

- **td-43 · parts.py exits 0 when a part only said UNCHECKED (exit 3); dev.sh turns it into 3 itself**
  devtools/parts.py (runner 1.3.0) header: a part that exits 3 is unchecked and 'does not make the run red'; exit 0 iff no part failed or errored. Proven 2026-10-15 by mutant check-unchecked-is-green (dev.sh's code=3 set to 0 turns tests.test_hooks_gate red: the runner alone exited 0 with the hooks part UNCHECKED). dev.sh cmd_check reads the run (UNCHK line, or --json unchecked with reason 'exit 3') and exits 3 itself.
  · reported to: checks on 2026-10-15 (no counterpart yet)
  · work: code
  · size: S
  · files: dev.sh, devtools/parts.py
  · done when: parts.py exits 3 when a run part said UNCHECKED and none failed, and dev.sh's said_unchecked wrapper is removed with its mutants
  · added: 2026-10-15

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
  · plan pins: PLAN-services.md§3 as of 2026-10-15 (sha256 55621f435a82)
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
