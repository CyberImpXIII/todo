#!/usr/bin/env bash
# The one pre-commit command for this repo: ./dev.sh check
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 2

usage() {
  cat <<'EOF'
./dev.sh <command>

  check      every gate below, in order; non-zero if any fails (--json: {"ok": bool, "gates": {...}})
  test       the unit tests (tests/), trimmed to the result unless something fails
  hooks      the shared hook copies: present, executable, parse, their own tests pass; registered once settings.json exists
  files      the files the tool needs: present, executable where they must be, data parses
  audit      the direction audit (devtools/audit.py): nothing reads the delegation layer or names a roster agent
  self       todo check on this repo's own store (its TODO.md is the render of todo.json)
  mutants    break each gate once in a throwaway copy, require red (devtools/mutants.json)
EOF
}

cmd_test() {
  local out code
  out=$(python3 -m unittest discover -s tests -t . 2>&1); code=$?
  if [ $code -ne 0 ]; then printf '%s\n' "$out"; else printf '%s\n' "$out" | grep -E '^(Ran|OK)' | paste -sd' ' -; fi
  return $code
}

cmd_hooks() {
  local fails=0 h name t out settings=".claude/settings.json"
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
    if [ $registered -eq 1 ]; then
      jq -e --arg n "$name" '[.hooks[][].hooks[].command | select(endswith("/" + $n))] | length > 0' \
        "$settings" >/dev/null || { echo "  FAIL  $name is not registered in $settings"; fails=$((fails+1)); }
    fi
    t=".claude/hooks/test-$name"
    if [ ! -f "$t" ]; then echo "  FAIL  $name has no test-$name"; fails=$((fails+1)); continue; fi
    if ! out=$(bash "$t" 2>&1); then
      echo "  FAIL  test-$name:"; printf '%s\n' "$out" | grep -E 'FAIL' | sed 's/^/        /'; fails=$((fails+1))
    fi
  done
  [ $fails -eq 0 ] && echo "  ok    hooks: $(ls .claude/hooks/*.sh | grep -vc /test-) hooks, each executable and passing its own test$([ $registered -eq 1 ] && echo ', registered')"
  return $((fails > 0))
}

cmd_files() {
  local fails=0 f
  for f in todo dev.sh devtools/audit.py devtools/mutate.py; do
    [ -x "$f" ] || { echo "  FAIL  $f missing or not executable"; fails=$((fails+1)); }
  done
  for f in vocab.json devtools/audit.json devtools/mutants.json todo.json todo-history.json; do
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

cmd_mutants() { python3 devtools/mutate.py "$@"; }

GATES=(test hooks files audit self mutants)

cmd_check() {
  local json=0 g code fails=0 results=""
  [ "${1:-}" = "--json" ] && json=1
  for g in "${GATES[@]}"; do
    if [ $json -eq 1 ]; then "cmd_$g" >/dev/null 2>&1; code=$?
    else echo "== $g"; "cmd_$g"; code=$?; fi
    [ $code -ne 0 ] && fails=$((fails+1))
    results="$results\"$g\": $([ $code -eq 0 ] && echo true || echo false), "
  done
  if [ $json -eq 1 ]; then
    printf '{"ok": %s, "gates": {%s}}\n' "$([ $fails -eq 0 ] && echo true || echo false)" "${results%, }"
  else
    [ $fails -eq 0 ] && echo "check: all ${#GATES[@]} gates green" || echo "check: $fails of ${#GATES[@]} gates FAILED"
  fi
  return $((fails > 0))
}

case "${1:-}" in
  check)   shift; cmd_check "$@" ;;
  test)    cmd_test ;;
  hooks)   cmd_hooks ;;
  files)   cmd_files ;;
  audit)   cmd_audit ;;
  self)    cmd_self ;;
  mutants) shift; cmd_mutants "$@" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; usage; exit 2 ;;
esac
