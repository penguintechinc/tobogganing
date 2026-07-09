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


@pytest.mark.asyncio
async def test_validate_certificate_fails_on_malformed_input(cert_manager):
    """Test that validation fails closed on malformed certificate input."""
    result = await cert_manager.validate_certificate("")
    assert result["valid"] is False
    assert result["node_id"] is None

    result = await cert_manager.validate_certificate("not-a-cert")
    assert result["valid"] is False
    assert result["node_id"] is None

    result = await cert_manager.validate_certificate("-----BEGIN CERTIFICATE-----\ngarbage\n-----END CERTIFICATE-----")
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_validate_certificate_fails_on_expired_cert(cert_manager):
    """Test that validation fails closed on expired certificate."""
    # Generate an expired certificate
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.backends import default_backend

    private_key = cert_manager.ca_key
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "test-expired"),
    ])

    # Create certificate expired 1 day ago
    now = datetime.now(timezone.utc)
    expired_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=365))
        .not_valid_after(now - timedelta(days=1))
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    expired_pem = expired_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    result = await cert_manager.validate_certificate(expired_pem)

    assert result["valid"] is False
    assert result["node_id"] is None


@pytest.mark.asyncio
async def test_serial_numbers_unique_across_certs(cert_manager):
    """Test that certificate serial numbers are unique and non-colliding."""
    # Generate two certificates
    cert1_dict = await cert_manager.generate_certificate("node-1", "client")
    cert2_dict = await cert_manager.generate_certificate("node-2", "client")

    # Parse certificates to get serial numbers
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    cert1 = x509.load_pem_x509_certificate(
        cert1_dict["certificate"].encode(),
        default_backend()
    )
    cert2 = x509.load_pem_x509_certificate(
        cert2_dict["certificate"].encode(),
        default_backend()
    )

    # Verify serials are different
    assert cert1.serial_number != cert2.serial_number

    # Generate 10 more and verify all are unique
    serials = {cert1.serial_number, cert2.serial_number}
    for i in range(10):
        cert_dict = await cert_manager.generate_certificate(f"node-{i+3}", "client")
        cert = x509.load_pem_x509_certificate(
            cert_dict["certificate"].encode(),
            default_backend()
        )
        # Each serial should be unique
        assert cert.serial_number not in serials
        serials.add(cert.serial_number)


@pytest.mark.asyncio
async def test_wireguard_ip_allocation_no_collision(cert_manager):
    """Test that WireGuard IP allocation does not collide for distinct clients."""
    # Allocate IPs for multiple clients
    ips = set()
    for i in range(20):
        node_id = f"node-{i}"
        keys = await cert_manager.generate_wireguard_keys(node_id, "client")
        ip = keys["ip_address"]

        # Verify IP is in correct range
        assert ip.startswith("10.200.")
        assert ip not in ips, f"IP collision detected: {ip} already allocated"
        ips.add(ip)

    # Verify we got 20 unique IPs
    assert len(ips) == 20


@pytest.mark.asyncio
async def test_ca_certificate_validation_fails_on_non_ca_cert(cert_manager):
    """Test that loading non-CA certificates fails validation."""
    # Generate a regular client certificate (not a CA)
    cert_dict = await cert_manager.generate_certificate("test-client", "client")

    # Try to validate it as a CA — should fail
    cert_pem = cert_dict["certificate"].encode()
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

    # This should raise ValueError because cert is not a CA
    with pytest.raises(ValueError, match="(missing BasicConstraints|not a valid CA)"):
        cert_manager._validate_ca_certificate(cert)
