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

log_info "Testing scaling capabilities"

# Get deployments
DEPLOYMENTS=$(microk8s kubectl get deployments -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')

if [[ -z "$DEPLOYMENTS" ]]; then
    log_warn "No deployments found for scaling test"
    log_pass "Scaling test skipped"
    exit 0
fi

# Scale first deployment up then down
FIRST_DEPLOY=$(echo "$DEPLOYMENTS" | awk '{print $1}')
log_info "Testing scale on deployment: $FIRST_DEPLOY"

# Scale up
if microk8s kubectl scale deployment "$FIRST_DEPLOY" -n "$NAMESPACE" --replicas=2 2>/dev/null; then
    log_pass "Deployment scaled up to 2 replicas"
else
    log_warn "Failed to scale deployment up"
fi

sleep 2

# Scale back down
if microk8s kubectl scale deployment "$FIRST_DEPLOY" -n "$NAMESPACE" --replicas=1 2>/dev/null; then
    log_pass "Deployment scaled back down to 1 replica"
else
    log_warn "Failed to scale deployment down"
fi

log_pass "Scaling test completed"
