"""Tests for WaddlePerf organizational units API endpoints."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from quart import Quart
from typing import Any

from core.modules.waddleperf_cluster.services.org_unit_manager import OrgUnit


def make_mock_ou(
    ou_id: str = "test-ou-1",
    name: str = "Test OU",
    tenant: str = "test-tenant",
    parent_id: str | None = None,
    description: str | None = None,
    is_active: bool = True,
) -> MagicMock:
    """Create a mock OU row object."""
    row = MagicMock()
    row.id = ou_id
    row.name = name
    row.tenant = tenant
    row.parent_id = parent_id
    row.description = description
    row.is_active = is_active
    row.created_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    row.as_dict.return_value = {
        "id": ou_id,
        "name": name,
        "tenant": tenant,
        "parent_id": parent_id,
        "description": description,
        "is_active": is_active,
    }
    return row


@pytest.fixture(autouse=True)
def enable_org_units_feature(monkeypatch: Any) -> None:
    """Enable org_units feature flag for all tests.

    Args:
        monkeypatch: pytest monkeypatch fixture.
    """
    from core.entitlements import gate
    monkeypatch.setattr(gate, "feature_enabled", lambda *args, **kwargs: True)


@pytest.fixture
def app_with_wpc(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with WaddlePerf cluster module registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with WaddlePerf cluster module and auth configured.
    """
    from core.auth.jwt import encode_access_token
    from core.crypto import InAppKeyProvider, generate_rsa_key_pair
    from core.registry import ModuleContext

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Register WaddlePerf cluster module via registry
    from core.modules.waddleperf_cluster import module as wpc_module

    wpc_contract = wpc_module()
    app.registry.register(wpc_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest.fixture
def valid_tenant_token(app_with_wpc: Quart) -> str:
    """Generate a valid tenant JWT token with org_units:read scope.

    Args:
        app_with_wpc: App with key provider.

    Returns:
        Encoded JWT token with tenant claim.
    """
    from core.auth.jwt import encode_access_token

    provider = app_with_wpc.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "org_units:read org_units:write",
    }

    token = encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.fixture
def valid_write_token(app_with_wpc: Quart) -> str:
    """Generate a valid JWT token with write scopes.

    Args:
        app_with_wpc: App with key provider.

    Returns:
        Encoded JWT token with write scopes.
    """
    from core.auth.jwt import encode_access_token

    provider = app_with_wpc.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }

    token = encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.fixture
def read_only_token(app_with_wpc: Quart) -> str:
    """Generate a JWT token with read-only scope.

    Args:
        app_with_wpc: App with key provider.

    Returns:
        Encoded JWT token with read-only scope.
    """
    from core.auth.jwt import encode_access_token

    provider = app_with_wpc.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "org_units:read",
    }

    token = encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_create_org_unit_success(
    app_with_wpc: Quart, valid_write_token: str
) -> None:
    """Test successful organizational unit creation.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()
    mock_db = app_with_wpc.db

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        ou = OrgUnit(
            id="ou-1",
            tenant="test-tenant",
            name="Engineering",
            parent_id=None,
            description="Engineering department",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.create_ou = AsyncMock(return_value=ou)

        response = await client.post(
            "/api/v1/waddleperf_cluster/org-units",
            json={
                "name": "Engineering",
                "description": "Engineering department",
            },
            headers={"Authorization": f"Bearer {valid_write_token}"},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == "ou-1"
        assert data["name"] == "Engineering"
        assert data["tenant"] == "test-tenant"
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_create_org_unit_missing_name(
    app_with_wpc: Quart, valid_write_token: str
) -> None:
    """Test organizational unit creation fails without name.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    response = await client.post(
        "/api/v1/waddleperf_cluster/org-units",
        json={"description": "No name provided"},
        headers={"Authorization": f"Bearer {valid_write_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Missing required field: name" in data["error"]


@pytest.mark.asyncio
async def test_list_org_units_success(
    app_with_wpc: Quart, valid_tenant_token: str
) -> None:
    """Test successful organizational units listing.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_tenant_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        ous = [
            OrgUnit(
                id="ou-1",
                tenant="test-tenant",
                name="Engineering",
                parent_id=None,
                description="Engineering department",
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            OrgUnit(
                id="ou-2",
                tenant="test-tenant",
                name="Sales",
                parent_id=None,
                description="Sales department",
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]
        mock_mgr.list_ous = AsyncMock(return_value=ous)

        response = await client.get(
            "/api/v1/waddleperf_cluster/org-units",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["org_units"]) == 2
        assert data["org_units"][0]["name"] == "Engineering"
        assert data["org_units"][1]["name"] == "Sales"
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_list_org_units_with_parent_filter(
    app_with_wpc: Quart, valid_tenant_token: str
) -> None:
    """Test listing org units filtered by parent_id (hierarchy).

    Args:
        app_with_wpc: Test app with WPC module.
        valid_tenant_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        ous = [
            OrgUnit(
                id="ou-1-1",
                tenant="test-tenant",
                name="Backend Team",
                parent_id="ou-1",
                description="Backend engineering",
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]
        mock_mgr.list_ous = AsyncMock(return_value=ous)

        response = await client.get(
            "/api/v1/waddleperf_cluster/org-units?parent_id=ou-1",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["org_units"]) == 1
        assert data["org_units"][0]["parent_id"] == "ou-1"
        assert data["org_units"][0]["name"] == "Backend Team"


@pytest.mark.asyncio
async def test_get_org_unit_success(
    app_with_wpc: Quart, valid_tenant_token: str
) -> None:
    """Test getting organizational unit details.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_tenant_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        ou = OrgUnit(
            id="ou-1",
            tenant="test-tenant",
            name="Engineering",
            parent_id=None,
            description="Engineering department",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.get_ou = AsyncMock(return_value=ou)

        response = await client.get(
            "/api/v1/waddleperf_cluster/org-units/ou-1",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "ou-1"
        assert data["name"] == "Engineering"


@pytest.mark.asyncio
async def test_get_org_unit_not_found(
    app_with_wpc: Quart, valid_tenant_token: str
) -> None:
    """Test getting non-existent organizational unit returns 404.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_tenant_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_ou = AsyncMock(return_value=None)

        response = await client.get(
            "/api/v1/waddleperf_cluster/org-units/nonexistent",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 404
        data = await response.get_json()
        assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_update_org_unit_success(
    app_with_wpc: Quart, valid_write_token: str
) -> None:
    """Test successful organizational unit update.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        ou = OrgUnit(
            id="ou-1",
            tenant="test-tenant",
            name="Engineering Updated",
            parent_id=None,
            description="Updated description",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_mgr.update_ou = AsyncMock(return_value=ou)

        response = await client.put(
            "/api/v1/waddleperf_cluster/org-units/ou-1",
            json={"name": "Engineering Updated", "description": "Updated description"},
            headers={"Authorization": f"Bearer {valid_write_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "ou-1"
        assert data["name"] == "Engineering Updated"


@pytest.mark.asyncio
async def test_update_org_unit_not_found(
    app_with_wpc: Quart, valid_write_token: str
) -> None:
    """Test updating non-existent organizational unit returns 404.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.update_ou = AsyncMock(return_value=None)

        response = await client.put(
            "/api/v1/waddleperf_cluster/org-units/nonexistent",
            json={"name": "Updated"},
            headers={"Authorization": f"Bearer {valid_write_token}"},
        )

        assert response.status_code == 404
        data = await response.get_json()
        assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_delete_org_unit_success(
    app_with_wpc: Quart, valid_write_token: str
) -> None:
    """Test successful organizational unit deletion.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.delete_ou = AsyncMock(return_value=True)

        response = await client.delete(
            "/api/v1/waddleperf_cluster/org-units/ou-1",
            headers={"Authorization": f"Bearer {valid_write_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "deleted" in data["message"]
        assert "meta" in data


@pytest.mark.asyncio
async def test_delete_org_unit_not_found(
    app_with_wpc: Quart, valid_write_token: str
) -> None:
    """Test deleting non-existent organizational unit returns 404.

    Args:
        app_with_wpc: Test app with WPC module.
        valid_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.delete_ou = AsyncMock(return_value=False)

        response = await client.delete(
            "/api/v1/waddleperf_cluster/org-units/nonexistent",
            headers={"Authorization": f"Bearer {valid_write_token}"},
        )

        assert response.status_code == 404
        data = await response.get_json()
        assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_read_only_token_cannot_write(
    app_with_wpc: Quart, read_only_token: str
) -> None:
    """Test that read-only token cannot create OU.

    Args:
        app_with_wpc: Test app with WPC module.
        read_only_token: JWT token with read-only scope.
    """
    client = app_with_wpc.test_client()

    response = await client.post(
        "/api/v1/waddleperf_cluster/org-units",
        json={"name": "Test OU"},
        headers={"Authorization": f"Bearer {read_only_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_auth_token_returns_403(app_with_wpc: Quart) -> None:
    """Test that requests without auth token return 403.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    response = await client.get("/api/v1/waddleperf_cluster/org-units")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tenant_isolation_read(
    app_with_wpc: Quart, valid_tenant_token: str
) -> None:
    """Test that tenant A cannot read org units from tenant B (isolation).

    Args:
        app_with_wpc: Test app with WPC module.
        valid_tenant_token: JWT token for test-tenant.
    """
    client = app_with_wpc.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        # Simulate list returning empty (OrgUnitManager scopes by tenant)
        mock_mgr.list_ous = AsyncMock(return_value=[])

        response = await client.get(
            "/api/v1/waddleperf_cluster/org-units",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        # Should succeed but return empty list (tenant-scoped query)
        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["org_units"]) == 0

        # Verify manager was initialized with correct tenant
        mock_manager_class.assert_called_with(mock_manager_class.call_args[0][0], "test-tenant")
