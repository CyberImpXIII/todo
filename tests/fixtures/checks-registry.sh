#!/bin/sh
# The real checks CLI ($CHECKS_REAL) reading a fixture practice registry
# ($CHECKS_REGISTRY) in place of its gates.json: tests/test_practices.py hands
# this to `todo brief --checks-cli`, so the brief is tested against the checks
# tool's own output, not a stub that agrees with todolib by construction.
[ -n "${CHECKS_REAL:-}" ] && [ -n "${CHECKS_REGISTRY:-}" ] || { echo "checks-registry.sh: CHECKS_REAL and CHECKS_REGISTRY are needed" >&2; exit 2; }
exec "$CHECKS_REAL" "$@" --registry "$CHECKS_REGISTRY"
