"""
WireGuard key management for SASE module.

Provides X25519 key pair generation, peer management, and IP address allocation.
"""

import base64
import hashlib
from dataclasses import dataclass
from typing import Dict, List

import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

logger = structlog.get_logger()


@dataclass(slots=True)
class WireGuardPeer:
    """Represents a WireGuard peer with tenant isolation."""

    node_id: str
    public_key: str
    ip_address: str
    tenant_id: str = "default"


class WireGuardKeyManager:
    """
    Manages WireGuard keys for the cluster.

    Provides X25519 key pair generation and IP address allocation for managed nodes.
    """

    def __init__(self) -> None:
        """
        Initialize the WireGuardKeyManager.

        Sets up instance variables for peer tracking and IP allocations.
        """
        self._peers: Dict[str, WireGuardPeer] = {}
        self._ip_allocations: Dict[str, str] = {}
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the WireGuardKeyManager."""
        self._initialized = True
        logger.info("WireGuardKeyManager initialized")

    async def shutdown(self) -> None:
        """Shutdown the WireGuardKeyManager (cleanup/no-op)."""
        logger.info("WireGuardKeyManager shutdown")

    async def is_healthy(self) -> bool:
        """
        Check if the WireGuardKeyManager is healthy.

        Returns:
            True if initialized, False otherwise.
        """
        return self._initialized

    async def generate_wireguard_keys(
        self, node_id: str, node_type: str, tenant_id: str = "default"
    ) -> Dict[str, str]:
        """
        Generate WireGuard key pair for a node.

        Creates an X25519 key pair for WireGuard and allocates an IP address
        for the node.

        Args:
            node_id: Unique identifier for the node.
            node_type: Type of node (for reference, not used in key generation).
            tenant_id: Tenant identifier for multi-tenancy isolation.

        Returns:
            Dictionary containing:
            - private_key: Base64-encoded private key string (>40 chars)
            - public_key: Base64-encoded public key string (>40 chars)
            - ip_address: Allocated IP address starting with "10.200."
        """
        try:
            # Generate X25519 key pair
            private_key = x25519.X25519PrivateKey.generate()
            public_key = private_key.public_key()

            # Get raw bytes and base64 encode
            private_key_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            public_key_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )

            private_key_b64 = base64.b64encode(private_key_bytes).decode("utf-8")
            public_key_b64 = base64.b64encode(public_key_bytes).decode("utf-8")

            # Allocate IP address
            ip_address = self._allocate_ip(node_id)

            # Store peer information (keyed by node_id for simplicity; tenant in peer)
            self._peers[node_id] = WireGuardPeer(
                node_id=node_id,
                public_key=public_key_b64,
                ip_address=ip_address,
                tenant_id=tenant_id,
            )

            return {
                "private_key": private_key_b64,
                "public_key": public_key_b64,
                "ip_address": ip_address,
            }
        except Exception as e:
            logger.error("Failed to generate WireGuard keys", node_id=node_id, error=str(e))
            raise

    async def get_all_wireguard_peers(
        self, tenant_id: str = "default"
    ) -> List[Dict[str, str]]:
        """
        Get WireGuard peers for a specific tenant.

        Args:
            tenant_id: Tenant identifier to filter peers.

        Returns:
            List of peer dictionaries for the tenant (node_id, public_key, ip_address).
        """
        return [
            {
                "node_id": peer.node_id,
                "public_key": peer.public_key,
                "ip_address": peer.ip_address,
            }
            for peer in self._peers.values()
            if peer.tenant_id == tenant_id
        ]

    async def revoke_wireguard_keys(
        self, node_id: str, tenant_id: str = "default"
    ) -> bool:
        """
        Revoke WireGuard keys for a node in a specific tenant.

        Args:
            node_id: Node identifier to revoke.
            tenant_id: Tenant identifier for isolation.

        Returns:
            True if the node existed in the tenant and was removed, False otherwise.
        """
        if node_id in self._peers:
            peer = self._peers[node_id]
            # Only allow revocation if the node belongs to the specified tenant
            if peer.tenant_id == tenant_id:
                del self._peers[node_id]
                logger.info(
                    "Revoked WireGuard keys",
                    node_id=node_id,
                    tenant_id=tenant_id,
                )
                return True
        return False

    async def get_wireguard_config(self, cluster_id: str) -> Dict[str, any]:
        """
        Get WireGuard configuration for a cluster node.

        Args:
            cluster_id: Cluster identifier.

        Returns:
            Dictionary with peer configuration or empty dict if not found.
        """
        if cluster_id in self._peers:
            peer = self._peers[cluster_id]
            return {
                "node_id": peer.node_id,
                "public_key": peer.public_key,
                "ip_address": peer.ip_address,
            }
        return {}

    def _allocate_ip(self, node_id: str) -> str:
        """
        Allocate a collision-safe IP address for a node.

        Returns the same IP for the same node_id. Detects and prevents collisions
        across different node_ids by regenerating if collision detected.
        IPs are in the 10.200.0.0/16 range.

        Args:
            node_id: Node identifier.

        Returns:
            IP address string starting with "10.200." (unique per node).

        Raises:
            RuntimeError: If unable to allocate a collision-free IP after retries.
        """
        if node_id in self._ip_allocations:
            return self._ip_allocations[node_id]

        # Derive deterministic IP from node_id hash with collision detection
        max_attempts = 100
        attempt = 0

        while attempt < max_attempts:
            # Use hash with attempt counter to avoid infinite loops on collision
            hash_input = f"{node_id}#{attempt}".encode()
            hash_obj = hashlib.sha256(hash_input)
            hash_bytes = hash_obj.digest()

            # Use first 2 bytes for octet 3 and 4 (0-255 range, avoiding .0 and .255)
            octet3 = (int.from_bytes(hash_bytes[0:1], "big") % 254) + 1  # 1-254
            octet4 = (int.from_bytes(hash_bytes[1:2], "big") % 254) + 1  # 1-254

            ip_address = f"10.200.{octet3}.{octet4}"

            # Check for collision: IP already allocated to a different node
            ip_collision = False
            for existing_node, existing_ip in self._ip_allocations.items():
                if existing_ip == ip_address and existing_node != node_id:
                    ip_collision = True
                    break

            if not ip_collision:
                # No collision, allocate this IP
                self._ip_allocations[node_id] = ip_address
                return ip_address

            attempt += 1

        # Exhausted retries without finding collision-free IP
        raise RuntimeError(f"Failed to allocate collision-free IP for node {node_id} after {max_attempts} attempts")
