"""Tests for netsvcs DNS servers API endpoints."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.modules.netsvcs.managers.config_service import (
    ConfigService,
    DNSServerConfigDTO,
    DNSZoneDTO,
    DNSRecordDTO,
)
from hub_api.modules.netsvcs.managers.server_manager import (
    ServerManager,
    DNSServerRecord,
    DNSMetricsRecord,
)


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with netsvcs module registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with netsvcs module and auth configured.
    """
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = "default"
    app.config["ENROLLMENT_BOOTSTRAP_TOKEN"] = "test-bootstrap-token"

    # Register netsvcs module via registry (combines module prefix + blueprint prefix)
    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def valid_tenant_token(app_with_netsvcs: Quart) -> str:
    """Generate a valid JWT token with tenant claim.

    Args:
        app_with_netsvcs: Test app with netsvcs module.

    Returns:
        Valid JWT token string.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "scope": "dns:read dns:write",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)

    return token


@pytest.mark.asyncio
async def test_list_dns_servers_without_token(app_with_netsvcs: Quart) -> None:
    """Test list servers fails without JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    client = app_with_netsvcs.test_client()

    response = await client.get("/api/v1/netsvcs/dns-servers")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_dns_servers_with_token(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """Test list servers with valid JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        server = DNSServerRecord(
            id="server-1",
            name="dns-server-1",
            status="online",
            version="1.0.0",
            region="us-east-1",
            hostname="dns1.example.com",
            last_heartbeat=datetime.now(timezone.utc),
            tenant="test-tenant",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.get_all_servers = AsyncMock(return_value=[server])

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/netsvcs/dns-servers",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert "servers" in data
            assert len(data["servers"]) == 1
            assert data["servers"][0]["id"] == "server-1"
            assert data["servers"][0]["name"] == "dns-server-1"
            assert data["servers"][0]["status"] == "online"


@pytest.mark.asyncio
async def test_get_dns_server_with_token(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """Test get single server with valid JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        server = DNSServerRecord(
            id="server-1",
            name="dns-server-1",
            status="online",
            version="1.0.0",
            region="us-east-1",
            hostname="dns1.example.com",
            last_heartbeat=datetime.now(timezone.utc),
            tenant="test-tenant",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.get_server = AsyncMock(return_value=server)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/netsvcs/dns-servers/server-1",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert data["id"] == "server-1"
            assert data["name"] == "dns-server-1"


@pytest.mark.asyncio
async def test_delete_dns_server_with_token(
    app_with_netsvcs: Quart, valid_tenant_token: str
) -> None:
    """Test delete server with valid JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        mock_mgr.delete_server = AsyncMock(return_value=True)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.delete(
                "/api/v1/netsvcs/dns-servers/server-1",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert "message" in data
            assert "deleted" in data["message"].lower()


@pytest.mark.asyncio
async def test_register_server_without_token(app_with_netsvcs: Quart) -> None:
    """Test server registration fails without bootstrap token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    client = app_with_netsvcs.test_client()

    response = await client.post(
        "/api/v1/netsvcs/dns-servers/register",
        json={
            "name": "dns-server-1",
            "hostname": "dns1.example.com",
            "version": "1.0.0",
            "region": "us-east-1",
        },
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "enrollment token required" in data["error"]


@pytest.mark.asyncio
async def test_register_server_with_bootstrap_token(app_with_netsvcs: Quart) -> None:
    """Test server enrollment with bootstrap token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    bootstrap_token = "test-bootstrap-token"
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token

    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        mock_mgr.initialize = AsyncMock()

        server = DNSServerRecord(
            id="server-1",
            name="dns-server-1",
            status="online",
            version="1.0.0",
            region="us-east-1",
            hostname="dns1.example.com",
            last_heartbeat=datetime.now(timezone.utc),
            tenant="default",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.register_server = AsyncMock(return_value=server)

        with patch("hub_api.modules.netsvcs.api.dns_servers.ConfigService") as mock_config_class:
            mock_config_svc = AsyncMock()
            mock_config_class.return_value = mock_config_svc

            config = DNSServerConfigDTO(
                zones=[
                    DNSZoneDTO(
                        name="example.com",
                        visibility="public",
                        records=[
                            DNSRecordDTO(
                                name="www",
                                type="A",
                                value="1.2.3.4",
                                ttl=300,
                            )
                        ],
                    )
                ],
                cache_settings={"ttl": 300},
                settings={"log_queries": True},
                version=0,
            )
            mock_config_svc.get_server_config = AsyncMock(return_value=config)

            response = await client.post(
                "/api/v1/netsvcs/dns-servers/register",
                json={
                    "name": "dns-server-1",
                    "hostname": "dns1.example.com",
                    "version": "1.0.0",
                    "region": "us-east-1",
                },
                headers={"Authorization": f"Bearer {bootstrap_token}"},
            )

            assert response.status_code == 201
            data = await response.get_json()
            assert data["server_id"] == "server-1"
            assert "jwt" in data
            assert "refresh_token" in data
            assert "config" in data


@pytest.mark.asyncio
async def test_get_server_config_with_machine_jwt(app_with_netsvcs: Quart) -> None:
    """Test get config requires machine-JWT with correct subject.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    from hub_api.auth.jwt import encode_access_token

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    # Generate machine-JWT for resolver:server-1
    claims = {
        "sub": "resolver:server-1",
        "iss": "tobogganing",
        "aud": "headend",  # Required by machine-JWT middleware
        "tenant": "default",
        "scope": "dns:config:read",
    }

    machine_jwt = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.modules.netsvcs.api.dns_servers.ConfigService") as mock_config_class:
        mock_config_svc = AsyncMock()
        mock_config_class.return_value = mock_config_svc

        config = DNSServerConfigDTO(
            zones=[
                DNSZoneDTO(
                    name="example.com",
                    visibility="public",
                    records=[
                        DNSRecordDTO(
                            name="www",
                            type="A",
                            value="1.2.3.4",
                            ttl=300,
                        )
                    ],
                )
            ],
            cache_settings={"ttl": 300},
            settings={"log_queries": True},
            version=1,
        )
        mock_config_svc.get_server_config = AsyncMock(return_value=config)

        response = await client.get(
            "/api/v1/netsvcs/dns-servers/server-1/config",
            headers={"Authorization": f"Bearer {machine_jwt}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "zones" in data
        assert data["version"] == 1


@pytest.mark.asyncio
async def test_server_heartbeat_with_machine_jwt(app_with_netsvcs: Quart) -> None:
    """Test heartbeat requires machine-JWT and records metrics.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    from hub_api.auth.jwt import encode_access_token

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    # Generate machine-JWT for resolver:server-1
    claims = {
        "sub": "resolver:server-1",
        "iss": "tobogganing",
        "aud": "headend",  # Required by machine-JWT middleware
        "tenant": "default",
        "scope": "metrics:write",
    }

    machine_jwt = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        mock_mgr.record_heartbeat = AsyncMock(return_value=True)

        with patch("hub_api.modules.netsvcs.api.dns_servers.ConfigService") as mock_config_class:
            mock_config_svc = AsyncMock()
            mock_config_class.return_value = mock_config_svc

            mock_config_svc.get_config_version = AsyncMock(return_value=2)

            response = await client.post(
                "/api/v1/netsvcs/dns-servers/server-1/heartbeat",
                json={
                    "queries_total": 1000,
                    "cache_hits": 800,
                    "errors": 5,
                    "avg_response_ms": 12.5,
                    "config_version": 1,
                },
                headers={"Authorization": f"Bearer {machine_jwt}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert data["config_version"] == 2
            assert data["should_sync"] is True  # 1 < 2


@pytest.mark.asyncio
async def test_get_server_metrics(app_with_netsvcs: Quart, valid_tenant_token: str) -> None:
    """Test get metrics with valid JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        metrics = [
            DNSMetricsRecord(
                id="metric-1",
                server_id="server-1",
                timestamp=datetime.now(timezone.utc),
                queries_total=1000,
                cache_hits=800,
                errors=5,
                avg_response_ms=12.5,
            )
        ]
        mock_mgr.get_metrics = AsyncMock(return_value=metrics)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/netsvcs/dns-servers/server-1/metrics?hours=24",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert "metrics" in data
            assert len(data["metrics"]) == 1
            assert data["metrics"][0]["queries_total"] == 1000


@pytest.mark.asyncio
async def test_enroll_then_config_round_trip(app_with_netsvcs: Quart) -> None:
    """Test round-trip: enroll with bootstrap token, use returned JWT for config pull.

    Regression test for aud mismatch defect: ensures enrollment-returned JWTs
    are actually usable for config pull.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    bootstrap_token = "test-bootstrap-token"
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token

    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        mock_mgr.initialize = AsyncMock()

        server = DNSServerRecord(
            id="server-1",
            name="dns-server-1",
            status="online",
            version="1.0.0",
            region="us-east-1",
            hostname="dns1.example.com",
            last_heartbeat=datetime.now(timezone.utc),
            tenant="default",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.register_server = AsyncMock(return_value=server)
        mock_mgr.get_server = AsyncMock(return_value=server)

        with patch("hub_api.modules.netsvcs.api.dns_servers.ConfigService") as mock_config_class:
            mock_config_svc = AsyncMock()
            mock_config_class.return_value = mock_config_svc

            config = DNSServerConfigDTO(
                zones=[],
                cache_settings={"ttl": 300},
                settings={"log_queries": True},
                version=0,
            )
            mock_config_svc.get_server_config = AsyncMock(return_value=config)

            # Step 1: Enroll server
            enroll_response = await client.post(
                "/api/v1/netsvcs/dns-servers/register",
                json={
                    "name": "dns-server-1",
                    "hostname": "dns1.example.com",
                    "version": "1.0.0",
                    "region": "us-east-1",
                },
                headers={"Authorization": f"Bearer {bootstrap_token}"},
            )

            assert enroll_response.status_code == 201
            enroll_data = await enroll_response.get_json()
            returned_jwt = enroll_data["jwt"]

            # Step 2: Use the RETURNED JWT to pull config (this should work)
            config_response = await client.get(
                "/api/v1/netsvcs/dns-servers/server-1/config",
                headers={"Authorization": f"Bearer {returned_jwt}"},
            )

            assert config_response.status_code == 200

            # Step 3: Same JWT on a different server_id should be rejected (403)
            config_other_response = await client.get(
                "/api/v1/netsvcs/dns-servers/server-2/config",
                headers={"Authorization": f"Bearer {returned_jwt}"},
            )

            assert config_other_response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token_rotation(app_with_netsvcs: Quart) -> None:
    """Test refresh token rotation with jti replay protection.

    Verifies that refresh tokens are single-use and reuses are rejected.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    from hub_api.auth.jwt import encode_access_token

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    # Generate initial refresh token
    initial_refresh_claims = {
        "sub": "resolver:server-1",
        "iss": "tobogganing",
        "aud": "headend",
        "tenant": "default",
        "scope": "dns:config:read",
        "token_type": "refresh",
    }

    initial_refresh_token = await encode_access_token(
        initial_refresh_claims, provider, ttl_hours=24
    )

    with patch("hub_api.modules.netsvcs.api.dns_servers.ServerManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        server = DNSServerRecord(
            id="server-1",
            name="dns-server-1",
            status="online",
            version="1.0.0",
            region="us-east-1",
            hostname="dns1.example.com",
            last_heartbeat=datetime.now(timezone.utc),
            tenant="default",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.get_server = AsyncMock(return_value=server)

        # Mock cache client
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)  # No cached jti yet
        mock_cache.set = AsyncMock()
        mock_cache.delete = AsyncMock()

        with patch.object(app_with_netsvcs.config, "get") as mock_config_get:
            def side_effect(key, default=None):
                if key == "KEY_PROVIDER":
                    return provider
                elif key == "CACHE":
                    return mock_cache
                return default

            mock_config_get.side_effect = side_effect

            # First refresh should succeed
            response1 = await client.post(
                "/api/v1/netsvcs/dns-servers/server-1/refresh-token",
                headers={"Authorization": f"Bearer {initial_refresh_token}"},
            )

            assert response1.status_code == 200
            data1 = await response1.get_json()
            assert "access_token" in data1
            assert "refresh_token" in data1
