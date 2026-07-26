#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PROJECT_NAME="$(basename "$REPO_ROOT")"
export NAMESPACE="${PROJECT_NAME}-alpha"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $*"; }

log_info "Starting K8s Alpha Smoke Tests for $PROJECT_NAME"

STEPS=("01-build-images.sh" "02-deploy-helm.sh" "03-wait-ready.sh" "04-health-check.sh" "05-unit-tests.sh" "06-api-integration.sh" "07-page-load.sh" "08-cleanup.sh")
FAILED=0

for step in "${STEPS[@]}"; do
    log_info "Running $step..."
    if "$SCRIPT_DIR/$step"; then
        log_pass "$step completed"
    else
        log_fail "$step failed"
        FAILED=$((FAILED + 1))
        break
    fi
done

if [[ $FAILED -eq 0 ]]; then
    log_pass "All alpha tests passed"
    exit 0
else
    log_fail "Alpha tests failed"
    exit 1
fi
