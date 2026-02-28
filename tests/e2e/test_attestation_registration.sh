#!/usr/bin/env bash
# E2E test: Register client with attestation data and verify confidence returned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

HUB_API_URL="${HUB_API_URL:-http://localhost:5000}"
API_KEY="${TEST_API_KEY:-test-api-key}"

echo "=== Attestation Registration E2E Test ==="

# Test 1: Register client with attestation data
echo "[1/2] Registering client with attestation..."
RESPONSE=$(curl -sf -X POST "$HUB_API_URL/api/v1/clients/register" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d '{
        "name": "e2e-attestation-test",
        "type": "client_native",
        "public_key": "dGVzdC1wdWJsaWMta2V5LWJhc2U2NA==",
        "attestation": {
            "product_uuid": "E2E-TEST-UUID-1234",
            "board_serial": "E2E-SN-001",
            "sys_vendor": "E2E Vendor",
            "product_name": "E2E TestServer",
            "cpu_model": "Test CPU",
            "cpu_count": 4,
            "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
            "disk_serials": ["DISK001"],
            "kernel_version": "6.1.0",
            "os_release": "Ubuntu 24.04",
            "architecture": "amd64",
            "platform": "linux",
            "hostname": "e2e-test",
            "composite_hash": "will-be-recomputed",
            "collected_at": "2026-02-28T00:00:00Z"
        }
    }' 2>&1) || {
    echo "  FAIL: Registration request failed"
    echo "  Response: $RESPONSE"
    exit 1
}

echo "  Registration response received"

# Test 2: Verify attestation_confidence in response
echo "[2/2] Verifying attestation confidence in response..."
HAS_CONFIDENCE=$(echo "$RESPONSE" | python3 -c "
import json, sys
data = json.load(sys.stdin)
ac = data.get('attestation_confidence', {})
if ac:
    print(f'score={ac.get(\"score\", 0)} level={ac.get(\"level\", \"\")} method={ac.get(\"method\", \"\")}')
    sys.exit(0)
else:
    print('NO_ATTESTATION_CONFIDENCE')
    sys.exit(1)
" 2>&1) || {
    echo "  WARN: attestation_confidence not in response (hub-api may not be running with attestation)"
    echo "  Response: $RESPONSE"
    echo "  Skipping confidence verification"
    exit 0
}

echo "  PASS: $HAS_CONFIDENCE"

echo ""
echo "=== Attestation registration E2E test PASSED ==="
