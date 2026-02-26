#!/usr/bin/env bash
set -euo pipefail

echo "=== Smoke Test: XDP Stub (No Build Tag) ==="

cd services/hub-router

echo "Verifying XDP stub compiles without BPF dependencies..."
go build ./internal/xdp/
echo "PASS: XDP stub compiles"

echo "Running XDP stub tests..."
go test ./internal/xdp/ -v -count=1
echo "PASS: XDP stub tests pass"

echo "=== XDP Stub: ALL PASSED ==="
