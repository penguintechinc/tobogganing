#!/usr/bin/env bash
set -euo pipefail

echo "=== E2E Test: Overlay Scope Policy Filtering ==="

cd services/hub-router

echo "Step 1: Run OverlayScope filtering tests..."
go test ./internal/policy/ -v -count=1 -run TestOverlayScope
echo "PASS: OverlayScope filtering works"

echo "Step 2: Run empty scope test..."
go test ./internal/policy/ -v -count=1 -run TestEmptyScope
echo "PASS: Empty scope matches all overlays"

echo "=== Overlay Scope Policy: ALL PASSED ==="
