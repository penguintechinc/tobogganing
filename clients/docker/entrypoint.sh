#!/bin/bash
set -e

echo "==========================================="
echo "  SASEWaddle Docker Client Starting"
echo "==========================================="

# Validate required environment variables
if [ -z "$MANAGER_URL" ]; then
    echo "ERROR: MANAGER_URL environment variable is required"
    exit 1
fi

if [ -z "$CLIENT_API_KEY" ]; then
    echo "ERROR: CLIENT_API_KEY environment variable is required"
    exit 1
fi

# Generate client name if not provided (include architecture info)
if [ -z "$CLIENT_NAME" ]; then
    ARCH=$(uname -m)
    CLIENT_NAME="docker-client-${ARCH}-$(hostname | cut -c1-8)"
fi

echo "Client Name: $CLIENT_NAME"
echo "Client Type: $CLIENT_TYPE"
echo "Manager URL: $MANAGER_URL"
echo "Architecture: $(uname -m)"

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv6/conf/all/forwarding

# Generate WireGuard keys
echo "Generating WireGuard keys..."
wg genkey | tee /etc/wireguard/privatekey | wg pubkey > /etc/wireguard/publickey
chmod 600 /etc/wireguard/privatekey

PUBLIC_KEY=$(cat /etc/wireguard/publickey)
echo "Public Key: $PUBLIC_KEY"

# Step 1: Register client with Manager Service
echo "Registering with SASEWaddle Manager Service..."
REGISTRATION_RESPONSE=$(curl -sf -X POST "$MANAGER_URL/api/v1/clients/register" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CLIENT_API_KEY" \
    -d "{
        \"name\": \"$CLIENT_NAME\",
        \"type\": \"$CLIENT_TYPE\",
        \"public_key\": \"$PUBLIC_KEY\",
        \"location\": {
            \"region\": \"${REGION:-us-east-1}\",
            \"datacenter\": \"${DATACENTER:-dc1}\",
            \"architecture\": \"$(uname -m)\"
        }
    }")

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to register with Manager Service"
    exit 1
fi

echo "Registration successful!"

# Parse registration response
CLIENT_ID=$(echo "$REGISTRATION_RESPONSE" | jq -r '.client_id')
NEW_API_KEY=$(echo "$REGISTRATION_RESPONSE" | jq -r '.api_key')
HEADEND_URL=$(echo "$REGISTRATION_RESPONSE" | jq -r '.cluster.headend_url')
CLIENT_CERT=$(echo "$REGISTRATION_RESPONSE" | jq -r '.certificates.cert')
CLIENT_KEY=$(echo "$REGISTRATION_RESPONSE" | jq -r '.certificates.key')
CA_CERT=$(echo "$REGISTRATION_RESPONSE" | jq -r '.certificates.ca')

echo "Client ID: $CLIENT_ID"
echo "Assigned Headend: $HEADEND_URL"

# Validate registration response
if [ "$CLIENT_ID" = "null" ] || [ -z "$CLIENT_ID" ]; then
    echo "ERROR: Invalid registration response - no client ID"
    exit 1
fi

if [ "$HEADEND_URL" = "null" ] || [ -z "$HEADEND_URL" ]; then
    echo "ERROR: Invalid registration response - no headend URL"
    exit 1
fi

# Step 2: Save certificates for dual authentication
echo "Setting up client certificates..."
echo "$CLIENT_CERT" > /certs/client.crt
echo "$CLIENT_KEY" > /certs/client.key
echo "$CA_CERT" > /certs/ca.crt
chmod 600 /certs/client.key
chmod 644 /certs/client.crt /certs/ca.crt

# Update API key for authenticated requests
CLIENT_API_KEY="$NEW_API_KEY"

# Step 3: Get JWT token for dual authentication
echo "Obtaining JWT token for application-level authentication..."
JWT_RESPONSE=$(curl -sf -X POST "$MANAGER_URL/api/v1/auth/token" \
    -H "Content-Type: application/json" \
    -d "{
        \"node_id\": \"$CLIENT_ID\",
        \"node_type\": \"$CLIENT_TYPE\",
        \"api_key\": \"$CLIENT_API_KEY\"
    }")

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to obtain JWT token"
    exit 1
fi

# Parse JWT response
ACCESS_TOKEN=$(echo "$JWT_RESPONSE" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$JWT_RESPONSE" | jq -r '.refresh_token')

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    echo "ERROR: Failed to obtain valid JWT token"
    exit 1
fi

echo "JWT token obtained successfully"

# Step 4: Get WireGuard configuration and keys from Manager
echo "Requesting WireGuard configuration..."
WG_CONFIG_RESPONSE=$(curl -sf -X POST "$MANAGER_URL/api/v1/wireguard/keys" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d "{
        \"node_id\": \"$CLIENT_ID\",
        \"node_type\": \"$CLIENT_TYPE\",
        \"api_key\": \"$CLIENT_API_KEY\"
    }")

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to get WireGuard configuration"
    exit 1
fi

# Parse WireGuard configuration
WG_PRIVATE_KEY=$(echo "$WG_CONFIG_RESPONSE" | jq -r '.wireguard.private_key')
WG_PUBLIC_KEY=$(echo "$WG_CONFIG_RESPONSE" | jq -r '.wireguard.public_key')
WG_IP_ADDRESS=$(echo "$WG_CONFIG_RESPONSE" | jq -r '.wireguard.ip_address')
WG_NETWORK_CIDR=$(echo "$WG_CONFIG_RESPONSE" | jq -r '.wireguard.network_cidr')

if [ "$WG_PRIVATE_KEY" = "null" ] || [ -z "$WG_PRIVATE_KEY" ]; then
    echo "ERROR: Invalid WireGuard configuration response"
    exit 1
fi

echo "WireGuard configuration obtained:"
echo "  IP Address: $WG_IP_ADDRESS"
echo "  Network: $WG_NETWORK_CIDR"

# Step 5: Extract headend connection details
HEADEND_HOST=$(echo "$HEADEND_URL" | sed 's|https://||' | sed 's|http://||' | cut -d: -f1)
HEADEND_WG_PORT="51820"  # Standard WireGuard port

# Save WireGuard private key
echo "$WG_PRIVATE_KEY" > /etc/wireguard/wg0.key
chmod 600 /etc/wireguard/wg0.key

# Get headend public key (would typically be provided in the response)
# For now, we'll need to connect and retrieve it
echo "Retrieving headend WireGuard public key..."
HEADEND_PUBLIC_KEY=$(curl -sf -H "Authorization: Bearer $ACCESS_TOKEN" \
    "$MANAGER_URL/api/v1/clusters/$(echo $HEADEND_URL | cut -d'/' -f3 | cut -d'.' -f1)/wireguard-pubkey" 2>/dev/null || echo "")

# If we can't get the public key from API, we'll discover it during connection
if [ "$HEADEND_PUBLIC_KEY" = "null" ] || [ -z "$HEADEND_PUBLIC_KEY" ]; then
    echo "Warning: Could not retrieve headend public key from API, will discover during connection"
    HEADEND_PUBLIC_KEY="PLACEHOLDER"
fi

# Step 6: Create WireGuard configuration with dual authentication
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = $WG_IP_ADDRESS
PrivateKey = $WG_PRIVATE_KEY
DNS = 10.200.0.1

# Embed JWT token and certificates for dual authentication
PostUp = echo "JWT:$ACCESS_TOKEN" > /tmp/auth_token
PostUp = echo "HOST:$HEADEND_HOST" >> /tmp/auth_token
PostDown = rm -f /tmp/auth_token

[Peer]
PublicKey = $HEADEND_PUBLIC_KEY
Endpoint = $HEADEND_HOST:$HEADEND_WG_PORT
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
EOF

echo "WireGuard configuration created successfully"

# Step 7: Start WireGuard VPN connection
echo "Starting WireGuard VPN connection..."
if ! wg-quick up wg0; then
    echo "ERROR: Failed to start WireGuard interface"
    exit 1
fi

# Verify WireGuard is running
if ! wg show wg0 >/dev/null 2>&1; then
    echo "ERROR: WireGuard interface failed to initialize"
    exit 1
fi

echo "WireGuard VPN connected successfully!"
wg show wg0

# Save authentication tokens and certificates for background services
cat > /config/auth.json <<EOF
{
    "client_id": "$CLIENT_ID",
    "access_token": "$ACCESS_TOKEN", 
    "refresh_token": "$REFRESH_TOKEN",
    "headend_url": "$HEADEND_URL",
    "manager_url": "$MANAGER_URL",
    "client_api_key": "$CLIENT_API_KEY"
}
EOF
chmod 600 /config/auth.json

echo "==========================================="
echo "  SASEWaddle Client Initialization Complete"
echo "==========================================="
echo "Client ID: $CLIENT_ID"
echo "WireGuard IP: $WG_IP_ADDRESS"
echo "Headend URL: $HEADEND_URL"
echo "Dual Authentication: Certificate + JWT"
echo "==========================================="

# Start background services
echo "Starting background services..."

# Start health check loop
if [ -f "/app/scripts/health-check.sh" ]; then
    echo "Starting health monitoring..."
    /app/scripts/health-check.sh &
    HEALTH_PID=$!
fi

# Start certificate and JWT renewal loop  
if [ -f "/app/scripts/auth-renewal.sh" ]; then
    echo "Starting authentication renewal service..."
    /app/scripts/auth-renewal.sh &
    RENEWAL_PID=$!
fi

# Start connection monitoring and restart loop
echo "Starting connection monitoring..."

# Trap signals for graceful shutdown
trap 'echo "Shutting down SASEWaddle client..."; wg-quick down wg0 2>/dev/null || true; kill $HEALTH_PID $RENEWAL_PID 2>/dev/null || true; exit 0' SIGTERM SIGINT

# Main monitoring loop
while true; do
    # Check WireGuard interface status
    if ! wg show wg0 > /dev/null 2>&1; then
        echo "$(date): WireGuard interface down, attempting to restart..."
        wg-quick down wg0 2>/dev/null || true
        sleep 5
        
        if ! wg-quick up wg0; then
            echo "$(date): Failed to restart WireGuard, will retry in 30 seconds..."
        else
            echo "$(date): WireGuard interface restored successfully"
        fi
    fi
    
    # Check connectivity to headend
    if ! ping -c 1 -W 5 $(echo "$HEADEND_HOST" | cut -d: -f1) >/dev/null 2>&1; then
        echo "$(date): Warning: Cannot reach headend server"
    fi
    
    sleep 30
done