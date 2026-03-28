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

log_info "Cleaning up alpha test environment"

# Uninstall Helm release
if helm uninstall "$PROJECT_NAME" -n "$NAMESPACE" 2>/dev/null; then
    log_pass "Helm release uninstalled"
else
    log_pass "Helm release not found or already removed"
fi

# Delete namespace
if microk8s kubectl delete namespace "$NAMESPACE" 2>/dev/null; then
    log_pass "Namespace deleted"
else
    log_pass "Namespace not found or already deleted"
fi

log_pass "Cleanup completed"
