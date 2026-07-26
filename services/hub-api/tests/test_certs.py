"""Tests for certs/certificate_manager.py."""
import pytest
from certs.certificate_manager import CertificateManager


@pytest.fixture
def cert_mgr():
    return CertificateManager()


class TestCertificateManager:
    @pytest.mark.asyncio
    async def test_initialize_does_not_raise(self, cert_mgr):
        await cert_mgr.initialize()

    @pytest.mark.asyncio
    async def test_shutdown_does_not_raise(self, cert_mgr):
        await cert_mgr.shutdown()

    @pytest.mark.asyncio
    async def test_is_healthy_returns_true(self, cert_mgr):
        result = await cert_mgr.is_healthy()
        assert result is True

    @pytest.mark.asyncio
    async def test_issue_certificate_returns_dict_with_node_id(self, cert_mgr):
        result = await cert_mgr.issue_certificate("node-abc")
        assert isinstance(result, dict)
        assert result["node_id"] == "node-abc"

    @pytest.mark.asyncio
    async def test_revoke_certificate_returns_true(self, cert_mgr):
        result = await cert_mgr.revoke_certificate("node-abc")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_certificate_returns_none(self, cert_mgr):
        result = await cert_mgr.get_certificate("node-abc")
        assert result is None
