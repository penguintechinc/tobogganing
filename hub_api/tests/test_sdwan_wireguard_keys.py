"""Tests for SASE WireGuard key management."""
from __future__ import annotations

import pytest

from hub_api.modules.sdwan.certs import WireGuardKeyManager
from hub_api.modules.sdwan.certs.wireguard_manager import WireGuardPeer


@pytest.fixture
def wg_manager():
    """Create a WireGuardKeyManager instance."""
    return WireGuardKeyManager()


@pytest.mark.asyncio
async def test_wg_manager_initialize(wg_manager):
    """Test WireGuardKeyManager initialization."""
    await wg_manager.initialize()
    assert wg_manager._initialized is True


@pytest.mark.asyncio
async def test_wg_manager_is_healthy(wg_manager):
    """Test health check."""
    await wg_manager.initialize()
    health = await wg_manager.is_healthy()
    assert health is True


@pytest.mark.asyncio
async def test_wg_manager_generate_wireguard_keys(wg_manager):
    """Test WireGuard key generation."""
    keys_dict = await wg_manager.generate_wireguard_keys(
        node_id="node-1",
        node_type="client",
    )

    assert "private_key" in keys_dict
    assert "public_key" in keys_dict
    assert "ip_address" in keys_dict
    assert len(keys_dict["private_key"]) > 40
    assert len(keys_dict["public_key"]) > 40
    assert keys_dict["ip_address"].startswith("10.200.")


@pytest.mark.asyncio
async def test_wg_manager_wireguard_keys_deterministic(wg_manager):
    """Test that WireGuard keys are deterministic for same node."""
    keys1 = await wg_manager.generate_wireguard_keys(
        node_id="node-1",
        node_type="client",
    )

    # Create new manager to test persistence
    wgm2 = WireGuardKeyManager()
    keys2 = await wgm2.generate_wireguard_keys(
        node_id="node-1",
        node_type="client",
    )

    # IPs should be the same
    assert keys1["ip_address"] == keys2["ip_address"]


@pytest.mark.asyncio
async def test_wg_manager_get_all_wireguard_peers(wg_manager):
    """Test getting all WireGuard peers."""
    await wg_manager.generate_wireguard_keys("node-1", "client")
    await wg_manager.generate_wireguard_keys("node-2", "headend")

    peers = await wg_manager.get_all_wireguard_peers()

    assert len(peers) == 2
    assert peers[0]["node_id"] in ["node-1", "node-2"]


@pytest.mark.asyncio
async def test_wg_manager_revoke_wireguard_keys(wg_manager):
    """Test revoking WireGuard keys."""
    await wg_manager.generate_wireguard_keys("node-1", "client")

    result = await wg_manager.revoke_wireguard_keys("node-1")
    assert result is True

    result = await wg_manager.revoke_wireguard_keys("non-existent")
    assert result is False


@pytest.mark.asyncio
async def test_wg_manager_get_wireguard_config(wg_manager):
    """Test getting WireGuard config."""
    keys = await wg_manager.generate_wireguard_keys("cluster-1", "headend")

    config = await wg_manager.get_wireguard_config("cluster-1")

    assert config["node_id"] == "cluster-1"
    assert config["public_key"] == keys["public_key"]
    assert config["ip_address"] == keys["ip_address"]


def test_wireguard_peer_dataclass():
    """Test WireGuardPeer dataclass."""
    peer = WireGuardPeer(
        node_id="node-1",
        public_key="public_key_b64",
        ip_address="10.200.1.1",
    )

    assert peer.node_id == "node-1"
    assert peer.public_key == "public_key_b64"
    assert peer.ip_address == "10.200.1.1"


@pytest.mark.asyncio
async def test_wireguard_ip_allocation_no_collision(wg_manager):
    """Test that WireGuard IP allocation does not collide for distinct clients."""
    # Allocate IPs for multiple clients
    ips = set()
    for i in range(20):
        node_id = f"node-{i}"
        keys = await wg_manager.generate_wireguard_keys(node_id, "client")
        ip = keys["ip_address"]

        # Verify IP is in correct range
        assert ip.startswith("10.200.")
        assert ip not in ips, f"IP collision detected: {ip} already allocated"
        ips.add(ip)

    # Verify we got 20 unique IPs
    assert len(ips) == 20


@pytest.mark.asyncio
async def test_wg_manager_shutdown(wg_manager):
    """Test shutdown."""
    await wg_manager.shutdown()
    # Should complete without raising
