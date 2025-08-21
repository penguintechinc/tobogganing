#!/bin/sh

# Setup traffic mirroring using iptables TEE target
echo "Setting up traffic mirroring..."

# Parse mirror destinations
IFS=',' read -ra DESTINATIONS <<< "$TRAFFIC_MIRROR_DESTINATIONS"

for dest in "${DESTINATIONS[@]}"; do
    echo "Adding mirror destination: $dest"
    
    # Add iptables rule to duplicate packets
    iptables -t mangle -A PREROUTING -j TEE --gateway ${dest%:*}
    iptables -t mangle -A POSTROUTING -j TEE --gateway ${dest%:*}
done

# If using tc for mirroring (alternative method)
if [ "${TRAFFIC_MIRROR_USE_TC}" = "true" ]; then
    tc qdisc add dev wg0 ingress
    tc filter add dev wg0 parent ffff: \
        protocol all u32 match u8 0 0 \
        action mirred egress mirror dev eth0
fi

echo "Traffic mirroring setup complete"