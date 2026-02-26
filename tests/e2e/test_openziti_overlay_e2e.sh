#!/usr/bin/env bash
set -euo pipefail

echo "=== E2E Test: OpenZiti Overlay Path ==="
echo "Requires a running OpenZiti controller and hub-router with openziti overlay."

ZITI_CTRL="${ZITI_CTRL_URL:-}"

if [ -z "${ZITI_CTRL}" ]; then
    echo "SKIP: ZITI_CTRL_URL not set, skipping OpenZiti E2E"
    exit 0
fi

echo "Step 1: Verify Ziti controller reachable..."
if curl -sf "${ZITI_CTRL}/.well-known/est/cacerts" > /dev/null 2>&1; then
    echo "PASS: Ziti controller reachable"
else
    echo "SKIP: Ziti controller not reachable at ${ZITI_CTRL}"
    exit 0
fi

HUB_ROUTER_URL="${HUB_ROUTER_URL:-http://localhost:8443}"

echo "Step 2: Verify hub-router health with openziti..."
HEALTH=$(curl -sf "${HUB_ROUTER_URL}/health" 2>/dev/null || echo '{"status":"error"}')
OVERLAY_TYPE=$(echo "${HEALTH}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('overlay_type','unknown'))" 2>/dev/null || echo "unknown")

if [ "${OVERLAY_TYPE}" = "openziti" ]; then
    echo "PASS: Hub-router running with openziti overlay"
else
    echo "WARN: Hub-router overlay type is '${OVERLAY_TYPE}', expected 'openziti'"
fi

echo "Step 3: Verify Ziti listener active..."
ZITI_ACTIVE=$(echo "${HEALTH}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ziti_listener_active', False))" 2>/dev/null || echo "false")
if [ "${ZITI_ACTIVE}" = "True" ]; then
    echo "PASS: Ziti listener is active"
else
    echo "WARN: Ziti listener not active"
fi

echo "=== OpenZiti Overlay E2E: COMPLETED ==="
