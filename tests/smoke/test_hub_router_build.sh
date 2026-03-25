#!/usr/bin/env bash
set -euo pipefail

echo "=== Smoke Test: Hub Router Build ==="

cd services/hub-router

echo "Testing default build (no XDP tag)..."
go build -o /tmp/hub-router-test ./proxy/
echo "PASS: Default build succeeded"
rm -f /tmp/hub-router-test

echo "Testing go vet..."
go vet ./...
echo "PASS: go vet clean"

echo "=== Hub Router Build: ALL PASSED ==="
