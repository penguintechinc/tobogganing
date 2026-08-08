"""Tests for netsvcs DNS zones API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.modules.netsvcs.managers.zone_manager import (
    ZoneManager,
    DNSZoneRecord,
    DNSRecordRecord,
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

    # Register netsvcs module via registry
    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def tenant_a_token(app_with_netsvcs: Quart) -> str:
    """Generate JWT token for tenant A.

    Args:
        app_with_netsvcs: Test app with netsvcs module.

    Returns:
        Valid JWT token for tenant A.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "user-a",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "dns:read dns:write",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def tenant_b_token(app_with_netsvcs: Quart) -> str:
    """Generate JWT token for tenant B.

    Args:
        app_with_netsvcs: Test app with netsvcs module.

    Returns:
        Valid JWT token for tenant B.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "user-b",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-b",
        "scope": "dns:read dns:write",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_list_zones_without_token(app_with_netsvcs: Quart) -> None:
    """Test list zones fails without JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    client = app_with_netsvcs.test_client()

    response = await client.get("/api/v1/netsvcs/zones")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_zones_with_token(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test list zones returns tenant-scoped results.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        zone = DNSZoneRecord(
            id="zone-1",
            name="example.com",
            visibility="public",
            description="Example zone",
            tenant="tenant-a",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.list_zones = AsyncMock(return_value=[zone])

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/netsvcs/zones",
                headers={"Authorization": f"Bearer {tenant_a_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert "zones" in data
            assert len(data["zones"]) == 1
            assert data["zones"][0]["name"] == "example.com"


@pytest.mark.asyncio
async def test_create_zone_with_token(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test create zone returns successfully with proper version bump.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as mock_zone_manager, \
         patch("hub_api.modules.netsvcs.api.zones.ConfigService") as mock_config_service:
        mock_mgr = AsyncMock()
        mock_zone_manager.return_value = mock_mgr

        zone = DNSZoneRecord(
            id="zone-new",
            name="newzone.com",
            visibility="public",
            description=None,
            tenant="tenant-a",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.create_zone = AsyncMock(return_value=zone)

        mock_config = AsyncMock()
        mock_config_service.return_value = mock_config
        mock_config.bump_version = AsyncMock(return_value=1)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.post(
                "/api/v1/netsvcs/zones",
                headers={"Authorization": f"Bearer {tenant_a_token}"},
                json={"name": "newzone.com", "visibility": "public"},
            )

            assert response.status_code == 201
            data = await response.get_json()
            assert data["id"] == "zone-new"
            assert data["name"] == "newzone.com"
            # Verify bump_version was called
            mock_config.bump_version.assert_called_once()


@pytest.mark.asyncio
async def test_tenant_isolation_cross_zone_access(
    app_with_netsvcs: Quart,
    tenant_a_token: str,
    tenant_b_token: str,
) -> None:
    """Test tenant A cannot access tenant B's zone (404).

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Token for tenant A.
        tenant_b_token: Token for tenant B.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        # Tenant A tries to access tenant B's zone: returns None (not found)
        mock_mgr.get_zone = AsyncMock(return_value=None)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            # Tenant A tries to get tenant B's zone
            response = await client.get(
                "/api/v1/netsvcs/zones/zone-b-1",
                headers={"Authorization": f"Bearer {tenant_a_token}"},
            )

            # Should return 404 (zone not in tenant A)
            assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_zone_name_rejected(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test creating zone with duplicate name in same tenant is rejected.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        # Simulate duplicate name: returns None
        mock_mgr.create_zone = AsyncMock(return_value=None)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.post(
                "/api/v1/netsvcs/zones",
                headers={"Authorization": f"Bearer {tenant_a_token}"},
                json={"name": "duplicate.com", "visibility": "public"},
            )

            # Should return 400
            assert response.status_code == 400
            data = await response.get_json()
            assert "already exists" in data["error"]


@pytest.mark.asyncio
async def test_list_records_for_zone(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test list records returns zone's records.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        zone = DNSZoneRecord(
            id="zone-1",
            name="example.com",
            visibility="public",
            description=None,
            tenant="tenant-a",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.get_zone = AsyncMock(return_value=zone)

        record = DNSRecordRecord(
            id="record-1",
            zone_id="zone-1",
            name="www",
            type="A",
            value="192.168.1.1",
            ttl=300,
            priority=None,
            weight=None,
            port=None,
            tenant="tenant-a",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.list_records = AsyncMock(return_value=[record])

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/netsvcs/zones/zone-1/records",
                headers={"Authorization": f"Bearer {tenant_a_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert "records" in data
            assert len(data["records"]) == 1
            assert data["records"][0]["name"] == "www"
            assert data["records"][0]["type"] == "A"


@pytest.mark.asyncio
async def test_create_record_bumps_version(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test creating a record bumps config version.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as mock_zone_manager, \
         patch("hub_api.modules.netsvcs.api.zones.ConfigService") as mock_config_service:
        mock_mgr = AsyncMock()
        mock_zone_manager.return_value = mock_mgr

        zone = DNSZoneRecord(
            id="zone-1",
            name="example.com",
            visibility="public",
            description=None,
            tenant="tenant-a",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.get_zone = AsyncMock(return_value=zone)

        record = DNSRecordRecord(
            id="record-new",
            zone_id="zone-1",
            name="api",
            type="A",
            value="10.0.0.1",
            ttl=600,
            priority=None,
            weight=None,
            port=None,
            tenant="tenant-a",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.create_record = AsyncMock(return_value=record)

        mock_config = AsyncMock()
        mock_config_service.return_value = mock_config
        mock_config.bump_version = AsyncMock(return_value=2)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.post(
                "/api/v1/netsvcs/zones/zone-1/records",
                headers={"Authorization": f"Bearer {tenant_a_token}"},
                json={
                    "name": "api",
                    "type": "A",
                    "value": "10.0.0.1",
                    "ttl": 600,
                },
            )

            assert response.status_code == 201
            # Verify bump_version was called
            mock_config.bump_version.assert_called_once()


@pytest.mark.asyncio
async def test_delete_zone_bumps_version(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test deleting a zone bumps config version.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as mock_zone_manager, \
         patch("hub_api.modules.netsvcs.api.zones.ConfigService") as mock_config_service:
        mock_mgr = AsyncMock()
        mock_zone_manager.return_value = mock_mgr

        # Zone deletion returns True
        mock_mgr.delete_zone = AsyncMock(return_value=True)

        mock_config = AsyncMock()
        mock_config_service.return_value = mock_config
        mock_config.bump_version = AsyncMock(return_value=3)

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.delete(
                "/api/v1/netsvcs/zones/zone-1",
                headers={"Authorization": f"Bearer {tenant_a_token}"},
            )

            assert response.status_code == 200
            # Verify bump_version was called
            mock_config.bump_version.assert_called_once()
