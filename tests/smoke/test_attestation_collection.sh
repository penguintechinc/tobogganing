#!/usr/bin/env bash
# Smoke test: Verify attestation collector runs on current machine
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLIENT_DIR="$PROJECT_ROOT/clients/native"
ATTEST_DIR="$CLIENT_DIR/internal/attestation"
SMOKE_TEST_FILE="$ATTEST_DIR/smoke_collection_test.go"

echo "=== Attestation Collection Smoke Test ==="

# Write a temporary Go test file inside the module so imports resolve
trap 'rm -f "$SMOKE_TEST_FILE"' EXIT

cat > "$SMOKE_TEST_FILE" << 'GOEOF'
package attestation

import (
	"context"
	"encoding/json"
	"os"
	"testing"
)

func TestSmokeCollection(t *testing.T) {
	cfg := CollectorConfig{
		EnableTPM: false,
	}
	c := NewCollector(cfg)
	fp, err := c.Collect(context.Background())
	if err != nil {
		t.Fatalf("Collect() failed: %v", err)
	}

	data, _ := json.MarshalIndent(fp, "", "  ")

	outPath := os.Getenv("SMOKE_OUTPUT_FILE")
	if outPath != "" {
		if err := os.WriteFile(outPath, data, 0644); err != nil {
			t.Fatalf("Failed to write output: %v", err)
		}
	}

	// Verify composite_hash is 64 hex chars (SHA-256)
	if len(fp.CompositeHash) != 64 {
		t.Fatalf("composite_hash should be 64 chars (SHA-256 hex), got %d: %s",
			len(fp.CompositeHash), fp.CompositeHash)
	}

	// Verify platform fields are non-empty
	if fp.Platform == "" {
		t.Fatal("platform is empty")
	}
	if fp.Architecture == "" {
		t.Fatal("architecture is empty")
	}

	t.Logf("composite_hash = %s...", fp.CompositeHash[:16])
	t.Logf("platform=%s arch=%s", fp.Platform, fp.Architecture)
}
GOEOF

OUTFILE=$(mktemp /tmp/attestation_smoke_XXXXXX.json)
trap 'rm -f "$SMOKE_TEST_FILE" "$OUTFILE"' EXIT

echo "[1/3] Running attestation collection via go test..."
cd "$CLIENT_DIR"
SMOKE_OUTPUT_FILE="$OUTFILE" go test -v -run TestSmokeCollection ./internal/attestation/ 2>&1

echo "[2/3] Verifying non-empty fingerprint..."
# Check that composite_hash exists and is 64 hex chars
HASH=$(python3 -c "import json; d=json.load(open('$OUTFILE')); print(d.get('composite_hash', ''))" 2>/dev/null || echo "")

if [ -n "$HASH" ] && [ ${#HASH} -eq 64 ]; then
    echo "  PASS: composite_hash = ${HASH:0:16}..."
else
    echo "  INFO: Output file not populated (test validates internally)"
    echo "  PASS: go test verified hash length"
fi

echo "[3/3] Verifying platform fields..."
PLATFORM=$(python3 -c "import json; d=json.load(open('$OUTFILE')); print(d.get('platform', ''))" 2>/dev/null || echo "")
ARCH=$(python3 -c "import json; d=json.load(open('$OUTFILE')); print(d.get('architecture', ''))" 2>/dev/null || echo "")

if [ -n "$PLATFORM" ] && [ -n "$ARCH" ]; then
    echo "  PASS: platform=$PLATFORM arch=$ARCH"
else
    echo "  INFO: Platform fields verified by go test assertions"
    echo "  PASS: go test verified platform fields"
fi

echo ""
echo "=== All attestation collection smoke tests PASSED ==="
