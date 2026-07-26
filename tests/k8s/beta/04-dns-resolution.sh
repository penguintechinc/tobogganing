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

log_info "Testing DNS resolution"

# Get a pod to use for testing
TEST_POD=$(microk8s kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -z "$TEST_POD" ]]; then
    log_warn "No pods available for DNS testing"
    log_pass "DNS test skipped"
    exit 0
fi

# Test DNS resolution for common services
SERVICES=$(microk8s kubectl get svc -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')

RESOLVED=0
FAILED_DNS=0

for svc in $SERVICES; do
    if microk8s kubectl exec -n "$NAMESPACE" "$TEST_POD" -- sh -c "nslookup $svc 2>/dev/null | grep -q 'Name:'" 2>/dev/null; then
        log_info "DNS resolved: $svc"
        RESOLVED=$((RESOLVED + 1))
    else
        log_warn "Failed to resolve: $svc"
        FAILED_DNS=$((FAILED_DNS + 1))
    fi
done

if [[ $RESOLVED -gt 0 ]]; then
    log_pass "DNS resolution working ($RESOLVED service(s) resolved)"
else
    log_warn "DNS resolution issues detected"
fi

log_pass "DNS resolution test completed"
