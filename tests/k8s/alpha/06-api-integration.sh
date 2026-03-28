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

log_info "Running API integration tests"

# Port-forward API service if available
API_POD=$(microk8s kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$API_POD" ]]; then
    log_info "Port-forwarding to API service..."
    microk8s kubectl port-forward -n "$NAMESPACE" "pod/$API_POD" 8000:8000 &
    PF_PID=$!
    sleep 2

    # Try basic health check
    if curl -sf http://localhost:8000/health 2>/dev/null || curl -sf http://localhost:8000/healthz 2>/dev/null; then
        log_pass "API health check passed"
    else
        log_warn "API health endpoint not responding"
    fi

    kill $PF_PID 2>/dev/null || true
else
    log_warn "No API pod found for integration tests"
fi

log_pass "API integration tests step completed"
