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

log_info "Checking for hardcoded credentials and secrets"

# Check pod environment variables for potential hardcoded secrets
PODS=$(microk8s kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')

FOUND_HARDCODED=0
for pod in $PODS; do
    ENV=$(microk8s kubectl exec -n "$NAMESPACE" "$pod" -- env 2>/dev/null || echo "")

    # Check for common hardcoded secret patterns
    if echo "$ENV" | grep -iE "(password|secret|token|key)=(.*)" | grep -v "^[A-Z_]*=\$(" | grep -v "^[A-Z_]*=$" 2>/dev/null; then
        log_warn "Potential hardcoded secret found in $pod"
        FOUND_HARDCODED=$((FOUND_HARDCODED + 1))
    fi
done

if [[ $FOUND_HARDCODED -eq 0 ]]; then
    log_pass "No obvious hardcoded credentials detected"
else
    log_warn "Found $FOUND_HARDCODED pod(s) with potential hardcoded values - review recommended"
fi

log_pass "Hardcoded check completed"
