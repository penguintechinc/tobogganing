#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PROJECT_NAME="$(basename "$REPO_ROOT")"
export NAMESPACE="${PROJECT_NAME}-alpha"

# Auto-detect HELM_DIR
if [[ -d "$REPO_ROOT/k8s/helm/$PROJECT_NAME" ]]; then
    HELM_DIR="k8s/helm/$PROJECT_NAME"
elif [[ -d "$REPO_ROOT/helm/$PROJECT_NAME" ]]; then
    HELM_DIR="helm/$PROJECT_NAME"
elif [[ -d "$REPO_ROOT/infrastructure/helm/$PROJECT_NAME" ]]; then
    HELM_DIR="infrastructure/helm/$PROJECT_NAME"
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $*"; }

log_info "Building Docker images for $PROJECT_NAME (alpha)"
cd "$REPO_ROOT"

# Build images for alpha - this is project-specific
# The actual build commands depend on each project's structure
# For now, we'll tag images as 'alpha' for use with microk8s
if docker build -t "$PROJECT_NAME:alpha" .; then
    log_pass "Docker images built successfully"
else
    log_fail "Failed to build Docker images"
    exit 1
fi
