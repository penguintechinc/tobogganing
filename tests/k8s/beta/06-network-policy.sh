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

log_info "Checking network policies"

# Check if network policies are defined
POLICIES=$(microk8s kubectl get networkpolicies -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$POLICIES" ]]; then
    log_info "Found network policies: $POLICIES"
    log_pass "Network policies are defined"
else
    log_warn "No network policies defined in $NAMESPACE"
fi

# Check pod network connectivity
PODS=$(microk8s kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')
FIRST_POD=$(echo "$PODS" | awk '{print $1}')

if [[ -n "$FIRST_POD" ]]; then
    if microk8s kubectl exec -n "$NAMESPACE" "$FIRST_POD" -- sh -c "ping -c 1 8.8.8.8" 2>/dev/null; then
        log_pass "Pod network connectivity verified"
    else
        log_warn "Network connectivity limited (expected with network policies)"
    fi
fi

log_pass "Network policy check completed"
