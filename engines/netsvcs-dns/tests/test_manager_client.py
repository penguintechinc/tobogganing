"""Tests for ManagerClient gRPC client."""
from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path

from app.manager_client import ManagerClient


@pytest.mark.asyncio
async def test_enroll_success(stub_server_addr: str) -> None:
    """Test successful enrollment with bootstrap token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        result = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )

        assert result is True
        assert client.server_id == "test-server-1"
        assert client.jwt == "test-jwt-v1"
        assert client.refresh_token == "test-refresh-token"
        assert len(client.config) > 0

        await client.close()


@pytest.mark.asyncio
async def test_enroll_failure_invalid_token(stub_server_addr: str) -> None:
    """Test enrollment failure with invalid bootstrap token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        result = await client.enroll(
            bootstrap_token="invalid-token",
            hostname="test-host",
            version="0.1.0",
        )

        assert result is False
        assert client.server_id == ""

        await client.close()


@pytest.mark.asyncio
async def test_get_config(stub_server_addr: str) -> None:
    """Test fetching config with access JWT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # First enroll
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        # Then fetch config
        config = await client.get_config()
        assert config is not None
        assert "zones" in config
        assert "version" in config
        assert len(config["zones"]) > 0

        await client.close()


@pytest.mark.asyncio
async def test_refresh_token(stub_server_addr: str) -> None:
    """Test token refresh."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # First enroll
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        original_jwt = client.jwt

        # Refresh
        result = await client.refresh()
        assert result is True
        assert client.jwt == "test-jwt-refreshed"
        assert client.jwt != original_jwt

        await client.close()


@pytest.mark.asyncio
async def test_offline_cache_fallback(stub_server_addr: str) -> None:
    """Test offline cache fallback when server is unreachable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll and cache
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True
        cached_server_id = client.server_id

        await client.close()

        # Create new client pointing to invalid address
        offline_client = ManagerClient(
            grpc_addr="127.0.0.1:1",  # Invalid port
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Try to enroll with invalid address (should fail but load from cache)
        result = await offline_client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )

        # Should load from cache
        assert result is True
        assert offline_client.server_id == cached_server_id

        await offline_client.close()


@pytest.mark.asyncio
async def test_metadata_bearer_token(stub_server_addr: str) -> None:
    """Test that metadata contains bearer token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Metadata should be formatted correctly
        metadata = client._metadata("test-token")
        assert metadata == [("authorization", "Bearer test-token")]

        await client.close()


@pytest.mark.asyncio
async def test_cache_persistence(stub_server_addr: str) -> None:
    """Test that cache is persisted to disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        await client.close()

        # Check cache file exists
        cache_file = Path(tmpdir) / "manager_cache.json"
        assert cache_file.exists()

        # Load and verify cache content
        with open(cache_file, "r") as f:
            cache_data = json.load(f)

        assert cache_data["server_id"] == "test-server-1"
        assert cache_data["jwt"] == "test-jwt-v1"
        assert cache_data["refresh_token"] == "test-refresh-token"
