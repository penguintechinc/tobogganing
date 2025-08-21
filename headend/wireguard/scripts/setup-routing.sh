#!/bin/bash
# Setup intelligent routing for WireGuard traffic
# Supports both peer-to-peer and internet-bound traffic patterns

set -e

WG_INTERFACE="wg0"
WG_NETWORK="${WG_IP_ADDRESS%/*}/16"  # Extract network from IP (e.g., 10.200.0.0/16)
PROXY_TCP_PORT="8444"
PROXY_UDP_PORT="8445"

echo "Setting up routing for WireGuard network: $WG_NETWORK"

# Create custom routing table for WireGuard
echo "200 wireguard" >> /etc/iproute2/rt_tables

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv6/conf/all/forwarding

# Clear any existing rules
iptables -t nat -F PREROUTING 2>/dev/null || true
iptables -t nat -F POSTROUTING 2>/dev/null || true
iptables -F FORWARD 2>/dev/null || true

# 1. AUTHENTICATED TRAFFIC ROUTING (All traffic goes through Go proxy)
echo "Configuring authenticated traffic routing..."

# Allow forwarding from WireGuard to loopback (for proxy processing)
iptables -A FORWARD -i $WG_INTERFACE -o lo -j ACCEPT
iptables -A FORWARD -i lo -o $WG_INTERFACE -j ACCEPT

# Allow forwarding between WireGuard clients (after proxy authentication)
iptables -A FORWARD -i $WG_INTERFACE -o $WG_INTERFACE -m mark --mark 100 -j ACCEPT

# Allow forwarding to internet (after proxy authentication)
iptables -A FORWARD -i $WG_INTERFACE -o eth0 -m mark --mark 100 -j ACCEPT
iptables -A FORWARD -i eth0 -o $WG_INTERFACE -m state --state RELATED,ESTABLISHED -j ACCEPT

# Masquerade internet-bound traffic
iptables -t nat -A POSTROUTING -s $WG_NETWORK -o eth0 -j MASQUERADE

# 2. REDIRECT ALL TRAFFIC THROUGH AUTHENTICATION PROXY
echo "Redirecting all traffic through authentication proxy..."

# Redirect ALL TCP traffic through authentication proxy (including peer-to-peer)
iptables -t nat -A PREROUTING -i $WG_INTERFACE -p tcp -j REDIRECT --to-port $PROXY_TCP_PORT

# Redirect ALL UDP traffic through authentication proxy
iptables -t nat -A PREROUTING -i $WG_INTERFACE -p udp -j REDIRECT --to-port $PROXY_UDP_PORT

echo "✓ All traffic routing through authentication proxy configured"

# 3. LOGGING AND MONITORING
echo "Setting up traffic monitoring..."

# Log peer-to-peer traffic for monitoring
iptables -A FORWARD -i $WG_INTERFACE -o $WG_INTERFACE -j LOG --log-prefix "WG-P2P: " --log-level 6

# Log internet-bound traffic
iptables -A FORWARD -i $WG_INTERFACE -o eth0 -j LOG --log-prefix "WG-INET: " --log-level 6

echo "✓ Traffic monitoring configured"

# 4. SECURITY RULES
echo "Applying security rules..."

# Prevent spoofing - only allow traffic from assigned WireGuard IPs
iptables -A FORWARD -i $WG_INTERFACE ! -s $WG_NETWORK -j DROP

# Rate limiting to prevent abuse
iptables -A FORWARD -i $WG_INTERFACE -m limit --limit 1000/sec --limit-burst 2000 -j ACCEPT
iptables -A FORWARD -i $WG_INTERFACE -j DROP

echo "✓ Security rules applied"

echo "WireGuard routing setup complete!"
echo ""
echo "Traffic Patterns:"
echo "  📡 Peer-to-Peer: Client → WG Server → Other WG Clients"
echo "  🌐 Internet:     Client → WG Server → Go Proxy → Internet"
echo "  🛡️  Network:      $WG_NETWORK"
echo ""