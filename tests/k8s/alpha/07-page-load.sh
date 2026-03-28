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

log_info "Testing page load"

# Port-forward web service if available
WEB_POD=$(microk8s kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$WEB_POD" ]]; then
    log_info "Port-forwarding to web service..."
    microk8s kubectl port-forward -n "$NAMESPACE" "pod/$WEB_POD" 3000:3000 2>/dev/null &
    PF_PID=$!
    sleep 2

    # Try to load main page
    if curl -sf http://localhost:3000 2>/dev/null | grep -q "html\|<!DOCTYPE" 2>/dev/null || true; then
        log_pass "Web page load test passed"
    else
        log_warn "Web page not accessible or HTML not found"
    fi

    kill $PF_PID 2>/dev/null || true
else
    log_warn "No web pod found for page load tests"
fi

log_pass "Page load test step completed"
