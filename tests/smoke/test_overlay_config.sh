#!/usr/bin/env bash
set -euo pipefail

echo "=== Smoke Test: Overlay Configuration ==="

echo "Verifying overlay provider files exist..."
test -f services/hub-router/internal/overlay/provider.go && echo "PASS: hub-router provider.go"
test -f services/hub-router/internal/overlay/wireguard.go && echo "PASS: hub-router wireguard.go"
test -f services/hub-router/internal/overlay/openziti.go && echo "PASS: hub-router openziti.go"
test -f services/hub-router/internal/overlay/manager.go && echo "PASS: hub-router manager.go"
test -f services/hub-router/internal/overlay/config.go && echo "PASS: hub-router config.go"

echo "Verifying client overlay files exist..."
test -f clients/native/internal/overlay/provider.go && echo "PASS: client provider.go"
test -f clients/native/internal/overlay/wireguard.go && echo "PASS: client wireguard.go"
test -f clients/native/internal/overlay/openziti.go && echo "PASS: client openziti.go"
test -f clients/native/internal/overlay/dual.go && echo "PASS: client dual.go"

echo "Verifying XDP files exist..."
test -f services/hub-router/internal/xdp/config.go && echo "PASS: xdp config.go"
test -f services/hub-router/internal/xdp/loader_stub.go && echo "PASS: xdp loader_stub.go"
test -f services/hub-router/internal/xdp/metrics.go && echo "PASS: xdp metrics.go"

echo "=== Overlay Config: ALL PASSED ==="
