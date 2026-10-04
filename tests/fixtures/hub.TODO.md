# hub TODO

## Own bugs

- **`./dev.sh check` is still the setup stub** (deep-work, 2026-10-04): it fails by
  design until the hub is built. The one seam this repo has today, `docs/inputs/`
  against `docs/inputs/SHA256SUMS` and against the brief's §2 list, is checked only by
  hand (`shasum -a 256 -c docs/inputs/SHA256SUMS`, 13 OK on 2026-10-04 after the
  second copy). The first real `check` should run that, plus "every file the brief's
  §2 names is present" and "the README's table lists exactly the files in SHA256SUMS".
- **`docs/inputs/claudeTest-CLAUDE.md` is behind its original** (deep-work,
  2026-10-04): the top-level `CLAUDE.md` changed after the copy, two lines, both repo
  lists (tools/setup's origin now exists; addon-bench and setup named in the git
  section). None of the sections the brief's §2 cites changed, so the snapshot was
  kept. Refresh it, and its SHA256SUMS line, if those sections change before the
  cloud session runs. Probe: `diff docs/inputs/claudeTest-CLAUDE.md ../../CLAUDE.md`.

## Open decisions

- **`.claude/settings.json` is absent** (Jacob's step): the three shared hooks are
  installed but not registered, so they do not fire here, in a local session or a
  cloud one. setup wrote `.claude/settings.proposed.json` (untracked); applying it is
  `cp .claude/settings.proposed.json .claude/settings.json`.

## Unconfirmed suspicions

- **The cloud session may lack inputs it needs** (deep-work, 2026-10-04):
  `PLAN-repo-setup.md` and `PLAN-portable-env.md` were added to the brief's §2 and
  copied (second commit, same day). Still cited but not listed or copied:
  `PLAN-context-hygiene.md` (6 mentions), `PLAN-knowledge-base.md` (4),
  `PLAN-applications.md` (1). Probe: whether `PLAN-hub.md` comes back with open
  pointers to them.

## Reported to other owners

- **setup** (via the dispatcher, 2026-10-04): it leaves `.claude/settings.proposed.json`
  untracked with no `.gitignore` entry, so a new repo never reads clean and a
  `git add -A` would commit the proposal; and it writes no `.gitignore` at all, though
  this repo's plan (routing-tree §7) puts a token in `local.env`.
