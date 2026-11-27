#!/usr/bin/env bash
# test-check-no-stubs.sh — proves check-no-stubs.sh can pass AND fail.
# Builds throwaway fixture trees: clean (PASS), stubbed (FAIL), allowlisted (PASS), empty (FAIL).
set -euo pipefail

GATE="$(cd "$(dirname "$0")" && pwd)/check-no-stubs.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failures=0; cases=0

# expect <name> <expected-rc> <root>
expect() {
  local name="$1" want="$2" root="$3" got=0
  cases=$((cases+1))
  bash "$GATE" "$root" > "$work/$name.log" 2>&1 || got=$?
  if [[ "$want" == 0 && "$got" == 0 ]] || [[ "$want" != 0 && "$got" != 0 ]]; then
    echo "ok   $name (rc=$got)"
  else
    echo "FAIL $name: want rc=$want got rc=$got"; cat "$work/$name.log"; failures=$((failures+1))
  fi
}

mk() { mkdir -p "$(dirname "$1")"; printf '%s\n' "$2" > "$1"; }

clean="$work/clean"
mk "$clean/hub_api/ok.py" 'def f() -> int:'$'\n''    return 1'
mk "$clean/portal/src/A.tsx" '<input placeholder="e.g. host" className="placeholder-slate-500" />'
mk "$clean/hub_api/tests/test_x.py" '# TODO: tests are excluded'
mk "$clean/engines/x/err.rs" 'return Err(ApiError::X("HTTP/3 not yet implemented".into()));'
: > "$clean/.stubs-allowlist"
expect clean 0 "$clean"

stub="$work/stub"; cp -r "$clean" "$stub"
mk "$stub/hub_api/bad.py" '# TODO: implement this'
mk "$stub/services/x/p.py" 'def g():'$'\n''    pass  # Placeholder for lookup'
expect stubbed 1 "$stub"

allowed="$work/allowed"; cp -r "$stub" "$allowed"
printf 'hub_api/bad.py\tTODO: implement\tfixture\tfixture-track\nservices/x/\t*\tfixture\tfixture-track\n' > "$allowed/.stubs-allowlist"
expect allowlisted 0 "$allowed"

noreason="$work/noreason"; cp -r "$stub" "$noreason"
printf 'hub_api/bad.py\tTODO\n' > "$noreason/.stubs-allowlist"
expect allowlist-missing-reason 1 "$noreason"

empty="$work/empty"; mkdir -p "$empty/hub_api"; : > "$empty/.stubs-allowlist"
expect zero-examined 1 "$empty"

echo "no-stubs self-test: ${cases} cases, ${failures} failed"
[[ $cases -gt 0 && $failures -eq 0 ]]
