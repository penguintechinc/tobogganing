"""Tests for WaddlePerf organizational units API endpoints."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from quart import Quart
from typing import Any

from hub_api.modules.perftest_cluster.services.org_unit_manager import OrgUnit


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


# Use canonical fixtures from conftest.py:
# - app_with_wpc: real auth, flags enabled
# - wpc_tenant_token: minimal scopes
# - wpc_write_token: full write access
# - wpc_readonly_token: read-only access


# Aliases for backward compatibility with this test file
@pytest.fixture
def valid_tenant_token(wpc_tenant_token: str) -> str:
    """Alias to canonical wpc_tenant_token fixture.

    Args:
        wpc_tenant_token: Token from canonical fixture.

    Returns:
        JWT token with tenant/read scopes.
    """
    return wpc_tenant_token


@pytest.fixture
def valid_write_token(wpc_write_token: str) -> str:
    """Alias to canonical wpc_write_token fixture.

    Args:
        wpc_write_token: Token from canonical fixture.

    Returns:
        JWT token with full write scopes.
    """
    return wpc_write_token


@pytest.fixture
def read_only_token(wpc_readonly_token: str) -> str:
    """Alias to canonical wpc_readonly_token fixture.

    Args:
        wpc_readonly_token: Token from canonical fixture.

    Returns:
        JWT token with read-only scope.
    """
    return wpc_readonly_token


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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
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
            "/api/v1/perftest_cluster/org-units",
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
        "/api/v1/perftest_cluster/org-units",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
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
            "/api/v1/perftest_cluster/org-units",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
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
            "/api/v1/perftest_cluster/org-units?parent_id=ou-1",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
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
            "/api/v1/perftest_cluster/org-units/ou-1",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_ou = AsyncMock(return_value=None)

        response = await client.get(
            "/api/v1/perftest_cluster/org-units/nonexistent",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
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
            "/api/v1/perftest_cluster/org-units/ou-1",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.update_ou = AsyncMock(return_value=None)

        response = await client.put(
            "/api/v1/perftest_cluster/org-units/nonexistent",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.delete_ou = AsyncMock(return_value=True)

        response = await client.delete(
            "/api/v1/perftest_cluster/org-units/ou-1",
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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.delete_ou = AsyncMock(return_value=False)

        response = await client.delete(
            "/api/v1/perftest_cluster/org-units/nonexistent",
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
        "/api/v1/perftest_cluster/org-units",
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

    response = await client.get("/api/v1/perftest_cluster/org-units")

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
        "hub_api.modules.perftest_cluster.api.org_units.OrgUnitManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        # Simulate list returning empty (OrgUnitManager scopes by tenant)
        mock_mgr.list_ous = AsyncMock(return_value=[])

        response = await client.get(
            "/api/v1/perftest_cluster/org-units",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        # Should succeed but return empty list (tenant-scoped query)
        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["org_units"]) == 0

        # Verify manager was initialized with correct tenant
        mock_manager_class.assert_called_with(mock_manager_class.call_args[0][0], "test-tenant")
