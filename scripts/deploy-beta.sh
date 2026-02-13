#!/usr/bin/env bash
# =============================================================================
# Tobogganing Beta Deployment Script
# Zero Trust SASE Platform - Kubernetes Deployment Automation
#
# Usage:
#   ./scripts/deploy-beta.sh [OPTIONS]
#
# Options:
#   --tag TAG               Image tag to deploy (default: latest)
#   --service SERVICE       Deploy specific service only (hub-api|hub-router|hub-webui|redis)
#   --skip-build            Skip Docker build, use existing images
#   --dry-run               Show what would be deployed without applying changes
#   --rollback              Rollback to previous deployment
#   --help                  Show this help message
#
# Environment:
#   KUBE_CONFIG             Path to kubeconfig file
#   KUBE_CONTEXT            Kubernetes context to use (default: dal2-beta)
#   RELEASE_NAME            Helm release name (default: tobogganing)
#   NAMESPACE               Kubernetes namespace (default: tobogganing)
#   IMAGE_REGISTRY          Docker registry URL (default: registry-dal2.penguintech.io)
#   APP_HOST                Application hostname (default: tobogganing.penguintech.io)
#
# =============================================================================

set -euo pipefail

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Script configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
readonly RELEASE_NAME="${RELEASE_NAME:-tobogganing}"
readonly NAMESPACE="${NAMESPACE:-tobogganing}"
readonly IMAGE_REGISTRY="${IMAGE_REGISTRY:-registry-dal2.penguintech.io}"
readonly KUBE_CONTEXT="${KUBE_CONTEXT:-dal2-beta}"
readonly APP_HOST="${APP_HOST:-tobogganing.penguintech.io}"
readonly CHART_PATH="${PROJECT_ROOT}/k8s/helm/tobogganing"
readonly MANIFESTS_PATH="${PROJECT_ROOT}/k8s/manifests"

# Service configuration
declare -a SERVICES=("hub-api" "hub-router" "hub-webui" "redis")
declare TAG="latest"
declare SERVICE_FILTER=""
declare SKIP_BUILD=false
declare DRY_RUN=false
declare DO_ROLLBACK=false

# =============================================================================
# Color output helpers
# =============================================================================

print_info() {
  echo -e "${BLUE}[INFO]${NC} $*"
}

print_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $*"
}

print_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $*"
}

print_error() {
  echo -e "${RED}[ERROR]${NC} $*" >&2
}

# =============================================================================
# Prerequisite checks
# =============================================================================

check_prerequisites() {
  print_info "Checking prerequisites..."

  local missing_tools=()

  # Check required commands
  local required_commands=("docker" "kubectl" "helm" "jq")
  for cmd in "${required_commands[@]}"; do
    if ! command -v "${cmd}" &> /dev/null; then
      missing_tools+=("${cmd}")
    fi
  done

  if [[ ${#missing_tools[@]} -gt 0 ]]; then
    print_error "Missing required tools: ${missing_tools[*]}"
    print_error "Please install the missing tools and try again"
    exit 1
  fi

  # Check Kubernetes connectivity
  if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot connect to Kubernetes cluster"
    print_error "Check your kubeconfig and KUBE_CONTEXT settings"
    exit 1
  fi

  # Check Helm chart exists
  if [[ ! -d "${CHART_PATH}" ]]; then
    print_error "Helm chart not found at: ${CHART_PATH}"
    exit 1
  fi

  # Check manifests directory exists
  if [[ ! -d "${MANIFESTS_PATH}" ]]; then
    print_error "Manifests directory not found at: ${MANIFESTS_PATH}"
    exit 1
  fi

  print_success "All prerequisites satisfied"
}

# =============================================================================
# Docker image build and push
# =============================================================================

build_and_push_images() {
  local service="$1"
  local tag="$2"
  local service_path="${PROJECT_ROOT}/services/${service}"

  if [[ ! -d "${service_path}" ]]; then
    print_warning "Service directory not found: ${service_path}"
    return 1
  fi

  if [[ ! -f "${service_path}/Dockerfile" ]]; then
    print_warning "Dockerfile not found for ${service}"
    return 1
  fi

  local image_name="${IMAGE_REGISTRY}/tobogganing/${service}:${tag}"

  print_info "Building Docker image for ${service}..."
  print_info "  Image: ${image_name}"

  if docker build \
    --file "${service_path}/Dockerfile" \
    --tag "${image_name}" \
    --label "version=${tag}" \
    --label "service=${service}" \
    --label "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "${service_path}"; then
    print_success "Built image: ${image_name}"
  else
    print_error "Failed to build image for ${service}"
    return 1
  fi

  print_info "Pushing Docker image for ${service}..."

  if docker push "${image_name}"; then
    print_success "Pushed image: ${image_name}"
  else
    print_error "Failed to push image for ${service}"
    return 1
  fi
}

# =============================================================================
# Kubernetes deployment
# =============================================================================

do_deploy() {
  local tag="$1"

  print_info "Deploying to Kubernetes cluster..."
  print_info "  Release: ${RELEASE_NAME}"
  print_info "  Namespace: ${NAMESPACE}"
  print_info "  Context: ${KUBE_CONTEXT}"
  print_info "  Tag: ${tag}"
  print_info "  Registry: ${IMAGE_REGISTRY}"

  # Set kubectl context
  if ! kubectl config use-context "${KUBE_CONTEXT}" &> /dev/null; then
    print_error "Failed to set Kubernetes context to: ${KUBE_CONTEXT}"
    exit 1
  fi

  # Ensure namespace exists
  if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
    print_info "Creating namespace: ${NAMESPACE}"
    kubectl create namespace "${NAMESPACE}" || true
  fi

  # Build Helm override values
  local helm_overrides=""
  helm_overrides+=" --set hubApi.image.repository=${IMAGE_REGISTRY}/tobogganing/hub-api"
  helm_overrides+=" --set hubApi.image.tag=${tag}"
  helm_overrides+=" --set hubRouter.image.repository=${IMAGE_REGISTRY}/tobogganing/hub-router"
  helm_overrides+=" --set hubRouter.image.tag=${tag}"
  helm_overrides+=" --set hubWebui.image.repository=${IMAGE_REGISTRY}/tobogganing/hub-webui"
  helm_overrides+=" --set hubWebui.image.tag=${tag}"
  helm_overrides+=" --set ingress.hosts[0].host=${APP_HOST}"

  # Use beta values file
  local values_file="${CHART_PATH}/values-beta.yaml"
  if [[ ! -f "${values_file}" ]]; then
    print_warning "Beta values file not found, using default values"
    values_file="${CHART_PATH}/values.yaml"
  fi

  print_info "Helm values file: ${values_file}"

  # Prepare helm upgrade command
  local helm_cmd="helm upgrade --install"
  helm_cmd+=" ${RELEASE_NAME}"
  helm_cmd+=" ${CHART_PATH}"
  helm_cmd+=" --namespace ${NAMESPACE}"
  helm_cmd+=" --values ${values_file}"
  helm_cmd+="${helm_overrides}"
  helm_cmd+=" --wait"
  helm_cmd+=" --timeout 5m"

  if [[ "${DRY_RUN}" == "true" ]]; then
    print_info "DRY-RUN mode: Showing deployment plan"
    helm_cmd+=" --dry-run"
    helm_cmd+=" --debug"
  fi

  print_info "Executing Helm deployment..."
  if eval "${helm_cmd}"; then
    print_success "Helm deployment completed successfully"
  else
    print_error "Helm deployment failed"
    return 1
  fi

  if [[ "${DRY_RUN}" != "true" ]]; then
    print_info "Waiting for deployments to be ready..."
    verify_deployment
  fi
}

# =============================================================================
# Deployment verification
# =============================================================================

verify_deployment() {
  print_info "Verifying deployment health..."

  local max_attempts=30
  local attempt=0

  while [[ ${attempt} -lt ${max_attempts} ]]; do
    # Check if all deployments are ready
    local ready_replicas=$(kubectl get deployments -n "${NAMESPACE}" \
      -o jsonpath='{.items[*].status.readyReplicas}' | \
      awk '{for(i=1;i<=NF;i++)sum+=$i}END{print sum}')

    local desired_replicas=$(kubectl get deployments -n "${NAMESPACE}" \
      -o jsonpath='{.items[*].spec.replicas}' | \
      awk '{for(i=1;i<=NF;i++)sum+=$i}END{print sum}')

    if [[ "${ready_replicas}" == "${desired_replicas}" ]]; then
      print_success "All deployments are ready"
      print_success "Ready replicas: ${ready_replicas}/${desired_replicas}"

      # Show service endpoints
      print_info "Service endpoints:"
      kubectl get endpoints -n "${NAMESPACE}" -o wide

      return 0
    fi

    print_info "Waiting for deployments... (${attempt}/${max_attempts}) - Ready: ${ready_replicas}/${desired_replicas}"
    sleep 10
    ((attempt++))
  done

  print_warning "Deployment verification timeout"
  print_warning "Showing current deployment status:"
  kubectl get deployments -n "${NAMESPACE}" -o wide
  kubectl get pods -n "${NAMESPACE}" -o wide

  return 1
}

# =============================================================================
# Rollback functionality
# =============================================================================

do_rollback() {
  print_warning "Rolling back to previous release..."
  print_info "Release: ${RELEASE_NAME}"
  print_info "Namespace: ${NAMESPACE}"

  if kubectl config use-context "${KUBE_CONTEXT}" &> /dev/null; then
    if helm rollback "${RELEASE_NAME}" --namespace "${NAMESPACE}"; then
      print_success "Rollback completed successfully"
      print_info "Verifying rollback..."
      verify_deployment
    else
      print_error "Rollback failed"
      return 1
    fi
  else
    print_error "Failed to set Kubernetes context"
    return 1
  fi
}

# =============================================================================
# Help message
# =============================================================================

show_help() {
  sed -n '2,37p' "${BASH_SOURCE[0]}" | sed 's/^# //'
}

# =============================================================================
# Main execution
# =============================================================================

main() {
  print_info "Tobogganing Beta Deployment Script"
  print_info "====================================="

  # Parse command line arguments
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tag)
        TAG="$2"
        shift 2
        ;;
      --service)
        SERVICE_FILTER="$2"
        shift 2
        ;;
      --skip-build)
        SKIP_BUILD=true
        shift
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

  # Check prerequisites
  check_prerequisites

  # Handle rollback
  if [[ "${DO_ROLLBACK}" == "true" ]]; then
    do_rollback
    exit $?
  fi

  # Build images unless skipped
  if [[ "${SKIP_BUILD}" != "true" ]]; then
    print_info "Building and pushing Docker images..."

    for service in "${SERVICES[@]}"; do
      if [[ -z "${SERVICE_FILTER}" ]] || [[ "${SERVICE_FILTER}" == "${service}" ]]; then
        build_and_push_images "${service}" "${TAG}" || {
          print_error "Failed to build/push ${service}, continuing..."
        }
      fi
    done
  else
    print_info "Skipping Docker build (--skip-build specified)"
  fi

  # Deploy to Kubernetes
  do_deploy "${TAG}"

  # Final status
  if [[ "${DRY_RUN}" != "true" ]]; then
    print_success "Deployment completed successfully!"
    print_info "Application accessible at: https://${APP_HOST}"
    print_info "Release name: ${RELEASE_NAME}"
    print_info "Namespace: ${NAMESPACE}"

    print_info "Quick commands:"
    print_info "  View logs:     kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=tobogganing -f"
    print_info "  Show status:   kubectl get all -n ${NAMESPACE}"
    print_info "  Describe pods: kubectl describe pods -n ${NAMESPACE}"
  else
    print_success "Dry-run completed successfully!"
  fi
}

main "$@"
