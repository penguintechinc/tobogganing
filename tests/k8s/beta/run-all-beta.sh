#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PROJECT_NAME="$(basename "$REPO_ROOT")"
export NAMESPACE="${PROJECT_NAME}-beta"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $*"; }

log_info "Starting K8s Beta Smoke Tests for $PROJECT_NAME"

STEPS=("01-deploy-helm.sh" "02-wait-ready.sh" "03-hardcoded-check.sh" "04-dns-resolution.sh" "05-integration-test.sh" "06-network-policy.sh" "07-scaling-test.sh" "08-cleanup.sh")
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
    log_pass "All beta tests passed"
    exit 0
else
    log_fail "Beta tests failed"
    exit 1
fi
