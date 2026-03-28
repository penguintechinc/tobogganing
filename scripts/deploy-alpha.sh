#!/usr/bin/env bash
# =============================================================================
# tobogganing Alpha Deployment Script
# Local MicroK8s Deployment via Kustomize
#
# Usage:
#   ./scripts/deploy-alpha.sh [OPTIONS]
#
# Options:
#   --build               Build Docker images and import into MicroK8s (default)
#   --skip-build          Skip Docker build, use existing images
#   --tag TAG             Image tag to use (default: alpha)
#   --service SERVICE     Build/deploy specific service only
#   --dry-run             Show what would be deployed without applying
#   --rollback            Rollback deployments to previous revision
#   --help                Show this help message
#
# Environment:
#   KUBE_CONTEXT          Kubernetes context (default: local-alpha)
#   NAMESPACE             Target namespace (default: tobogganing-alpha)
#   APP_HOST              Application hostname (default: tobogganing.localhost.local)
#
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

readonly APP_NAME="${APP_NAME:-tobogganing}"
readonly KUBE_CONTEXT="${KUBE_CONTEXT:-local-alpha}"
readonly NAMESPACE="${NAMESPACE:-tobogganing-alpha}"
readonly APP_HOST="${APP_HOST:-tobogganing.localhost.local}"
readonly OVERLAY_PATH="${OVERLAY_PATH:-k8s/kustomize/overlays/alpha}"

# Services with Dockerfiles (customize per repo)
declare -a SERVICES=("hub-api" "hub-router" "hub-webui")

# Image name prefix (used for docker build tags)
readonly IMAGE_PREFIX="${APP_NAME}"

# Defaults
declare TAG="alpha"
declare SERVICE_FILTER=""
declare SKIP_BUILD=false
declare DRY_RUN=false
declare DO_ROLLBACK=false

# =============================================================================
# Color output helpers
# =============================================================================

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $*"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# =============================================================================
# kubectl wrapper (always uses --context)
# =============================================================================

kctl() {
    kubectl --context "${KUBE_CONTEXT}" "$@"
}

# =============================================================================
# Prerequisite checks
# =============================================================================

check_prerequisites() {
    print_info "Checking prerequisites..."
    local missing=()

    for cmd in kubectl docker microk8s; do
        if ! command -v "${cmd}" &>/dev/null; then
            missing+=("${cmd}")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        print_error "Missing required tools: ${missing[*]}"
        exit 1
    fi

    # Verify context exists
    if ! kubectl config get-contexts "${KUBE_CONTEXT}" &>/dev/null; then
        print_error "Kubernetes context '${KUBE_CONTEXT}' not found"
        echo "Available contexts:"
        kubectl config get-contexts --output=name
        exit 1
    fi

    # Verify cluster reachable
    if ! kctl cluster-info &>/dev/null; then
        print_error "Cannot reach cluster via context '${KUBE_CONTEXT}'"
        print_error "Is MicroK8s running? Try: microk8s status"
        exit 1
    fi

    # Verify overlay exists
    if [[ ! -d "${PROJECT_ROOT}/${OVERLAY_PATH}" ]]; then
        print_error "Kustomize overlay not found: ${OVERLAY_PATH}"
        exit 1
    fi

    print_success "All prerequisites satisfied"
}

# =============================================================================
# Docker build and MicroK8s import
# =============================================================================

build_and_import() {
    local service="$1"
    local tag="$2"
    local service_path="${PROJECT_ROOT}/services/${service}"

    if [[ ! -d "${service_path}" ]]; then
        print_warning "Service directory not found: services/${service} — skipping"
        return 0
    fi

    # Find Dockerfile (prefer Dockerfile.notests for faster alpha builds)
    local dockerfile="${service_path}/Dockerfile"
    if [[ -f "${service_path}/Dockerfile.notests" ]]; then
        dockerfile="${service_path}/Dockerfile.notests"
        print_info "Using Dockerfile.notests for ${service} (faster alpha build)"
    fi

    if [[ ! -f "${dockerfile}" ]]; then
        print_warning "No Dockerfile found for ${service} — skipping"
        return 0
    fi

    local image_name="${IMAGE_PREFIX}/${service}:${tag}"

    print_info "Building image: ${image_name}"
    if ! docker build \
        --file "${dockerfile}" \
        --tag "${image_name}" \
        --label "environment=alpha" \
        --label "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "${service_path}"; then
        print_error "Failed to build ${service}"
        return 1
    fi

    print_info "Importing ${image_name} into MicroK8s..."
    if ! docker save "${image_name}" | microk8s ctr image import -; then
        print_error "Failed to import ${image_name} into MicroK8s"
        return 1
    fi

    print_success "Built and imported: ${image_name}"
}

# =============================================================================
# Kustomize deployment
# =============================================================================

do_deploy() {
    print_info "Deploying to local MicroK8s cluster..."
    print_info "  Context:   ${KUBE_CONTEXT}"
    print_info "  Namespace: ${NAMESPACE}"
    print_info "  Overlay:   ${OVERLAY_PATH}"
    print_info "  Host:      ${APP_HOST}"

    # Create namespace if missing
    if ! kctl get namespace "${NAMESPACE}" &>/dev/null; then
        print_info "Creating namespace: ${NAMESPACE}"
        kctl create namespace "${NAMESPACE}"
    fi

    # Apply kustomize overlay
    if [[ "${DRY_RUN}" == "true" ]]; then
        print_info "DRY-RUN: Rendering kustomize output..."
        kctl apply -k "${PROJECT_ROOT}/${OVERLAY_PATH}" --dry-run=client -o yaml
        return 0
    fi

    if ! kctl apply -k "${PROJECT_ROOT}/${OVERLAY_PATH}"; then
        print_error "Failed to apply kustomize overlay"
        return 1
    fi

    print_success "Kustomize manifests applied"
}

# =============================================================================
# Rollout verification
# =============================================================================

wait_for_rollout() {
    print_info "Waiting for deployments to roll out..."

    # Get all deployments in namespace
    local deployments
    deployments=$(kctl get deployments -n "${NAMESPACE}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "${deployments}" ]]; then
        print_warning "No deployments found in namespace ${NAMESPACE}"
        return 0
    fi

    local failed=false
    for deploy in ${deployments}; do
        print_info "Waiting for deployment/${deploy}..."
        if ! kctl rollout status "deployment/${deploy}" -n "${NAMESPACE}" --timeout=300s; then
            print_error "Deployment ${deploy} failed to roll out"
            failed=true
        fi
    done

    # Also check statefulsets
    local statefulsets
    statefulsets=$(kctl get statefulsets -n "${NAMESPACE}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

    for sts in ${statefulsets}; do
        print_info "Waiting for statefulset/${sts}..."
        if ! kctl rollout status "statefulset/${sts}" -n "${NAMESPACE}" --timeout=300s; then
            print_error "StatefulSet ${sts} failed to roll out"
            failed=true
        fi
    done

    if [[ "${failed}" == "true" ]]; then
        return 1
    fi

    print_success "All workloads rolled out successfully"
}

# =============================================================================
# Show status
# =============================================================================

show_status() {
    echo ""
    print_info "Pod Status:"
    kctl get pods -n "${NAMESPACE}" -o wide
    echo ""
    print_info "Services:"
    kctl get svc -n "${NAMESPACE}"
    echo ""
    print_info "Access URL: https://${APP_HOST}"
    echo ""
    print_info "Quick commands:"
    echo "  View pods:   kubectl --context ${KUBE_CONTEXT} get pods -n ${NAMESPACE}"
    echo "  View logs:   kubectl --context ${KUBE_CONTEXT} logs -n ${NAMESPACE} -l environment=alpha -f"
    echo "  Describe:    kubectl --context ${KUBE_CONTEXT} describe pods -n ${NAMESPACE}"
}

# =============================================================================
# Rollback
# =============================================================================

do_rollback() {
    print_warning "Rolling back deployments in ${NAMESPACE}..."

    local deployments
    deployments=$(kctl get deployments -n "${NAMESPACE}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "${deployments}" ]]; then
        print_error "No deployments found in namespace ${NAMESPACE}"
        return 1
    fi

    for deploy in ${deployments}; do
        print_info "Rolling back deployment/${deploy}..."
        kctl rollout undo "deployment/${deploy}" -n "${NAMESPACE}"
    done

    print_success "Rollback initiated"
    wait_for_rollout
}

# =============================================================================
# Help
# =============================================================================

show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploy ${APP_NAME} to local MicroK8s alpha environment using Kustomize.

OPTIONS:
    --build               Build images and import into MicroK8s (default)
    --skip-build          Skip Docker build, use existing images
    --tag TAG             Image tag (default: alpha)
    --service SERVICE     Build specific service only (e.g., hub-api)
    --dry-run             Render manifests without applying
    --rollback            Rollback deployments to previous revision
    --help                Show this help message

ENVIRONMENT:
    KUBE_CONTEXT:   ${KUBE_CONTEXT}
    NAMESPACE:      ${NAMESPACE}
    APP_HOST:       ${APP_HOST}
    OVERLAY_PATH:   ${OVERLAY_PATH}
    SERVICES:       ${SERVICES[*]}

EXAMPLES:
    # Full build and deploy
    $(basename "$0")

    # Deploy without rebuilding images
    $(basename "$0") --skip-build

    # Build and deploy only one service
    $(basename "$0") --service hub-api

    # Preview what would be applied
    $(basename "$0") --skip-build --dry-run

    # Rollback to previous deployment
    $(basename "$0") --rollback
EOF
}

# =============================================================================
# Main
# =============================================================================

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --build)
                SKIP_BUILD=false
                shift
                ;;
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            --tag)
                TAG="$2"
                shift 2
                ;;
            --service)
                SERVICE_FILTER="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --rollback)
                DO_ROLLBACK=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    echo ""
    print_info "=========================================="
    print_info "  ${APP_NAME} — Alpha Deployment"
    print_info "=========================================="
    echo ""

    check_prerequisites

    # Handle rollback
    if [[ "${DO_ROLLBACK}" == "true" ]]; then
        do_rollback
        show_status
        exit $?
    fi

    # Build images
    if [[ "${SKIP_BUILD}" != "true" ]]; then
        print_info "Building and importing Docker images..."
        for service in "${SERVICES[@]}"; do
            if [[ -z "${SERVICE_FILTER}" ]] || [[ "${SERVICE_FILTER}" == "${service}" ]]; then
                build_and_import "${service}" "${TAG}" || {
                    print_error "Failed to build ${service}"
                    exit 1
                }
            fi
        done
    else
        print_info "Skipping build (--skip-build)"
    fi

    # Deploy
    do_deploy || exit 1

    if [[ "${DRY_RUN}" != "true" ]]; then
        wait_for_rollout || print_warning "Some workloads did not roll out cleanly"
        show_status
        print_success "Alpha deployment complete!"
    else
        print_success "Dry-run complete!"
    fi
}

main "$@"
