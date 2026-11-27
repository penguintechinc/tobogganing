#!/usr/bin/env bash
# check-no-stubs.sh — fatal no-stubs gate (enforcing-no-stubs skill).
# Scans shipped source for stub markers; every hit must match .stubs-allowlist.
# Usage: check-no-stubs.sh [ROOT]   (ROOT defaults to repo root)
set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel)}"
ALLOWLIST="${STUBS_ALLOWLIST:-$ROOT/.stubs-allowlist}"
SCAN_DIRS=(hub_api services engines agents portal shared jobs k8s/helm)
# Case-sensitive markers + case-insensitive stub phrases.
PATTERN='\b(TODO|FIXME|XXX|STUB)\b|NotImplementedError|unimplemented!|todo!\('
# "placeholder=" / "placeholder-" are HTML attrs / CSS classes, not stubs.
PATTERN_I='\bplaceholder([^=a-z-]|$)|stub(bed)? (implementation|response|data|value|result)|stub always|not (yet )?implemented'

cd "$ROOT"
[[ -f "$ALLOWLIST" ]] || { echo "FAIL: allowlist $ALLOWLIST missing"; exit 2; }

existing=()
for d in "${SCAN_DIRS[@]}"; do
  if [[ -d "$d" ]]; then existing+=("$d"); fi
done
[[ ${#existing[@]} -gt 0 ]] || { echo "FAIL: none of the scan dirs exist under $ROOT"; exit 1; }

files_list="$(mktemp)"
hits="$(mktemp)"
trap 'rm -f "$files_list" "$hits"' EXIT

find "${existing[@]}" \
  \( -name node_modules -o -name target -o -name vendor -o -name .worktrees -o -name dist -o -name build \
     -o -name __pycache__ -o -name tests -o -name test -o -name __tests__ -o -name mocks -o -name __mocks__ \
     -o -name testdata -o -name generated -o -name gen \) -prune -o -type f \
  \( -name '*.py' -o -name '*.go' -o -name '*.rs' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' \
     -o -name '*.jsx' -o -name '*.sh' -o -name 'values*.yaml' \) -print \
  | { grep -Ev '(_test\.go|/test_[^/]*\.py|_test\.py|conftest\.py|\.test\.[jt]sx?|\.spec\.[jt]sx?|_pb2(_grpc)?\.pyi?|\.pb\.go|\.min\.js|/mock[^/]*\.(py|go|ts|js))$' || true; } \
  | sort > "$files_list"

examined=$(wc -l < "$files_list" | tr -d ' ')
echo "no-stubs: examined ${examined} files in: ${existing[*]}"
[[ "$examined" -gt 0 ]] || { echo "FAIL: zero files examined"; exit 1; }

set +e
tr '\n' '\0' < "$files_list" | xargs -0 grep -nHE "$PATTERN" > "$hits"
rc=$?
# Fail-loud error constructions ("not yet implemented" returned as an error) are compliant.
FAIL_LOUD='Err\(|Errorf|errors\.New|#\[error|raise [A-Za-z]|\.Error = |ApiError'
tr '\n' '\0' < "$files_list" | xargs -0 grep -nHiE "$PATTERN_I" | grep -vE "$FAIL_LOUD" >> "$hits"
rc2=${PIPESTATUS[1]}
[[ $rc2 -gt $rc ]] && rc=$rc2
set -e
# xargs returns 123 when any grep found nothing in a batch; >123 is a real error.
if [[ $rc -ne 0 && $rc -ne 1 && $rc -ne 123 ]]; then echo "FAIL: grep error rc=$rc"; exit 1; fi

total=0; bad=0; allowed=0
while IFS= read -r hit; do
  total=$((total+1))
  file="${hit%%:*}"; rest="${hit#*:}"; lineno="${rest%%:*}"; text="${rest#*:}"
  # Rust: skip markers inside the trailing #[cfg(test)] module (test code).
  if [[ "$file" == *.rs ]]; then
    tstart=$(grep -n -m1 '^[[:space:]]*#\[cfg(test)\]' "$file" | cut -d: -f1 || true)
    if [[ -n "$tstart" && "$lineno" -gt "$tstart" ]]; then total=$((total-1)); continue; fi
  fi
  ok=0
  while IFS=$'\t' read -r apath aregex areason atrack; do
    [[ -z "$apath" || "$apath" == \#* ]] && continue
    [[ -n "${areason:-}" && -n "${atrack:-}" ]] || { echo "FAIL: allowlist entry '$apath' lacks reason/tracking"; exit 1; }
    if [[ "$file" == "$apath" || ( "$apath" == */ && "$file" == "$apath"* ) ]]; then
      if [[ "$aregex" == "*" ]] || grep -qE -- "$aregex" <<<"$text"; then ok=1; break; fi
    fi
  done < "$ALLOWLIST"
  if [[ $ok -eq 1 ]]; then allowed=$((allowed+1)); else bad=$((bad+1)); echo "STUB: $hit"; fi
done < <(sort -u "$hits")

echo "no-stubs: ${total} markers, ${allowed} allowlisted, ${bad} unallowlisted"
if [[ $bad -gt 0 ]]; then
  echo "FAIL: implement it, fail loud, or add to .stubs-allowlist (path<TAB>regex<TAB>reason<TAB>tracking)"
  exit 1
fi
echo "PASS"
