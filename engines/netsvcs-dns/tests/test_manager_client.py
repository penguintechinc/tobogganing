"""Tests for ManagerClient gRPC client."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
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


# S3 Tests: Control-plane gRPC methods


@pytest.mark.asyncio
async def test_check_ioc_blocked(stub_server_addr: str) -> None:
    """Test CheckIOC RPC returns blocked status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll first
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        # Check blocked domain
        result = await client.check_ioc("blocked.example.com")
        assert result["blocked"] is True
        assert result["feed_source"] == "test-feed"

        # Check clean domain
        result = await client.check_ioc("clean.example.com")
        assert result["blocked"] is False

        await client.close()


@pytest.mark.asyncio
async def test_check_ioc_fail_open(stub_server_addr: str) -> None:
    """Test CheckIOC fails open on error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create client with invalid address
        client = ManagerClient(
            grpc_addr="127.0.0.1:1",  # Invalid
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Manually set enrolled state
        client.server_id = "test"
        client.jwt = "test-jwt"

        # Even with error, check_ioc returns fail-open (blocked=False)
        result = await client.check_ioc("any.domain")
        assert result["blocked"] is False

        await client.close()


@pytest.mark.asyncio
async def test_validate_token_valid(stub_server_addr: str) -> None:
    """Test ValidateToken RPC with valid token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll first
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        # Validate token with allowed zones
        result = await client.validate_token("test-token-z1")
        assert result["valid"] is True
        assert "z1" in result["allowed_zone_ids"]

        # Validate token with multiple zones
        result = await client.validate_token("test-token-all")
        assert result["valid"] is True
        assert "z1" in result["allowed_zone_ids"]
        assert "z2" in result["allowed_zone_ids"]

        await client.close()


@pytest.mark.asyncio
async def test_validate_token_invalid(stub_server_addr: str) -> None:
    """Test ValidateToken RPC with invalid token."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll first
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        # Validate unknown token
        result = await client.validate_token("unknown-token")
        assert result["valid"] is False
        assert result["allowed_zone_ids"] == []

        await client.close()


@pytest.mark.asyncio
async def test_validate_token_fail_closed(stub_server_addr: str) -> None:
    """Test ValidateToken fails closed on error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create client with invalid address
        client = ManagerClient(
            grpc_addr="127.0.0.1:1",  # Invalid
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Manually set enrolled state
        client.server_id = "test"
        client.jwt = "test-jwt"

        # On error, validate_token returns fail-closed (valid=False)
        result = await client.validate_token("test-token")
        assert result["valid"] is False
        assert result["allowed_zone_ids"] == []

        await client.close()


@pytest.mark.asyncio
async def test_stream_config_updates(stub_server_addr: str) -> None:
    """Test StreamConfigUpdates RPC streams config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll first
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        # Collect updates from the stream
        updates = []

        async def on_update(config: dict) -> None:
            updates.append(config)

        # Start streaming (will receive one update from stub)
        await client.stream_config_updates(on_update)

        # Should have received at least one update
        assert len(updates) > 0
        assert "zones" in updates[0]
        assert "version" in updates[0]

        await client.close()


@pytest.mark.asyncio
async def test_send_heartbeat(stub_server_addr: str) -> None:
    """Test SendHeartbeat RPC with metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll first
        enrolled = await client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        # Send heartbeat with metrics
        metrics = {
            "queries_total": 1000,
            "cache_hits": 500,
            "errors": 5,
            "avg_response_ms": 25.5,
            "queries_by_type": {"A": 600, "AAAA": 400},
        }

        result = await client.send_heartbeat(metrics)
        assert "config_version" in result
        assert "should_sync" in result

        await client.close()


# P5 coverage backfill: init edge cases, channel setup, cache/RPC error branches


def test_init_chmod_oserror_ignored(tmp_path: Path) -> None:
    """__init__ tolerates OSError raised while chmod'ing a pre-existing cache dir."""
    with patch("app.manager_client.os.chmod", side_effect=OSError("no perm")):
        client = ManagerClient(
            grpc_addr="127.0.0.1:1",
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=str(tmp_path),
            server_name="dns-test",
        )

    assert client.cache_dir == tmp_path


def test_init_requires_tls_or_insecure_flag(tmp_path: Path) -> None:
    """__init__ raises RuntimeError when no TLS CA path and insecure flag disabled."""
    with pytest.raises(RuntimeError, match="Secure gRPC channel required"):
        ManagerClient(
            grpc_addr="127.0.0.1:1",
            tls_ca_path=None,
            insecure_dev_flag=False,
            cache_dir=str(tmp_path),
            server_name="dns-test",
        )


@pytest.mark.asyncio
async def test_create_channel_with_tls(tmp_path: Path) -> None:
    """_create_channel builds a secure channel when tls_ca_path is configured."""
    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(b"-----BEGIN CERTIFICATE-----\nMIIBAjCB2QIJ\n-----END CERTIFICATE-----\n")

    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=str(ca_path),
        insecure_dev_flag=False,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )

    channel = await client._create_channel()
    try:
        assert channel is not None
    finally:
        await channel.close()


@pytest.mark.asyncio
async def test_connect_idempotent(stub_server_addr: str, tmp_path: Path) -> None:
    """connect() is a no-op when a channel is already established."""
    client = ManagerClient(
        grpc_addr=stub_server_addr,
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )

    await client.connect()
    first_channel = client.channel
    await client.connect()

    assert client.channel is first_channel
    await client.close()


def test_load_cache_corrupt_file_returns_false(tmp_path: Path) -> None:
    """_load_cache returns False and does not raise on a corrupt cache file."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )
    client.cache_file.write_text("not valid json{{{")

    assert client._load_cache() is False


@pytest.mark.asyncio
async def test_get_config_not_enrolled(tmp_path: Path) -> None:
    """get_config returns None when not enrolled (no jwt/server_id)."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )

    assert await client.get_config() is None


@pytest.mark.asyncio
async def test_get_config_error_returns_none(tmp_path: Path) -> None:
    """get_config returns None when the RPC call fails."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )
    client.server_id = "test"
    client.jwt = "test-jwt"

    assert await client.get_config() is None
    await client.close()


@pytest.mark.asyncio
async def test_refresh_not_enrolled(tmp_path: Path) -> None:
    """refresh returns False when not enrolled (no refresh_token/server_id)."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )

    assert await client.refresh() is False


@pytest.mark.asyncio
async def test_refresh_error_returns_false(tmp_path: Path) -> None:
    """refresh returns False when the RPC call fails."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )
    client.server_id = "test"
    client.refresh_token = "test-refresh"

    assert await client.refresh() is False
    await client.close()


@pytest.mark.asyncio
async def test_check_ioc_not_enrolled(tmp_path: Path) -> None:
    """check_ioc fails open when not enrolled."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )

    assert await client.check_ioc("example.com") == {"blocked": False}


@pytest.mark.asyncio
async def test_validate_token_not_enrolled(tmp_path: Path) -> None:
    """validate_token fails closed when not enrolled."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )

    assert await client.validate_token("some-token") == {
        "valid": False,
        "allowed_zone_ids": [],
    }


@pytest.mark.asyncio
async def test_stream_config_updates_not_enrolled(tmp_path: Path) -> None:
    """stream_config_updates returns immediately when not enrolled."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )
    calls: list[dict] = []

    await client.stream_config_updates(lambda cfg: calls.append(cfg))

    assert calls == []


@pytest.mark.asyncio
async def test_stream_config_updates_error_logged(tmp_path: Path) -> None:
    """stream_config_updates logs and returns on an RPC error."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )
    client.server_id = "test"
    client.jwt = "test-jwt"

    async def on_update(cfg: dict) -> None:
        pass

    await client.stream_config_updates(on_update)  # should not raise
    await client.close()


@pytest.mark.asyncio
async def test_send_heartbeat_not_enrolled(tmp_path: Path) -> None:
    """send_heartbeat returns zeroed result when not enrolled."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )

    assert await client.send_heartbeat({}) == {
        "config_version": 0,
        "should_sync": False,
    }


@pytest.mark.asyncio
async def test_send_heartbeat_error_returns_zeroed(tmp_path: Path) -> None:
    """send_heartbeat returns zeroed result when the RPC call fails."""
    client = ManagerClient(
        grpc_addr="127.0.0.1:1",
        tls_ca_path=None,
        insecure_dev_flag=True,
        cache_dir=str(tmp_path),
        server_name="dns-test",
    )
    client.server_id = "test"
    client.jwt = "test-jwt"

    result = await client.send_heartbeat({"queries_total": 1})
    assert result == {"config_version": 0, "should_sync": False}
    await client.close()
