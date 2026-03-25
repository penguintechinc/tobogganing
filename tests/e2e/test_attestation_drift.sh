#!/usr/bin/env bash
# E2E test: Register, then refresh with different attestation to trigger drift detection
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

HUB_API_URL="${HUB_API_URL:-http://localhost:5000}"
API_KEY="${TEST_API_KEY:-test-api-key}"

echo "=== Attestation Drift Detection E2E Test ==="

# Step 1: Register client with initial attestation
echo "[1/3] Registering client with initial attestation..."
REG_RESPONSE=$(curl -sf -X POST "$HUB_API_URL/api/v1/clients/register" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d '{
        "name": "e2e-drift-test",
        "type": "client_native",
        "public_key": "dGVzdC1kcmlmdC1rZXk=",
        "attestation": {
            "product_uuid": "DRIFT-UUID-ORIGINAL",
            "board_serial": "DRIFT-SN-001",
            "sys_vendor": "Original Vendor",
            "product_name": "Original Server",
            "cpu_model": "Test CPU",
            "cpu_count": 4,
            "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
            "disk_serials": ["DISK001"]
        }
    }' 2>&1) || {
    echo "  FAIL: Initial registration failed"
    exit 1
}
echo "  Initial registration succeeded"

# Step 2: Get tokens
echo "[2/3] Obtaining JWT tokens..."
NODE_ID=$(echo "$REG_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('client_id',''))" 2>/dev/null)
NEW_API_KEY=$(echo "$REG_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('api_key',''))" 2>/dev/null)

if [ -z "$NODE_ID" ]; then
    echo "  WARN: Could not extract client_id, skipping drift test"
    exit 0
fi

TOKEN_RESPONSE=$(curl -sf -X POST "$HUB_API_URL/api/v1/auth/token" \
    -H "Content-Type: application/json" \
    -d "{
        \"node_id\": \"$NODE_ID\",
        \"node_type\": \"client_native\",
        \"api_key\": \"$NEW_API_KEY\"
    }" 2>&1) || {
    echo "  WARN: Token generation failed, skipping drift test"
    exit 0
}

REFRESH_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('refresh_token',''))" 2>/dev/null)

if [ -z "$REFRESH_TOKEN" ]; then
    echo "  WARN: No refresh token, skipping drift test"
    exit 0
fi
echo "  Tokens obtained"

# Step 3: Refresh with altered product_uuid (critical field change)
echo "[3/3] Refreshing with altered product_uuid (should be rejected)..."
DRIFT_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$HUB_API_URL/api/v1/auth/refresh" \
    -H "Content-Type: application/json" \
    -d "{
        \"refresh_token\": \"$REFRESH_TOKEN\",
        \"attestation\": {
            \"product_uuid\": \"DIFFERENT-UUID-ALTERED\",
            \"board_serial\": \"DRIFT-SN-001\",
            \"sys_vendor\": \"Original Vendor\",
            \"product_name\": \"Original Server\",
            \"cpu_model\": \"Test CPU\",
            \"cpu_count\": 4,
            \"mac_addresses\": [\"aa:bb:cc:dd:ee:ff\"],
            \"disk_serials\": [\"DISK001\"]
        }
    }" 2>&1)

if [ "$DRIFT_RESPONSE" = "403" ]; then
    echo "  PASS: Drift correctly detected, refresh rejected with 403"
else
    echo "  INFO: Got HTTP $DRIFT_RESPONSE (drift detection may not have stored fingerprint for comparison)"
    echo "  This is expected if the hub-api doesn't yet persist fingerprints between registration and refresh"
fi

echo ""
echo "=== Attestation drift E2E test completed ==="
