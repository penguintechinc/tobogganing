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

log_info "Checking pod health in $NAMESPACE"

# Get pod names
PODS=$(microk8s kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')

if [[ -z "$PODS" ]]; then
    log_fail "No pods found in $NAMESPACE"
    exit 1
fi

HEALTHY=0
for pod in $PODS; do
    STATUS=$(microk8s kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
    if [[ "$STATUS" == "Running" ]]; then
        log_pass "Pod $pod is Running"
        HEALTHY=$((HEALTHY + 1))
    else
        log_fail "Pod $pod is $STATUS"
    fi
done

if [[ $HEALTHY -gt 0 ]]; then
    log_pass "Health check passed: $HEALTHY pod(s) running"
else
    log_fail "Health check failed: no pods running"
    exit 1
fi
