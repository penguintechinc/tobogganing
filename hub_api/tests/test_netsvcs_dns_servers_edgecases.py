"""Edge-case tests for dns_servers.py error/branch handling.

Complements tests/test_netsvcs_dns_servers.py (happy-path + auth) with the
not-found/exception branches for list/get/delete/metrics, register_server
validation failures, and the refresh-token rotation error branches
(missing/invalid/wrong-type/subject-mismatch/aud-mismatch/inactive-server/
cache-read-error) that the existing suite doesn't reach.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.modules.netsvcs.managers.server_manager import DNSServerRecord


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Test app with netsvcs module registered."""
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = "default"
    app.config["ENROLLMENT_BOOTSTRAP_TOKEN"] = "test-bootstrap-token"

    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def valid_tenant_token(app_with_netsvcs: Quart) -> str:
    """A valid tenant-scoped JWT with dns:read/write scope."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "scope": "dns:read dns:write",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


def _server_record() -> DNSServerRecord:
    return DNSServerRecord(
        id="server-1",
        name="dns-1",
        status="online",
        version="1.0.0",
        region="us-east-1",
        hostname="dns1.example.com",
        last_heartbeat=datetime.now(timezone.utc),
        tenant="test-tenant",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _feature_flag_on() -> object:
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True) as m:
        yield m


# --- list/get/delete/metrics not-found + exception branches ----------------


@pytest.mark.asyncio
async def test_list_dns_servers_exception_returns_500(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """list_dns_servers() returns 500 when the manager raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.get_all_servers = AsyncMock(side_effect=RuntimeError("db down"))
        MockSM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/dns-servers",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_dns_server_not_found(app_with_netsvcs: Quart, valid_tenant_token: str) -> None:
    """get_dns_server() returns 404 when the server doesn't exist."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.get_server = AsyncMock(return_value=None)
        MockSM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/dns-servers/nonexistent",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_dns_server_exception_returns_500(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """get_dns_server() returns 500 when the manager raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.get_server = AsyncMock(side_effect=RuntimeError("boom"))
        MockSM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/dns-servers/server-1",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_delete_dns_server_not_found(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """delete_dns_server() returns 404 when the server doesn't exist."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.delete_server = AsyncMock(return_value=False)
        MockSM.return_value = mock_mgr

        response = await client.delete(
            "/api/v1/netsvcs/dns-servers/nonexistent",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_dns_server_exception_returns_500(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """delete_dns_server() returns 500 when the manager raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.delete_server = AsyncMock(side_effect=RuntimeError("boom"))
        MockSM.return_value = mock_mgr

        response = await client.delete(
            "/api/v1/netsvcs/dns-servers/server-1",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_dns_server_metrics_invalid_hours_defaults(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """get_dns_server_metrics() falls back to 24h on a non-numeric hours param."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.get_metrics = AsyncMock(return_value=[])
        MockSM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/dns-servers/server-1/metrics?hours=notanumber",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_dns_server_metrics_exception_returns_500(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """get_dns_server_metrics() returns 500 when the manager raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.get_metrics = AsyncMock(side_effect=RuntimeError("boom"))
        MockSM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/dns-servers/server-1/metrics",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

    assert response.status_code == 500


# --- register_server validation branches ------------------------------------


@pytest.mark.asyncio
async def test_register_server_missing_required_field(app_with_netsvcs: Quart) -> None:
    """register_server() returns 400 when a required field is missing."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = "test-bootstrap-token"
    client = app_with_netsvcs.test_client()

    response = await client.post(
        "/api/v1/netsvcs/dns-servers/register",
        json={"name": "dns-1", "hostname": "dns1.example.com"},  # missing version/region
        headers={"Authorization": "Bearer test-bootstrap-token"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_server_missing_key_provider_returns_500(
    app_with_netsvcs: Quart,
) -> None:
    """register_server() returns 500 when KEY_PROVIDER isn't configured."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = "test-bootstrap-token"
    client = app_with_netsvcs.test_client()

    with (
        patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM,
        patch.object(app_with_netsvcs.config, "get") as mock_config_get,
    ):
        mock_mgr = AsyncMock()
        mock_mgr.initialize = AsyncMock()
        mock_mgr.register_server = AsyncMock(return_value=_server_record())
        MockSM.return_value = mock_mgr

        def side_effect(key: str, default: object = None) -> object:
            if key == "KEY_PROVIDER":
                return None
            if key == "ENROLLMENT_TENANT":
                return "default"
            return default

        mock_config_get.side_effect = side_effect

        response = await client.post(
            "/api/v1/netsvcs/dns-servers/register",
            json={
                "name": "dns-1",
                "hostname": "dns1.example.com",
                "version": "1.0.0",
                "region": "us-east-1",
            },
            headers={"Authorization": "Bearer test-bootstrap-token"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_register_server_exception_returns_500(app_with_netsvcs: Quart) -> None:
    """register_server() returns 500 when the manager raises unexpectedly."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = "test-bootstrap-token"
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.initialize = AsyncMock()
        mock_mgr.register_server = AsyncMock(side_effect=RuntimeError("boom"))
        MockSM.return_value = mock_mgr

        response = await client.post(
            "/api/v1/netsvcs/dns-servers/register",
            json={
                "name": "dns-1",
                "hostname": "dns1.example.com",
                "version": "1.0.0",
                "region": "us-east-1",
            },
            headers={"Authorization": "Bearer test-bootstrap-token"},
        )

    assert response.status_code == 500


# --- get_server_config exception branch -------------------------------------


@pytest.mark.asyncio
async def test_get_server_config_exception_returns_500(app_with_netsvcs: Quart) -> None:
    """get_server_config() returns 500 when ConfigService raises."""
    from hub_api.auth.jwt import encode_access_token

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "resolver:server-1",
        "iss": "tobogganing",
        "aud": "headend",
        "tenant": "default",
        "scope": "dns:config:read",
    }
    machine_jwt = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.modules.netsvcs.api.dns_servers.ConfigService") as MockCS:
        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(side_effect=RuntimeError("boom"))
        MockCS.return_value = mock_cs

        response = await client.get(
            "/api/v1/netsvcs/dns-servers/server-1/config",
            headers={"Authorization": f"Bearer {machine_jwt}"},
        )

    assert response.status_code == 500


# --- server_heartbeat branches ----------------------------------------------


@pytest.mark.asyncio
async def test_server_heartbeat_subject_mismatch_returns_403(app_with_netsvcs: Quart) -> None:
    """server_heartbeat() returns 403 when the machine-JWT subject doesn't match server_id."""
    from hub_api.auth.jwt import encode_access_token

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "resolver:OTHER-server",
        "iss": "tobogganing",
        "aud": "headend",
        "tenant": "default",
        "scope": "metrics:write",
    }
    machine_jwt = await encode_access_token(claims, provider, ttl_hours=1)

    response = await client.post(
        "/api/v1/netsvcs/dns-servers/server-1/heartbeat",
        json={"queries_total": 1},
        headers={"Authorization": f"Bearer {machine_jwt}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_server_heartbeat_not_found_returns_404(app_with_netsvcs: Quart) -> None:
    """server_heartbeat() returns 404 when record_heartbeat reports server not found."""
    from hub_api.auth.jwt import encode_access_token

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "resolver:server-1",
        "iss": "tobogganing",
        "aud": "headend",
        "tenant": "default",
        "scope": "metrics:write",
    }
    machine_jwt = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.record_heartbeat = AsyncMock(return_value=False)
        MockSM.return_value = mock_mgr

        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/heartbeat",
            json={"queries_total": 1},
            headers={"Authorization": f"Bearer {machine_jwt}"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_server_heartbeat_exception_returns_500(app_with_netsvcs: Quart) -> None:
    """server_heartbeat() returns 500 when record_heartbeat raises."""
    from hub_api.auth.jwt import encode_access_token

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "resolver:server-1",
        "iss": "tobogganing",
        "aud": "headend",
        "tenant": "default",
        "scope": "metrics:write",
    }
    machine_jwt = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM:
        mock_mgr = AsyncMock()
        mock_mgr.record_heartbeat = AsyncMock(side_effect=RuntimeError("boom"))
        MockSM.return_value = mock_mgr

        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/heartbeat",
            json={"queries_total": 1},
            headers={"Authorization": f"Bearer {machine_jwt}"},
        )

    assert response.status_code == 500


# --- refresh_server_token branches -------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_missing_bearer_prefix_returns_401(
    app_with_netsvcs: Quart,
) -> None:
    """refresh_server_token() returns 401 without a Bearer-prefixed Authorization header."""
    client = app_with_netsvcs.test_client()

    response = await client.post(
        "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
        headers={"Authorization": "NotBearer sometoken"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_empty_after_bearer_returns_401(app_with_netsvcs: Quart) -> None:
    """refresh_server_token() returns 401 when the token is empty after 'Bearer '."""
    client = app_with_netsvcs.test_client()

    response = await client.post(
        "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
        headers={"Authorization": "Bearer "},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_missing_key_provider_or_cache_returns_500(
    app_with_netsvcs: Quart,
) -> None:
    """refresh_server_token() returns 500 when KEY_PROVIDER or CACHE is unset."""
    client = app_with_netsvcs.test_client()

    with patch.object(app_with_netsvcs.config, "get") as mock_config_get:
        mock_config_get.side_effect = lambda key, default=None: None

        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_refresh_token_invalid_token_returns_401(app_with_netsvcs: Quart) -> None:
    """refresh_server_token() returns 401 when decode_token() returns None."""
    client = app_with_netsvcs.test_client()

    with patch("hub_api.auth.jwt.decode_token", return_value=None):
        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
            headers={"Authorization": "Bearer garbage-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_wrong_token_type_returns_401(app_with_netsvcs: Quart) -> None:
    """refresh_server_token() returns 401 when the token isn't a refresh token."""
    client = app_with_netsvcs.test_client()

    with patch(
        "hub_api.auth.jwt.decode_token",
        return_value={"token_type": "access", "sub": "resolver:server-1"},
    ):
        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
            headers={"Authorization": "Bearer access-not-refresh"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_subject_mismatch_returns_403(app_with_netsvcs: Quart) -> None:
    """refresh_server_token() returns 403 when the token subject doesn't match server_id."""
    client = app_with_netsvcs.test_client()

    with patch(
        "hub_api.auth.jwt.decode_token",
        return_value={"token_type": "refresh", "sub": "resolver:OTHER-server"},
    ):
        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
            headers={"Authorization": "Bearer refresh-token"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token_missing_tenant_returns_401(app_with_netsvcs: Quart) -> None:
    """refresh_server_token() returns 401 when the refresh token has no tenant claim."""
    client = app_with_netsvcs.test_client()

    with patch(
        "hub_api.auth.jwt.decode_token",
        return_value={"token_type": "refresh", "sub": "resolver:server-1"},
    ):
        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
            headers={"Authorization": "Bearer refresh-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_server_not_active_returns_403(app_with_netsvcs: Quart) -> None:
    """refresh_server_token() returns 403 when the server is missing or not online."""
    client = app_with_netsvcs.test_client()

    with (
        patch(
            "hub_api.auth.jwt.decode_token",
            return_value={
                "token_type": "refresh",
                "sub": "resolver:server-1",
                "tenant": "default",
            },
        ),
        patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM,
    ):
        mock_mgr = AsyncMock()
        mock_mgr.get_server = AsyncMock(return_value=None)
        MockSM.return_value = mock_mgr

        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
            headers={"Authorization": "Bearer refresh-token"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token_cache_read_error_returns_503(app_with_netsvcs: Quart) -> None:
    """refresh_server_token() returns 503 when the replay-protection cache read fails."""
    client = app_with_netsvcs.test_client()
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(side_effect=RuntimeError("cache down"))

    with (
        patch(
            "hub_api.auth.jwt.decode_token",
            return_value={
                "token_type": "refresh",
                "sub": "resolver:server-1",
                "tenant": "default",
                "jti": "jti-1",
            },
        ),
        patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as MockSM,
        patch.object(app_with_netsvcs.config, "get") as mock_config_get,
    ):
        mock_mgr = AsyncMock()
        mock_mgr.get_server = AsyncMock(return_value=_server_record())
        MockSM.return_value = mock_mgr

        provider = app_with_netsvcs.config["KEY_PROVIDER"]

        def side_effect(key: str, default: object = None) -> object:
            if key == "KEY_PROVIDER":
                return provider
            if key == "CACHE":
                return mock_cache
            return default

        mock_config_get.side_effect = side_effect

        response = await client.post(
            "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
            headers={"Authorization": "Bearer refresh-token"},
        )

    assert response.status_code == 503
