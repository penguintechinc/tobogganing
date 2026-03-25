#!/usr/bin/env bash
set -euo pipefail

echo "=== Smoke Test: Native Client Build ==="

cd clients/native

echo "Testing headless build..."
go build -o /tmp/client-headless-test ./cmd/headless/
echo "PASS: Headless build succeeded"
rm -f /tmp/client-headless-test

echo "Testing go vet..."
go vet ./internal/overlay/... ./internal/config/... ./internal/client/...
echo "PASS: go vet clean"

echo "=== Client Build: ALL PASSED ==="
