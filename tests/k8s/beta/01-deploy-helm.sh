#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PROJECT_NAME="$(basename "$REPO_ROOT")"
export NAMESPACE="${PROJECT_NAME}-beta"

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

log_info "Deploying Helm chart for $PROJECT_NAME to $NAMESPACE (beta)"

# Create namespace if it doesn't exist
microk8s kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | microk8s kubectl apply -f -

# Deploy using Helm with beta values
if helm upgrade --install "$PROJECT_NAME" "./$HELM_DIR" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --values "./$HELM_DIR/values-beta.yaml" \
    --wait \
    --timeout 5m; then
    log_pass "Helm deployment successful"
else
    log_fail "Failed to deploy Helm chart"
    exit 1
fi
