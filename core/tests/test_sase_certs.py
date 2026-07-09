"""Tests for SASE certificate management module."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from core.modules.sase.certs.certificate_manager import CertificateManager, WireGuardPeer


@pytest.fixture
def cert_manager():
    """Create a CertificateManager instance."""
    return CertificateManager()


@pytest.mark.asyncio
async def test_cert_manager_initialize(cert_manager):
    """Test CertificateManager initialization."""
    await cert_manager.initialize()
    assert cert_manager._initialized is True


@pytest.mark.asyncio
async def test_cert_manager_is_healthy(cert_manager):
    """Test health check."""
    await cert_manager.initialize()
    assert cert_manager.ca_cert is not None
    health = await cert_manager.is_healthy()
    assert health is True


@pytest.mark.asyncio
async def test_cert_manager_generate_certificate(cert_manager):
    """Test certificate generation."""
    cert_dict = await cert_manager.generate_certificate(
        node_id="node-1",
        node_type="client",
        validity_days=365,
    )

    assert "certificate" in cert_dict
    assert "private_key" in cert_dict
    assert "ca_certificate" in cert_dict
    assert "-----BEGIN CERTIFICATE-----" in cert_dict["certificate"]
    assert "-----BEGIN EC PRIVATE KEY-----" in cert_dict["private_key"]


@pytest.mark.asyncio
async def test_cert_manager_validate_certificate(cert_manager):
    """Test certificate validation."""
    # Generate a certificate first
    cert_dict = await cert_manager.generate_certificate(
        node_id="node-1",
        node_type="client",
        validity_days=365,
    )

    # Validate it
    result = await cert_manager.validate_certificate(cert_dict["certificate"])

    assert result["valid"] is True
    assert result["node_id"] == "node-1"
    assert result["node_type"] == "client"
    assert result["not_before"] is not None
    assert result["not_after"] is not None


@pytest.mark.asyncio
async def test_cert_manager_validate_invalid_certificate(cert_manager):
    """Test validating an invalid certificate."""
    result = await cert_manager.validate_certificate("invalid-cert")

    assert result["valid"] is False
    assert result["node_id"] is None


@pytest.mark.asyncio
async def test_cert_manager_generate_wireguard_keys(cert_manager):
    """Test WireGuard key generation."""
    keys_dict = await cert_manager.generate_wireguard_keys(
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
async def test_cert_manager_wireguard_keys_deterministic(cert_manager):
    """Test that WireGuard keys are deterministic for same node."""
    keys1 = await cert_manager.generate_wireguard_keys(
        node_id="node-1",
        node_type="client",
    )

    # Create new manager to test persistence
    cm2 = CertificateManager()
    keys2 = await cm2.generate_wireguard_keys(
        node_id="node-1",
        node_type="client",
    )

    # IPs should be the same
    assert keys1["ip_address"] == keys2["ip_address"]


@pytest.mark.asyncio
async def test_cert_manager_get_all_wireguard_peers(cert_manager):
    """Test getting all WireGuard peers."""
    await cert_manager.generate_wireguard_keys("node-1", "client")
    await cert_manager.generate_wireguard_keys("node-2", "headend")

    peers = await cert_manager.get_all_wireguard_peers()

    assert len(peers) == 2
    assert peers[0]["node_id"] in ["node-1", "node-2"]


@pytest.mark.asyncio
async def test_cert_manager_revoke_wireguard_keys(cert_manager):
    """Test revoking WireGuard keys."""
    await cert_manager.generate_wireguard_keys("node-1", "client")

    result = await cert_manager.revoke_wireguard_keys("node-1")
    assert result is True

    result = await cert_manager.revoke_wireguard_keys("non-existent")
    assert result is False


@pytest.mark.asyncio
async def test_cert_manager_get_wireguard_config(cert_manager):
    """Test getting WireGuard config."""
    keys = await cert_manager.generate_wireguard_keys("cluster-1", "headend")

    config = await cert_manager.get_wireguard_config("cluster-1")

    assert config["node_id"] == "cluster-1"
    assert config["public_key"] == keys["public_key"]
    assert config["ip_address"] == keys["ip_address"]


@pytest.mark.asyncio
async def test_cert_manager_generate_headend_certificate(cert_manager):
    """Test headend certificate generation."""
    cert_tuple = await cert_manager.generate_headend_certificate(
        cluster_id="cluster-1",
        name="headend.local",
        sans=["headend.local", "headend.example.com"],
    )

    private_key_pem, cert_pem, ca_cert_pem = cert_tuple

    assert "-----BEGIN EC PRIVATE KEY-----" in private_key_pem
    assert "-----BEGIN CERTIFICATE-----" in cert_pem
    assert "-----BEGIN CERTIFICATE-----" in ca_cert_pem


@pytest.mark.asyncio
async def test_cert_manager_generate_client_certificate(cert_manager):
    """Test client certificate generation."""
    cert_tuple = await cert_manager.generate_client_certificate(
        client_id="client-1",
        name="client",
        client_type="docker",
    )

    private_key_pem, cert_pem, ca_cert_pem = cert_tuple

    assert "-----BEGIN EC PRIVATE KEY-----" in private_key_pem
    assert "-----BEGIN CERTIFICATE-----" in cert_pem
    assert "-----BEGIN CERTIFICATE-----" in ca_cert_pem


@pytest.mark.asyncio
async def test_cert_manager_shutdown(cert_manager):
    """Test shutdown."""
    await cert_manager.shutdown()
    # Should complete without raising


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
