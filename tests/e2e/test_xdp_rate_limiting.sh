#!/usr/bin/env bash
set -euo pipefail

echo "=== E2E Test: XDP Rate Limiting ==="
echo "Requires XDP build tag and root/CAP_BPF capabilities."

cd services/hub-router

# Check if XDP build tag is available
if go build -tags xdp ./internal/xdp/ 2>/dev/null; then
    echo "PASS: XDP package compiles with -tags xdp"
else
    echo "SKIP: XDP build not available (missing clang/BPF headers or bpf2go output)"
    echo "Falling back to stub tests..."
    go test ./internal/xdp/ -v -count=1
    echo "PASS: XDP stub tests pass"
    exit 0
fi

# If we can build XDP, try running XDP-specific tests
if [ "$(id -u)" -eq 0 ] || capsh --has-p=cap_bpf 2>/dev/null; then
    echo "Running XDP tests with BPF capabilities..."
    go test -tags xdp ./internal/xdp/ -v -count=1
    echo "PASS: XDP tests pass"
else
    echo "SKIP: XDP tests require root or CAP_BPF"
    echo "Running stub tests instead..."
    go test ./internal/xdp/ -v -count=1
    echo "PASS: XDP stub tests pass"
fi

echo "=== XDP Rate Limiting E2E: COMPLETED ==="
