#!/usr/bin/env bash
# The one pre-commit command for this repo: ./dev.sh check
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 2

# tools/checks, a sibling repo (td-12). Resolved once to an absolute path and
# exported, so a copy of this repo (tests, mutants) reaches the same CLI;
# CHECKS_CLI names another. Absent, the checks gate is red, never skipped.
if [ -z "${CHECKS_CLI:-}" ] && [ -x ../checks/checks ]; then CHECKS_CLI="$(cd ../checks && pwd -P)/checks"; fi
export CHECKS_CLI="${CHECKS_CLI:-}"

usage() {
  cat <<'EOF'
./dev.sh <command>

  check      check.parts.json through devtools/parts.py, the shared runner (setup's copy of tools/checks'):
             one part per tests/test_*.py module, then the gates below, each with its own timeout and
             recorded as it ends ($PROGRESS_FILE, default .progress/check.json). [--json] [--resume |
             --only PART ...]: the runner's options; --json is one check-json document, one check per part.
             Exit 1 if a part fails, else 3 if one said UNCHECKED (exit 3; the runner alone exits 0), else 0.
             CHECK_PARTS names another parts file (tests/test_parts_file.py, tests/test_dev.py)
  test       the unit tests (tests/), trimmed to the result unless something fails; test PART ...: those
             parts alone (check --only PART ...)
  hooks      the shared hook copies: present, executable, parse, their own tests pass (a test's exit 3: UNCHECKED,
             gate exit 3); registered once settings.json exists. hooks NAME.sh ...: those hooks alone, the
             check's hooks.NAME parts, one per hook (an unknown NAME: FAIL)
  files      the files the tool needs: present, executable where they must be, data parses
  audit      the direction audit (devtools/audit.py): nothing reads the delegation layer or names a roster agent
  self       todo check on this repo's own store (its TODO.md is the render of the store)
  checks     tools/checks' `checks run .` with the roster-name copy in devtools/audit.json; red on any
             fail, and when no-roster did not run or ran without the names (devtools/checks_gate.py)
  mutants    break each gate once in a throwaway copy, require red (devtools/mutants.json)
EOF
}

cmd_test() {
  local out code p only=()
  if [ "$#" -gt 0 ]; then
    for p in "$@"; do only+=(--only "$p"); done
    cmd_check "${only[@]}"; return
  fi
  out=$(python3 -m unittest discover -s tests -t . 2>&1); code=$?
  if [ $code -ne 0 ]; then printf '%s\n' "$out"; else printf '%s\n' "$out" | grep -E '^(Ran|OK)' | paste -sd' ' -; fi
  return $code
}

# A hook's own test answers like a gate: 0 pass, 3 UNCHECKED (it could not run here,
# e.g. no site-scrapers above a lone clone), anything else FAIL. An UNCHECKED test is
# named with its reason and makes the gate exit 3: never a pass, never a FAIL; a FAIL
# anywhere still makes it 1 (tests/test_hooks_gate.py).
# hooks NAME.sh ...: those hooks alone (each with its test file), so check.parts.json
# gives every hook a part of its own and no one part runs every hook test (td-82); a
# NAME that is not a hook in .claude/hooks is a FAIL, never an empty pass.
cmd_hooks() {
  local fails=0 unchecked=0 n=0 h name t out code why settings=".claude/settings.json"
  local registered=1 a files=() label=""
  if [ ! -f "$settings" ]; then
    registered=0
    echo "  NOTE  $settings absent: the hooks are not live here until Jacob copies .claude/settings.proposed.json over it (TODO.md)"
  elif ! jq -e . "$settings" >/dev/null 2>&1; then
    echo "  FAIL  $settings does not parse"; return 1
  fi
  if [ "$#" -eq 0 ]; then
    files=(.claude/hooks/*.sh)
  else
    for a in "$@"; do
      case "$a" in
        test-*|*/*|.*|"") echo "  FAIL  hooks: '$a' is not a hook's file name in .claude/hooks"; fails=$((fails+1)); continue ;;
      esac
      if [ ! -f ".claude/hooks/$a" ] || [ "${a%.sh}" = "$a" ]; then
        echo "  FAIL  hooks: no hook $a in .claude/hooks"; fails=$((fails+1)); continue
      fi
      files+=(".claude/hooks/$a")
      [ -f ".claude/hooks/test-$a" ] && files+=(".claude/hooks/test-$a")
    done
    label=" ($*)"
  fi
  for h in ${files[@]+"${files[@]}"}; do
    name=$(basename "$h")
    [ -x "$h" ] || { echo "  FAIL  $name is not executable"; fails=$((fails+1)); }
    bash -n "$h" 2>/dev/null || { echo "  FAIL  $name does not parse"; fails=$((fails+1)); }
    case "$name" in test-*) continue ;; esac
    n=$((n+1))
    if [ $registered -eq 1 ]; then
      jq -e --arg n "$name" '[.hooks[][].hooks[].command | select(endswith("/" + $n))] | length > 0' \
        "$settings" >/dev/null || { echo "  FAIL  $name is not registered in $settings"; fails=$((fails+1)); }
    fi
    t=".claude/hooks/test-$name"
    if [ ! -f "$t" ]; then echo "  FAIL  $name has no test-$name"; fails=$((fails+1)); continue; fi
    out=$(bash "$t" </dev/null 2>&1); code=$?
    if [ $code -eq 3 ]; then
      why=$(printf '%s\n' "$out" | grep -m1 -E '^[[:space:]]*UNCHECKED' | sed -E 's/^[[:space:]]*UNCHECKED:?[[:space:]]*//')
      echo "  UNCHECKED  test-$name: ${why:-exit 3 without saying why}"; unchecked=$((unchecked+1))
    elif [ $code -ne 0 ]; then
      echo "  FAIL  test-$name: exit $code"; printf '%s\n' "$out" | grep -E 'FAIL' | sed 's/^/        /'; fails=$((fails+1))
    fi
  done
  [ $fails -gt 0 ] && return 1
  if [ $unchecked -gt 0 ]; then
    echo "  note  hooks: $((n - unchecked)) of $n passed their own test; $unchecked UNCHECKED (did not run here, not a pass)"
    return 3
  fi
  echo "  ok    hooks: $n hooks$label, each executable and passing its own test$([ $registered -eq 1 ] && echo ', registered')"
  return 0
}

cmd_files() {
  local fails=0 f
  for f in todo dev.sh devtools/audit.py devtools/mutate.py devtools/checks_gate.py; do
    [ -x "$f" ] || { echo "  FAIL  $f missing or not executable"; fails=$((fails+1)); }
  done
  for f in vocab.json devtools/audit.json devtools/mutants.json checks.json cli.json check.parts.json; do
    jq -e . "$f" >/dev/null 2>&1 || { echo "  FAIL  $f missing or does not parse"; fails=$((fails+1)); }
  done
  for f in CLAUDE.md README.md TODO.md .gitignore todolib/__init__.py devtools/parts.py; do
    [ -f "$f" ] || { echo "  FAIL  $f missing"; fails=$((fails+1)); }
  done
  ./todo --help >/dev/null 2>&1 || { echo "  FAIL  ./todo --help does not run"; fails=$((fails+1)); }
  [ $fails -eq 0 ] && echo "  ok    files: present, executable and parsing"
  return $((fails > 0))
}

cmd_audit() { python3 devtools/audit.py; }

cmd_self() { ./todo -C . check; }

cmd_checks() {
  local names out code
  if [ -z "$CHECKS_CLI" ] || [ ! -x "$CHECKS_CLI" ]; then
    echo "  FAIL  checks: no checks CLI ('${CHECKS_CLI}'; looked for ../checks/checks, the sibling repo tools/checks; CHECKS_CLI names another)"
    return 1
  fi
  # The roster names come from this repo's own copy (devtools/audit.json), never the roster (td-4).
  names=$(jq -r '.roster_names | join(",")' devtools/audit.json 2>/dev/null)
  if [ -z "$names" ]; then echo "  FAIL  checks: no roster_names in devtools/audit.json to pass to no-roster"; return 1; fi
  out=$("$CHECKS_CLI" run . --json --names "$names" 2>&1); code=$?
  printf '%s' "$out" | python3 devtools/checks_gate.py "$code"
}

cmd_mutants() { python3 devtools/mutate.py "$@"; }

GATES=(test hooks files audit self checks mutants)

# The parts are check.parts.json (CHECK_PARTS names another), run by the shared runner;
# its options pass through. Two things are this repo's own:
#  - A check inside a check (tests/test_dev.py runs one) runs only parts named with
#    --only, and never a test.* part or the mutants: either would run that test again,
#    and so on without end (td-11). A foreign suite (CHECK_PARTS) is not this repo's
#    tests, so the guard leaves it alone (tools/checks' check-partial hands one in).
#  - The runner exits 0 when a part only said UNCHECKED (its exit 3). This check exits 3
#    then, so a part that could not run here is never green by exit code; a part --only
#    left out is not one of those (tests/test_parts_file.py Unchecked).
cmd_check() {
  local a only=0 heavy=0 json=0 out code
  for a in "$@"; do
    case "$a" in --only) only=1 ;; --json) json=1 ;; test.*|mutants) heavy=1 ;; esac
  done
  if [ -z "${CHECK_PARTS:-}" ] && [ -n "${TODO_DEV_CHECK:-}" ] && { [ $only -eq 0 ] || [ $heavy -eq 1 ]; }; then
    echo "check: refusing test/mutants inside another ./dev.sh check (TODO_DEV_CHECK is set): name the other parts to run (--only PART)" >&2
    return 2
  fi
  export TODO_DEV_CHECK=1
  out=$(mktemp "${TMPDIR:-/tmp}/todo-check.XXXXXX") || return 2
  python3 devtools/parts.py run "${CHECK_PARTS:-check.parts.json}" "$@" | tee "$out"; code=${PIPESTATUS[0]}
  if [ "$code" -eq 0 ] && said_unchecked "$json" "$out"; then code=3; fi
  rm -f "$out"
  return "$code"
}

# said_unchecked JSON FILE: did a part of the run in FILE exit 3 (UNCHECKED)? Text: the
# runner's `UNCHK <part>` line; --json: a check `unchecked` for `exit 3: <why>`, not one
# merely not run.
said_unchecked() {
  if [ "$1" -eq 1 ]; then
    jq -e '[.checks[] | select(.status == "unchecked" and ((.reason // "") | startswith("exit 3")))] | length > 0' "$2" >/dev/null 2>&1
  else
    grep -q '^UNCHK ' "$2"
  fi
}

case "${1:-}" in
  check)   shift; cmd_check "$@" ;;
  test)    shift; cmd_test "$@" ;;
  hooks)   shift; cmd_hooks "$@" ;;
  files)   cmd_files ;;
  audit)   cmd_audit ;;
  self)    cmd_self ;;
  checks)  cmd_checks ;;
  mutants) shift; cmd_mutants "$@" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; usage; exit 2 ;;
esac
