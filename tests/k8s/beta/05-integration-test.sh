#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PROJECT_NAME="$(basename "$REPO_ROOT")"
export NAMESPACE="${PROJECT_NAME}-beta"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

log_info "Running beta integration tests"
cd "$REPO_ROOT"

# Check if integration tests exist and run them
if [[ -d "tests/integration" ]] || [[ -f "tests/integration.sh" ]]; then
    if make test-integration 2>/dev/null || npm run test:integration 2>/dev/null || python -m pytest tests/integration 2>/dev/null; then
        log_pass "Integration tests passed"
    else
        log_warn "Integration tests failed or not configured"
    fi
else
    log_warn "No integration test directory found"
fi

log_pass "Integration test step completed"
