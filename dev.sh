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

  check      every gate below, in order; 1 if any fails, else 3 if any is UNCHECKED, else 0. [--json] [GATE ...]:
             --json prints {"ok": bool, "gates": {...}} (UNCHECKED is false there; the exit code tells it from a
             FAIL); named gates run alone, in the order given (tests/test_dev.py, tests/test_hooks_gate.py)
  test       the unit tests (tests/), trimmed to the result unless something fails
  hooks      the shared hook copies: present, executable, parse, their own tests pass (a test's exit 3: UNCHECKED,
             gate exit 3); registered once settings.json exists
  files      the files the tool needs: present, executable where they must be, data parses
  audit      the direction audit (devtools/audit.py): nothing reads the delegation layer or names a roster agent
  self       todo check on this repo's own store (its TODO.md is the render of the store)
  checks     tools/checks' `checks run .` with the roster-name copy in devtools/audit.json; red on any
             fail, and when no-roster did not run or ran without the names (devtools/checks_gate.py)
  mutants    break each gate once in a throwaway copy, require red (devtools/mutants.json)
EOF
}

cmd_test() {
  local out code
  out=$(python3 -m unittest discover -s tests -t . 2>&1); code=$?
  if [ $code -ne 0 ]; then printf '%s\n' "$out"; else printf '%s\n' "$out" | grep -E '^(Ran|OK)' | paste -sd' ' -; fi
  return $code
}

# A hook's own test answers like a gate: 0 pass, 3 UNCHECKED (it could not run here,
# e.g. no site-scrapers above a lone clone), anything else FAIL. An UNCHECKED test is
# named with its reason and makes the gate exit 3: never a pass, never a FAIL; a FAIL
# anywhere still makes it 1 (tests/test_hooks_gate.py).
cmd_hooks() {
  local fails=0 unchecked=0 n=0 h name t out code why settings=".claude/settings.json"
  local registered=1
  if [ ! -f "$settings" ]; then
    registered=0
    echo "  NOTE  $settings absent: the hooks are not live here until Jacob copies .claude/settings.proposed.json over it (TODO.md)"
  elif ! jq -e . "$settings" >/dev/null 2>&1; then
    echo "  FAIL  $settings does not parse"; return 1
  fi
  for h in .claude/hooks/*.sh; do
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
  echo "  ok    hooks: $n hooks, each executable and passing its own test$([ $registered -eq 1 ] && echo ', registered')"
  return 0
}

cmd_files() {
  local fails=0 f
  for f in todo dev.sh devtools/audit.py devtools/mutate.py devtools/checks_gate.py; do
    [ -x "$f" ] || { echo "  FAIL  $f missing or not executable"; fails=$((fails+1)); }
  done
  for f in vocab.json devtools/audit.json devtools/mutants.json checks.json cli.json; do
    jq -e . "$f" >/dev/null 2>&1 || { echo "  FAIL  $f missing or does not parse"; fails=$((fails+1)); }
  done
  for f in CLAUDE.md README.md TODO.md .gitignore todolib/__init__.py; do
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

cmd_check() {
  local json=0 g code fails=0 unchecked=0 results="" run=()
  [ "${1:-}" = "--json" ] && { json=1; shift; }
  for g in "$@"; do
    case " ${GATES[*]} " in *" $g "*) run+=("$g") ;; *) echo "check: unknown gate '$g' (gates: ${GATES[*]})" >&2; return 2 ;; esac
  done
  [ ${#run[@]} -eq 0 ] && run=("${GATES[@]}")
  # A check inside a check (tests/test_dev.py runs one) never runs the tests or the
  # mutants again: either would run that test again, and so on without end.
  if [ -n "${TODO_DEV_CHECK:-}" ]; then
    case " ${run[*]} " in *" test "*|*" mutants "*)
      echo "check: refusing test/mutants inside another ./dev.sh check (TODO_DEV_CHECK is set): name the gates to run" >&2; return 2 ;;
    esac
  fi
  export TODO_DEV_CHECK=1
  for g in "${run[@]}"; do
    if [ $json -eq 1 ]; then "cmd_$g" >/dev/null 2>&1; code=$?
    else echo "== $g"; "cmd_$g"; code=$?; fi
    # Exit 3 is a gate that could not check here (cmd_hooks): not green, not FAILED.
    if [ $code -eq 3 ]; then unchecked=$((unchecked+1)); elif [ $code -ne 0 ]; then fails=$((fails+1)); fi
    results="$results\"$g\": $([ $code -eq 0 ] && echo true || echo false), "
  done
  if [ $json -eq 1 ]; then
    printf '{"ok": %s, "gates": {%s}}\n' "$([ $((fails + unchecked)) -eq 0 ] && echo true || echo false)" "${results%, }"
  elif [ $((fails + unchecked)) -eq 0 ]; then echo "check: all ${#run[@]} gates green"
  else
    echo "check: $fails of ${#run[@]} gates FAILED$([ $unchecked -gt 0 ] && echo ", $unchecked UNCHECKED (did not run here, not a pass)")"
  fi
  [ $fails -gt 0 ] && return 1
  [ $unchecked -gt 0 ] && return 3
  return 0
}

case "${1:-}" in
  check)   shift; cmd_check "$@" ;;
  test)    cmd_test ;;
  hooks)   cmd_hooks ;;
  files)   cmd_files ;;
  audit)   cmd_audit ;;
  self)    cmd_self ;;
  checks)  cmd_checks ;;
  mutants) shift; cmd_mutants "$@" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; usage; exit 2 ;;
esac
