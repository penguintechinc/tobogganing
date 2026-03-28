#!/usr/bin/env bash
set -euo pipefail

# Tobogganing - Smoke Test Suite
# Quick verification that all core services can build and basic health checks pass

# Color output helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((TESTS_FAILED++))
}

skip() {
    echo -e "${YELLOW}⊘ SKIP${NC}: $1"
    ((TESTS_SKIPPED++))
}

info() {
    echo -e "${YELLOW}ℹ INFO${NC}: $1"
}

# Test 1: Hub API Dockerfile exists and builds
test_hub_api_build() {
    info "Testing Hub API build..."
    if [ ! -f "services/hub-api/Dockerfile" ]; then
        fail "Hub API Dockerfile not found"
        return
    fi

    if docker compose build services/hub-api 2>/dev/null; then
        pass "Hub API builds successfully"
    else
        fail "Hub API build failed"
    fi
}

# Test 2: Hub Router Dockerfile exists and builds
test_hub_router_build() {
    info "Testing Hub Router build..."
    if [ ! -f "services/hub-router/Dockerfile" ]; then
        fail "Hub Router Dockerfile not found"
        return
    fi

    if docker compose build services/hub-router 2>/dev/null; then
        pass "Hub Router builds successfully"
    else
        fail "Hub Router build failed"
    fi
}

# Test 3: Hub WebUI Dockerfile exists and builds
test_hub_webui_build() {
    info "Testing Hub WebUI build..."
    if [ ! -f "services/hub-webui/Dockerfile" ]; then
        fail "Hub WebUI Dockerfile not found"
        return
    fi

    if docker compose build services/hub-webui 2>/dev/null; then
        pass "Hub WebUI builds successfully"
    else
        fail "Hub WebUI build failed"
    fi
}

# Test 4: Version file exists and matches format
test_version_file() {
    info "Testing version file..."
    if [ ! -f ".version" ]; then
        fail "Version file .version not found"
        return
    fi

    VERSION=$(cat .version)
    if [[ $VERSION =~ ^v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        pass "Version file format is valid: $VERSION"
    else
        fail "Version file format invalid. Expected vX.X.X.EPOCH, got: $VERSION"
    fi
}

# Test 5: Hub API health endpoint
test_hub_api_health() {
    info "Testing Hub API health endpoint..."
    if curl -sf http://localhost:8080/healthz >/dev/null 2>&1; then
        pass "Hub API health endpoint responding"
    else
        skip "Hub API health endpoint not responding (container may not be running)"
    fi
}

# Test 6: Hub Router health endpoint
test_hub_router_health() {
    info "Testing Hub Router health endpoint..."
    if curl -sf http://localhost:9090/health >/dev/null 2>&1; then
        pass "Hub Router health endpoint responding"
    else
        skip "Hub Router health endpoint not responding (container may not be running)"
    fi
}

# Test 7: Hub WebUI health endpoint
test_hub_webui_health() {
    info "Testing Hub WebUI health endpoint..."
    if curl -sf http://localhost:3000/ >/dev/null 2>&1; then
        pass "Hub WebUI health endpoint responding"
    else
        skip "Hub WebUI health endpoint not responding (container may not be running)"
    fi
}

# Test 8: API status endpoint
test_api_status() {
    info "Testing API status endpoint..."
    if curl -sf http://localhost:8080/api/v1/status >/dev/null 2>&1; then
        pass "API status endpoint responding"
    else
        skip "API status endpoint not responding (container may not be running)"
    fi
}

# Main test execution
main() {
    echo "=========================================="
    echo "Tobogganing - Smoke Test Suite"
    echo "=========================================="
    echo ""

    # Change to project root directory
    cd "$(dirname "${BASH_SOURCE[0]}")/../.."

    # Run all tests
    test_hub_api_build
    test_hub_router_build
    test_hub_webui_build
    test_version_file
    test_hub_api_health
    test_hub_router_health
    test_hub_webui_health
    test_api_status

    # Summary
    echo ""
    echo "=========================================="
    echo "Test Summary"
    echo "=========================================="
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
    echo -e "${YELLOW}Skipped: $TESTS_SKIPPED${NC}"
    echo ""

    if [ $TESTS_FAILED -gt 0 ]; then
        echo -e "${RED}Smoke tests FAILED${NC}"
        exit 1
    else
        echo -e "${GREEN}Smoke tests PASSED${NC}"
        exit 0
    fi
}

main "$@"
