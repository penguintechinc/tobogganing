#!/bin/bash

# Health check script for SASEWaddle Docker Client
# Verifies WireGuard connectivity and authentication status

set -e

# Load authentication config
if [ -f "/config/auth.json" ]; then
    CLIENT_ID=$(jq -r '.client_id' /config/auth.json)
    ACCESS_TOKEN=$(jq -r '.access_token' /config/auth.json)
    HEADEND_URL=$(jq -r '.headend_url' /config/auth.json)
    MANAGER_URL=$(jq -r '.manager_url' /config/auth.json)
else
    echo "Health check: No authentication config found"
    exit 1
fi

# Check 1: WireGuard interface status
if ! wg show wg0 >/dev/null 2>&1; then
    echo "Health check FAIL: WireGuard interface not running"
    exit 1
fi

# Check 2: WireGuard peer connectivity
WG_ENDPOINT=$(wg show wg0 endpoints 2>/dev/null | awk '{print $2}' | head -1)
if [ -z "$WG_ENDPOINT" ]; then
    echo "Health check FAIL: No WireGuard peers configured"
    exit 1
fi

# Check 3: Network connectivity through tunnel
WG_IP=$(ip addr show wg0 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
if [ -z "$WG_IP" ]; then
    echo "Health check FAIL: WireGuard interface has no IP address"
    exit 1
fi

# Check 4: Ping headend through tunnel (if reachable)
HEADEND_HOST=$(echo "$HEADEND_URL" | sed 's|https://||' | sed 's|http://||' | cut -d: -f1)
if ! ping -c 1 -W 3 "$HEADEND_HOST" >/dev/null 2>&1; then
    echo "Health check WARNING: Cannot ping headend server (may be normal)"
fi

# Check 5: JWT token validity (if we can validate it)
if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
    # Try to validate token with manager
    VALIDATION_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        "$MANAGER_URL/api/v1/auth/validate" 2>/dev/null || echo "000")
    
    if [ "$VALIDATION_RESPONSE" != "200" ]; then
        echo "Health check WARNING: JWT token may be expired (HTTP $VALIDATION_RESPONSE)"
    fi
fi

# Check 6: Certificate files existence
if [ ! -f "/certs/client.crt" ] || [ ! -f "/certs/client.key" ]; then
    echo "Health check FAIL: Client certificates missing"
    exit 1
fi

# All checks passed
echo "Health check PASS: All systems operational"
echo "  WireGuard IP: $WG_IP"
echo "  Client ID: $CLIENT_ID"
echo "  Headend: $HEADEND_HOST"

exit 0