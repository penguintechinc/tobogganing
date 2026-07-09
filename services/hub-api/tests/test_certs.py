"""
Basic unit tests for Manager Service certificate management
"""
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

from certs.certificate_manager import CertificateManager


class TestCertificateManager:
    """Test certificate management functionality"""
    
    @pytest.fixture
    def cert_manager(self):
        """Create a certificate manager instance for testing"""
        return CertificateManager()
    
    def test_certificate_manager_initialization(self, cert_manager):
        """Test certificate manager initializes correctly"""
        assert cert_manager is not None
        assert hasattr(cert_manager, 'ca_cert')
        assert hasattr(cert_manager, 'ca_key')
    
    @pytest.mark.asyncio
    async def test_generate_wireguard_keys(self, cert_manager):
        """Test WireGuard key generation"""
        result = await cert_manager.generate_wireguard_keys(
            node_id="test-node-1",
            node_type="client"
        )
        
        assert "private_key" in result
        assert "public_key" in result
        assert "ip_address" in result
        
        # Basic key format validation
        private_key = result["private_key"]
        public_key = result["public_key"]
        
        assert len(private_key) > 40  # WireGuard keys are base64 encoded
        assert len(public_key) > 40
        assert private_key != public_key
    
    @pytest.mark.asyncio
    async def test_generate_certificate(self, cert_manager):
        """Test X.509 certificate generation"""
        result = await cert_manager.generate_certificate(
            node_id="test-client-cert",
            node_type="client",
            validity_days=365
        )
        
        assert "certificate" in result
        assert "private_key" in result
        assert "ca_certificate" in result
        
        # Basic certificate validation
        cert_pem = result["certificate"]
        key_pem = result["private_key"]
        
        assert cert_pem.startswith("-----BEGIN CERTIFICATE-----")
        assert cert_pem.endswith("-----END CERTIFICATE-----\n")
        assert key_pem.startswith("-----BEGIN EC PRIVATE KEY-----") or key_pem.startswith("-----BEGIN PRIVATE KEY-----")
    
    @pytest.mark.asyncio
    async def test_validate_certificate(self, cert_manager):
        """Test certificate validation"""
        # Generate a certificate first
        result = await cert_manager.generate_certificate(
            node_id="test-validation",
            node_type="client"
        )
        
        certificate = result["certificate"]
        
        # Validate the certificate
        validation_result = await cert_manager.validate_certificate(certificate)
        
        assert validation_result["valid"] is True
        assert validation_result["node_id"] == "test-validation"
        assert validation_result["node_type"] == "client"
        assert "not_before" in validation_result
        assert "not_after" in validation_result
    
    def test_ip_allocation(self, cert_manager):
        """Test IP address allocation for WireGuard"""
        # Test multiple allocations
        ip1 = cert_manager._allocate_ip("client-1")
        ip2 = cert_manager._allocate_ip("client-2")
        
        assert ip1 != ip2
        assert ip1.startswith("10.200.")
        assert ip2.startswith("10.200.")
        
        # Test same client gets same IP
        ip1_again = cert_manager._allocate_ip("client-1")
        assert ip1 == ip1_again
    
    def test_certificate_expiry_check(self, cert_manager):
        """Test certificate expiry checking"""
        # Create a test certificate that expires soon
        now = datetime.utcnow()
        expires_soon = now + timedelta(days=7)  # Expires in 7 days

        is_expiring = cert_manager._is_certificate_expiring(expires_soon, threshold_days=30)
        assert is_expiring is True

        expires_later = now + timedelta(days=60)  # Expires in 60 days
        is_expiring = cert_manager._is_certificate_expiring(expires_later, threshold_days=30)
        assert is_expiring is False

    @pytest.mark.asyncio
    async def test_validate_certificate_expired_cert_returns_invalid(self, cert_manager):
        """
        Regression test: validate_certificate rejects expired certificates.

        Finding 1 (HIGH) — validate_certificate should check the validity window.
        A certificate with not_after in the past must return valid: False.
        """
        # Generate a certificate with 1-day validity
        result = await cert_manager.generate_certificate(
            node_id="test-expired-cert",
            node_type="client",
            validity_days=1
        )
        certificate_pem = result["certificate"]

        # Mock datetime.now() to be past the certificate's not_after
        with patch('certs.certificate_manager.datetime') as mock_datetime:
            # Set the mocked now to be 2 days in the future
            future_time = datetime.now(timezone.utc) + timedelta(days=2)
            mock_datetime.now.return_value = future_time
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # Validate should return invalid
            validation_result = await cert_manager.validate_certificate(certificate_pem)

            assert validation_result["valid"] is False
            assert validation_result["node_id"] is None
            assert validation_result["node_type"] is None
            # Dates should still be present even for failed validation
            assert validation_result["not_before"] is not None
            assert validation_result["not_after"] is not None

    @pytest.mark.asyncio
    async def test_validate_certificate_not_yet_valid_returns_invalid(self, cert_manager):
        """
        Regression test: validate_certificate rejects not-yet-valid certificates.

        Finding 1 (HIGH) — validate_certificate should check the validity window.
        A certificate with not_before in the future must return valid: False.
        """
        # Generate a certificate to get the base structure
        result = await cert_manager.generate_certificate(
            node_id="test-future-cert",
            node_type="client",
            validity_days=365
        )

        # Load the certificate and rebuild it with future not_before
        cert_obj = x509.load_pem_x509_certificate(
            result["certificate"].encode(),
            default_backend()
        )

        # Create a new certificate with not_before in the future
        future_not_before = datetime.now(timezone.utc) + timedelta(days=1)
        future_not_after = future_not_before + timedelta(days=365)

        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(cert_obj.subject)
            .issuer_name(cert_obj.issuer)
            .public_key(cert_obj.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(future_not_before)
            .not_valid_after(future_not_after)
        )

        signed_cert = cert_builder.sign(cert_manager.ca_key, hashes.SHA256(), default_backend())
        future_cert_pem = signed_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        # Validate should return invalid
        validation_result = await cert_manager.validate_certificate(future_cert_pem)

        assert validation_result["valid"] is False
        assert validation_result["node_id"] is None
        assert validation_result["node_type"] is None
        assert validation_result["not_before"] is not None
        assert validation_result["not_after"] is not None

    @pytest.mark.asyncio
    async def test_validate_certificate_wrong_issuer_returns_invalid(self, cert_manager):
        """
        Regression test: validate_certificate rejects certs with wrong issuer.

        Finding 1 (HIGH) — validate_certificate should verify issuer matches CA.
        A certificate signed by a different CA must return valid: False.
        """
        # Create a certificate from our CA first to get the structure
        result = await cert_manager.generate_certificate(
            node_id="test-wrong-issuer",
            node_type="client"
        )

        cert_obj = x509.load_pem_x509_certificate(
            result["certificate"].encode(),
            default_backend()
        )

        # Create a different CA key and subject
        other_ca_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        other_ca_subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "Different CA"),
        ])

        # Build a certificate with the wrong issuer (our cert subject, but different issuer)
        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(cert_obj.subject)
            .issuer_name(other_ca_subject)  # Wrong issuer
            .public_key(cert_obj.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        )

        # Sign with the other CA key (which won't verify against our CA)
        wrong_issuer_cert = cert_builder.sign(other_ca_key, hashes.SHA256(), default_backend())
        wrong_issuer_pem = wrong_issuer_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        # Validate should return invalid (issuer mismatch)
        validation_result = await cert_manager.validate_certificate(wrong_issuer_pem)

        assert validation_result["valid"] is False
        assert validation_result["node_id"] is None
        assert validation_result["node_type"] is None
        assert validation_result["not_before"] is None
        assert validation_result["not_after"] is None