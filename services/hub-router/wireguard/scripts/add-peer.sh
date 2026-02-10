#!/bin/sh

# Script to add a new WireGuard peer dynamically
# Usage: ./add-peer.sh <public_key> <allowed_ips> [preshared_key]

PUBLIC_KEY=$1
ALLOWED_IPS=$2
PRESHARED_KEY=$3

if [ -z "$PUBLIC_KEY" ] || [ -z "$ALLOWED_IPS" ]; then
    echo "Usage: $0 <public_key> <allowed_ips> [preshared_key]"
    exit 1
fi

echo "Adding WireGuard peer..."

if [ -n "$PRESHARED_KEY" ]; then
    wg set wg0 peer "$PUBLIC_KEY" \
        allowed-ips "$ALLOWED_IPS" \
        preshared-key <(echo "$PRESHARED_KEY")
else
    wg set wg0 peer "$PUBLIC_KEY" \
        allowed-ips "$ALLOWED_IPS"
fi

# Save configuration
wg-quick save wg0

echo "Peer added successfully"