#!/usr/bin/env bash
# =============================================================================
# Tobogganing Smoke Test Suite
# =============================================================================
# Runs a curated set of quick health checks against a running Docker Compose
# environment.  Each test should complete in <30 seconds; the full suite in
# under 2 minutes.
#
# Usage:
#   ./tests/smoke/run-smoke-tests.sh
#
# Environment variables (all optional, have sensible defaults):
#   API_BASE_URL        Hub-api base URL          (default: http://localhost:8000)
#   API_TEST_TOKEN      JWT bearer token           (default: "")
#   SQUAWK_ENABLED      Set to "true" to run DNS tests (default: false)
#   DNS_LISTENER_HOST   DNS listener IP/hostname   (default: 127.0.0.1)
#   DNS_LISTENER_PORT   DNS listener port          (default: 5353)
#   K8S_NAMESPACE       Kubernetes namespace       (default: tobogganing)
#   KUBECTL_CONTEXT     kubectl context to use     (default: current context)
#   SMOKE_TIMEOUT       Per-request timeout (sec)  (default: 10)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
API_TEST_TOKEN="${API_TEST_TOKEN:-}"
SQUAWK_ENABLED="${SQUAWK_ENABLED:-false}"
DNS_LISTENER_HOST="${DNS_LISTENER_HOST:-127.0.0.1}"
DNS_LISTENER_PORT="${DNS_LISTENER_PORT:-5353}"
K8S_NAMESPACE="${K8S_NAMESPACE:-tobogganing}"
KUBECTL_CONTEXT="${KUBECTL_CONTEXT:-}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-10}"

# ---------------------------------------------------------------------------
# Colour output helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Colour

_pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
_fail() { echo -e "${RED}[FAIL]${NC} $*"; FAILURES=$((FAILURES + 1)); }
_skip() { echo -e "${YELLOW}[SKIP]${NC} $*"; SKIPPED=$((SKIPPED + 1)); }
_info() { echo -e "${BLUE}[INFO]${NC} $*"; }

FAILURES=0
SKIPPED=0
PASSED=0

# ---------------------------------------------------------------------------
# HTTP helper — wraps curl for consistent options
# ---------------------------------------------------------------------------
_http() {
    # Usage: _http <METHOD> <PATH> [curl-extra-args...]
    local method="$1"
    local path="$2"
    shift 2

    local url="${API_BASE_URL}${path}"
    local auth_header=()
    if [[ -n "${API_TEST_TOKEN}" ]]; then
        auth_header=(-H "Authorization: Bearer ${API_TEST_TOKEN}")
    fi

    curl --silent --show-error --max-time "${SMOKE_TIMEOUT}" \
        -X "${method}" \
        "${auth_header[@]}" \
        -H "Content-Type: application/json" \
        "$@" \
        "${url}"
}

_http_status() {
    # Return only the HTTP status code for a request.
    local method="$1"
    local path="$2"
    shift 2

    local url="${API_BASE_URL}${path}"
    local auth_header=()
    if [[ -n "${API_TEST_TOKEN}" ]]; then
        auth_header=(-H "Authorization: Bearer ${API_TEST_TOKEN}")
    fi

    curl --silent --output /dev/null --write-out "%{http_code}" \
        --max-time "${SMOKE_TIMEOUT}" \
        -X "${method}" \
        "${auth_header[@]}" \
        -H "Content-Type: application/json" \
        "$@" \
        "${url}"
}

# ---------------------------------------------------------------------------
# Smoke test 1 — Pydantic validation rejects malformed policy JSON with 422
# ---------------------------------------------------------------------------
test_pydantic_validation() {
    local test_name="Pydantic validation (malformed policy → 422)"
    _info "Running: ${test_name}"

    # Send a policy body that is missing the required `name` field.
    local payload='{"action":"allow","protocol":"ftp-invalid","src_cidrs":["not-a-cidr"]}'

    local status
    status=$(_http_status POST /api/v1/policies --data "${payload}")

    case "${status}" in
        422)
            _pass "${test_name}"
            PASSED=$((PASSED + 1))
            ;;
        401|403)
            _skip "${test_name} (auth not configured: HTTP ${status})"
            ;;
        *)
            _fail "${test_name}: expected HTTP 422, got ${status}"
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Smoke test 2 — DNS forwarder health (requires SQUAWK_ENABLED=true)
# ---------------------------------------------------------------------------
test_dns_forwarder_health() {
    local test_name="DNS forwarder health (SQUAWK UDP listener)"

    if [[ "${SQUAWK_ENABLED}" != "true" ]]; then
        _skip "${test_name} (SQUAWK_ENABLED is not 'true')"
        return
    fi

    _info "Running: ${test_name}"

    # Verify the DNS listener port is open and responsive.
    # Uses dig if available, falls back to nc (netcat).
    if command -v dig &>/dev/null; then
        # Send a real DNS query; a response of any kind means the listener is up.
        local result
        result=$(dig +short +time=3 +tries=1 \
            @"${DNS_LISTENER_HOST}" -p "${DNS_LISTENER_PORT}" \
            google.com A 2>&1 || true)

        if echo "${result}" | grep -qE '^[0-9]+\.[0-9]+'; then
            _pass "${test_name} (dig returned an A record)"
            PASSED=$((PASSED + 1))
        else
            # A connection-refused or timeout means the listener is down.
            if echo "${result}" | grep -qiE 'connection refused|timed out|no servers'; then
                _fail "${test_name}: DNS listener not responding on ${DNS_LISTENER_HOST}:${DNS_LISTENER_PORT}"
            else
                # Any other response (NXDOMAIN, SERVFAIL) still proves the listener is up.
                _pass "${test_name} (dig reached listener; response: ${result:-empty})"
                PASSED=$((PASSED + 1))
            fi
        fi
    elif command -v nc &>/dev/null; then
        if nc -zu -w 3 "${DNS_LISTENER_HOST}" "${DNS_LISTENER_PORT}" 2>/dev/null; then
            _pass "${test_name} (nc UDP probe succeeded)"
            PASSED=$((PASSED + 1))
        else
            _fail "${test_name}: UDP port ${DNS_LISTENER_PORT} unreachable on ${DNS_LISTENER_HOST}"
        fi
    else
        _skip "${test_name} (neither dig nor nc available)"
    fi
}

# ---------------------------------------------------------------------------
# Smoke test 3 — WaddlePerf endpoint POST + GET returns 200
# ---------------------------------------------------------------------------
test_perf_endpoint() {
    local test_name="WaddlePerf metrics endpoint (POST + GET)"
    _info "Running: ${test_name}"

    # --- POST a single metric ---
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")

    local post_payload
    post_payload=$(cat <<JSON
{
  "metrics": [{
    "source_id": "smoke-test-router-01",
    "source_type": "hub-router",
    "target_id": "smoke-test-router-02",
    "protocol": "wireguard",
    "latency_ms": 8.5,
    "jitter_ms": 0.9,
    "packet_loss_pct": 0.0,
    "throughput_mbps": 800.0,
    "timestamp": "${now}"
  }]
}
JSON
)

    local post_status
    post_status=$(_http_status POST /api/v1/perf/metrics --data "${post_payload}")

    local post_ok=false
    case "${post_status}" in
        200)
            post_ok=true
            ;;
        401|403)
            _skip "${test_name} (auth not configured: HTTP ${post_status})"
            return
            ;;
        *)
            _fail "${test_name}: POST returned HTTP ${post_status}, expected 200"
            return
            ;;
    esac

    # --- GET metrics and verify 200 ---
    local get_status
    get_status=$(_http_status GET /api/v1/perf/metrics)

    if [[ "${get_status}" == "200" ]]; then
        _pass "${test_name}"
        PASSED=$((PASSED + 1))
    else
        _fail "${test_name}: GET returned HTTP ${get_status}, expected 200"
    fi
}

# ---------------------------------------------------------------------------
# Smoke test 4 — NetworkPolicy default-deny applied in Kubernetes namespace
# ---------------------------------------------------------------------------
test_networkpolicy_applied() {
    local test_name="Kubernetes NetworkPolicy default-deny (namespace: ${K8S_NAMESPACE})"
    _info "Running: ${test_name}"

    if ! command -v kubectl &>/dev/null; then
        _skip "${test_name} (kubectl not available)"
        return
    fi

    local context_flag=()
    if [[ -n "${KUBECTL_CONTEXT}" ]]; then
        context_flag=(--context "${KUBECTL_CONTEXT}")
    fi

    # Check that at least one NetworkPolicy in the target namespace selects
    # all pods (i.e., has an empty podSelector — the canonical default-deny).
    local policy_count
    policy_count=$(kubectl "${context_flag[@]}" \
        get networkpolicies \
        --namespace "${K8S_NAMESPACE}" \
        --output jsonpath='{.items[*].spec.podSelector}' \
        2>/dev/null | grep -c '{}' || true)

    if [[ "${policy_count}" -ge 1 ]]; then
        _pass "${test_name} (found ${policy_count} default-deny policy/policies)"
        PASSED=$((PASSED + 1))
    else
        # Warn rather than hard-fail when namespace doesn't exist yet (pre-deploy).
        local ns_exists
        ns_exists=$(kubectl "${context_flag[@]}" \
            get namespace "${K8S_NAMESPACE}" \
            --output name 2>/dev/null || true)

        if [[ -z "${ns_exists}" ]]; then
            _skip "${test_name} (namespace '${K8S_NAMESPACE}' does not exist yet)"
        else
            _fail "${test_name}: no default-deny NetworkPolicy found in namespace '${K8S_NAMESPACE}'"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Main — run all tests and report
# ---------------------------------------------------------------------------
main() {
    echo ""
    echo "========================================"
    echo "  Tobogganing Smoke Test Suite"
    echo "  API: ${API_BASE_URL}"
    echo "========================================"
    echo ""

    test_pydantic_validation
    test_dns_forwarder_health
    test_perf_endpoint
    test_networkpolicy_applied

    echo ""
    echo "========================================"
    echo "  Results"
    echo "========================================"
    echo -e "  ${GREEN}Passed : ${PASSED}${NC}"
    echo -e "  ${YELLOW}Skipped: ${SKIPPED}${NC}"
    echo -e "  ${RED}Failed : ${FAILURES}${NC}"
    echo "========================================"
    echo ""

    if [[ "${FAILURES}" -gt 0 ]]; then
        echo -e "${RED}Smoke tests FAILED (${FAILURES} failure(s))${NC}"
        exit 1
    else
        echo -e "${GREEN}All smoke tests passed.${NC}"
        exit 0
    fi
}

main "$@"
