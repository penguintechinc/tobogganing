"""
Basic unit tests for Manager Service certificate management
"""
import pytest
import asyncio
from datetime import datetime, timedelta

from manager.certs.certificate_manager import CertificateManager


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