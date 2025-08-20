#!/bin/bash
set -e

echo "==========================================="
echo "  SASEWaddle Headend Server Starting"
echo "==========================================="

# Validate required environment variables
if [ -z "$CLUSTER_ID" ]; then
    echo "ERROR: CLUSTER_ID environment variable is required"
    exit 1
fi

if [ -z "$CLUSTER_API_KEY" ]; then
    echo "ERROR: CLUSTER_API_KEY environment variable is required" 
    exit 1
fi

echo "Cluster ID: $CLUSTER_ID"
echo "Manager URL: $MANAGER_URL"
echo "Auth Type: $HEADEND_AUTH_TYPE"

# Fetch configuration from Manager Service
echo "Fetching configuration from Manager Service..."
CONFIG_RESPONSE=$(curl -s -H "Authorization: Bearer $CLUSTER_API_KEY" \
    "$MANAGER_URL/api/v1/clusters/$CLUSTER_ID/headend-config")

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to fetch configuration from Manager Service"
    exit 1
fi

# Parse and apply configuration
echo "$CONFIG_RESPONSE" | jq . > /tmp/headend-config.json

# Extract WireGuard configuration
WG_PRIVATE_KEY=$(echo "$CONFIG_RESPONSE" | jq -r '.wireguard.private_key')
WG_IP_ADDRESS=$(echo "$CONFIG_RESPONSE" | jq -r '.wireguard.ip_address')
WG_LISTEN_PORT=$(echo "$CONFIG_RESPONSE" | jq -r '.wireguard.listen_port')

if [ "$WG_PRIVATE_KEY" = "null" ] || [ -z "$WG_PRIVATE_KEY" ]; then
    echo "ERROR: No WireGuard private key provided by Manager"
    exit 1
fi

# Enable IP forwarding and optimize network settings
echo "Configuring network settings..."
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv6/conf/all/forwarding
echo 1 > /proc/sys/net/ipv4/conf/all/proxy_arp
echo 0 > /proc/sys/net/ipv4/conf/all/send_redirects

# Increase network buffer sizes for high throughput
echo 134217728 > /proc/sys/net/core/rmem_max
echo 134217728 > /proc/sys/net/core/wmem_max
echo 134217728 > /proc/sys/net/core/netdev_max_backlog

# Setup WireGuard directories and permissions
mkdir -p /etc/wireguard
chown wireguard:wireguard /etc/wireguard

# Create WireGuard private key file
echo "$WG_PRIVATE_KEY" > /etc/wireguard/wg0.key
chmod 600 /etc/wireguard/wg0.key
chown wireguard:wireguard /etc/wireguard/wg0.key

# Create WireGuard interface configuration
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = $WG_IP_ADDRESS
ListenPort = $WG_LISTEN_PORT
PrivateKey = $WG_PRIVATE_KEY
SaveConfig = true

# Enable forwarding between WireGuard clients (peer-to-peer)
PostUp = iptables -A FORWARD -i wg0 -o wg0 -j ACCEPT

# Enable forwarding from WireGuard to external interfaces
PostUp = iptables -A FORWARD -i wg0 -o eth0 -j ACCEPT
PostUp = iptables -A FORWARD -i eth0 -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT

# Masquerade outgoing traffic to internet (for external destinations)
PostUp = iptables -t nat -A POSTROUTING -s $WG_IP_ADDRESS -o eth0 -j MASQUERADE

# Route internet-bound traffic through authentication proxy
# Only redirect traffic NOT destined for other WireGuard peers
PostUp = iptables -t nat -A PREROUTING -i wg0 -p tcp ! -d $WG_IP_ADDRESS -j REDIRECT --to-port 8444
PostUp = iptables -t nat -A PREROUTING -i wg0 -p udp ! -d $WG_IP_ADDRESS --dport 53 -j REDIRECT --to-port 8445

PostDown = iptables -D FORWARD -i wg0 -o wg0 -j ACCEPT
PostDown = iptables -D FORWARD -i wg0 -o eth0 -j ACCEPT  
PostDown = iptables -D FORWARD -i eth0 -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -s $WG_IP_ADDRESS -o eth0 -j MASQUERADE
PostDown = iptables -t nat -D PREROUTING -i wg0 -p tcp ! -d $WG_IP_ADDRESS -j REDIRECT --to-port 8444
PostDown = iptables -t nat -D PREROUTING -i wg0 -p udp ! -d $WG_IP_ADDRESS --dport 53 -j REDIRECT --to-port 8445

# Peers will be added dynamically by the Go application
EOF

echo "Starting WireGuard interface..."
wg-quick up wg0

# Verify WireGuard is running
if ! wg show wg0 >/dev/null 2>&1; then
    echo "ERROR: WireGuard interface failed to start"
    exit 1
fi

echo "WireGuard interface started successfully"
wg show wg0

# Setup intelligent routing for WireGuard traffic
echo "Setting up WireGuard traffic routing..."
export WG_IP_ADDRESS
/app/wireguard/scripts/setup-routing.sh

# Setup traffic mirroring iptables rules if enabled
MIRROR_ENABLED=$(echo "$CONFIG_RESPONSE" | jq -r '.mirror.enabled')
if [ "$MIRROR_ENABLED" = "true" ]; then
    echo "Configuring traffic mirroring..."
    /app/scripts/setup-mirror.sh
fi

# Setup TLS certificates
echo "Setting up TLS certificates..."
CERT_FILE="/certs/headend.crt"
KEY_FILE="/certs/headend.key"

# Create self-signed certificate if not provided
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "Generating self-signed TLS certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$KEY_FILE" -out "$CERT_FILE" \
        -subj "/C=US/ST=CA/L=SF/O=SASEWaddle/CN=headend-$CLUSTER_ID"
    chmod 600 "$KEY_FILE"
    chmod 644 "$CERT_FILE"
fi

# Export configuration for the Go application
export HEADEND_CONFIG_FILE="/tmp/headend-config.json"

echo "==========================================="
echo "  Configuration Complete"
echo "==========================================="
echo "WireGuard Interface: wg0"
echo "IP Address: $WG_IP_ADDRESS"
echo "Listen Port: $WG_LISTEN_PORT"
echo "Auth Type: $HEADEND_AUTH_TYPE"
echo "Mirror Enabled: $MIRROR_ENABLED"
echo "==========================================="

# Start the proxy server with proper signal handling
echo "Starting SASEWaddle Headend Proxy Server..."

# Trap signals to ensure graceful shutdown
trap 'echo "Shutting down..."; wg-quick down wg0; exit 0' SIGTERM SIGINT

# Start the application
exec /app/headend-proxy