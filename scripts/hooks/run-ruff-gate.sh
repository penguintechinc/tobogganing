#!/usr/bin/env bash
# run-ruff-gate.sh — ruff check against hub_api/, gated on NEW violations only.
#
# hub_api/ruff-baseline.txt tracks 229 pre-existing (file, code, message)
# violations discovered 2026-09-25 when `ruff check hub_api/ || true` in the
# Makefile was un-masked (see release/v1.2.X gate-integrity fix). Full-tree
# `make lint` was never gated before, so files untouched since ruff's adoption
# accumulated debt that the pre-commit `ruff --fix` hook (which only lints
# staged files per commit) never touched. Fixing all 256 raw findings is out
# of scope here — this gates the backlog shut (no more accumulation) without
# blocking on it. GATE DEBT: see hub_api/ruff-baseline.txt for the tracked
# backlog; shrink it opportunistically, never bulk-suppress.
#
# Line/column numbers are intentionally excluded from the comparison key
# (same tradeoff mypy-baseline makes) so unrelated line shifts elsewhere in a
# file don't spuriously register as "new" or "fixed".
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

BASELINE="hub_api/ruff-baseline.txt"
CURRENT="$(mktemp)"
NEW="$(mktemp)"

command -v ruff >/dev/null 2>&1 || {
  echo "ruff not installed — required Python linter (org standard: ruff only, never flake8/black)" >&2
  exit 1
}

# `ruff check` exits non-zero whenever it finds ANY violation (including
# already-baselined ones) — that is expected here, not a masked failure, so
# it is deliberately not gated on pipefail; the comm/diff check below is the
# real gate, run on this same output, same invocation.
RAW="$(mktemp)"
trap 'rm -f "$CURRENT" "$NEW" "$RAW"' EXIT
ruff check hub_api/ --output-format=json > "$RAW" || true
python3 "$(dirname "${BASH_SOURCE[0]}")/normalize_ruff_json.py" < "$RAW" > "$CURRENT"

touch "$BASELINE"
comm -13 <(sort "$BASELINE") <(sort "$CURRENT") > "$NEW"

if [ -s "$NEW" ]; then
  echo "NEW ruff violations not in $BASELINE (must fix, not baseline):"
  cat "$NEW"
  exit 1
fi

echo "ruff check: 0 new violations ($(wc -l < "$BASELINE" | tr -d ' ') baselined, tracked in $BASELINE)"
