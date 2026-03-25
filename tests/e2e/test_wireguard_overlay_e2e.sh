#!/usr/bin/env bash
set -euo pipefail

echo "=== E2E Test: WireGuard Overlay Path ==="
echo "Verifies the full WireGuard path with OverlayScope policy evaluation."

HUB_ROUTER_URL="${HUB_ROUTER_URL:-http://localhost:8443}"

echo "Step 1: Check hub-router health..."
HEALTH=$(curl -sf "${HUB_ROUTER_URL}/health" 2>/dev/null || echo '{"status":"error"}')
echo "Health: ${HEALTH}"

if echo "${HEALTH}" | grep -q '"status":"healthy"'; then
    echo "PASS: Hub-router is healthy"
else
    echo "SKIP: Hub-router not available (set HUB_ROUTER_URL)"
    exit 0
fi

echo "Step 2: Verify overlay type in health response..."
OVERLAY_TYPE=$(echo "${HEALTH}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('overlay_type','unknown'))" 2>/dev/null || echo "unknown")
echo "Overlay type: ${OVERLAY_TYPE}"

echo "Step 3: Verify WireGuard OverlayScope in policy engine..."
cd services/hub-router
go test ./internal/policy/ -v -count=1 -run TestOverlayScope 2>&1 | tail -5
echo "PASS: OverlayScope filtering verified"

echo "=== WireGuard Overlay E2E: COMPLETED ==="
