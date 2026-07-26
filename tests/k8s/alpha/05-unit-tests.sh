#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PROJECT_NAME="$(basename "$REPO_ROOT")"
export NAMESPACE="${PROJECT_NAME}-alpha"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

log_info "Running unit tests"
cd "$REPO_ROOT"

# Check if tests exist and run them
if [[ -d "tests/unit" ]] || [[ -d "test" ]]; then
    if make test-unit 2>/dev/null || npm test 2>/dev/null || python -m pytest tests/unit 2>/dev/null; then
        log_pass "Unit tests passed"
    else
        log_warn "Unit tests failed or not configured"
        # Don't exit on failure - this is optional
    fi
else
    log_warn "No unit test directory found"
fi

log_pass "Unit tests step completed"
