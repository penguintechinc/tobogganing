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

log_info "Waiting for deployments to be ready in $NAMESPACE"

# Wait for all deployments to be ready
if microk8s kubectl wait --for=condition=available --timeout=5m \
    -l "app.kubernetes.io/instance=$PROJECT_NAME" \
    deployment -n "$NAMESPACE"; then
    log_pass "All deployments are ready"
else
    log_fail "Timeout waiting for deployments"
    log_info "Current pod status:"
    microk8s kubectl get pods -n "$NAMESPACE" || true
    exit 1
fi

log_info "Current pod status:"
microk8s kubectl get pods -n "$NAMESPACE"
