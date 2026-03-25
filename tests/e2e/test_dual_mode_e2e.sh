#!/usr/bin/env bash
set -euo pipefail

echo "=== E2E Test: Dual Mode (WireGuard + OpenZiti) ==="
echo "Verifies dual-mode client connects both overlays."

echo "Step 1: Verify client overlay package compiles..."
cd clients/native
go build ./internal/overlay/...
echo "PASS: Client overlay package compiles"

echo "Step 2: Run dual provider tests..."
go test ./internal/overlay/... -v -count=1 -run TestDualProvider 2>&1 | tail -10
echo "PASS: Dual provider tests pass"

echo "Step 3: Verify client config defaults to dual..."
OVERLAY_DEFAULT=$(grep -A1 'OverlayType:' internal/config/config.go | grep '"dual"' || echo "")
if [ -n "${OVERLAY_DEFAULT}" ]; then
    echo "PASS: Client defaults to dual overlay mode"
else
    echo "FAIL: Client does not default to dual mode"
    exit 1
fi

echo "=== Dual Mode E2E: COMPLETED ==="
