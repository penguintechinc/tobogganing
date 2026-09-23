#!/usr/bin/env bash
# run-semgrep.sh — run semgrep SAST against the Python source, fully isolated.
#
# `uvx` resolves the pinned semgrep wheel from PyPI into its own ephemeral,
# cached venv — never the app's environment. This matters because semgrep
# pins `opentelemetry-sdk~=1.37.0`; if it is instead run from an environment
# that also has hub_api's newer opentelemetry-sdk, semgrep crashes on import
# (`cannot import name 'LogData' from 'opentelemetry.sdk._logs'`) before it
# ever scans a file — see the 2026-09-21 security audit. Never add semgrep or
# opentelemetry to hub_api/requirements*.txt to "fix" this — isolation is the
# fix; sharing the environment is the bug.
#
# Usage: run-semgrep.sh   (invoked by pre-commit at the pre-push stage, or
#                           directly via `make test-security`)
set -euo pipefail

SEMGREP_VERSION="1.177.0"
TARGETS=(hub_api engines)

echo "Running semgrep ${SEMGREP_VERSION} (isolated via uvx) against: ${TARGETS[*]}"
uvx --from "semgrep==${SEMGREP_VERSION}" semgrep scan --config auto --error "${TARGETS[@]}"
