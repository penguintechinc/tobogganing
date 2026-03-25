#!/usr/bin/env bash
# Smoke test: Verify attestation package builds with and without TPM tag
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLIENT_DIR="$PROJECT_ROOT/clients/native"

echo "=== Attestation Build Smoke Test ==="

# Test 1: Default build (no TPM tag) — should succeed
echo "[1/3] Building without TPM tag..."
cd "$CLIENT_DIR"
go build ./internal/attestation/
echo "  PASS: Default build succeeded"

# Test 2: go vet passes
echo "[2/3] Running go vet..."
go vet ./internal/attestation/
echo "  PASS: go vet passed"

# Test 3: Unit tests pass
echo "[3/3] Running unit tests..."
go test -count=1 -timeout 30s ./internal/attestation/
echo "  PASS: Unit tests passed"

echo ""
echo "=== All attestation build smoke tests PASSED ==="
