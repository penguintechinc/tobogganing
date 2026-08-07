"""Tests for SASE block pages API endpoints (security-critical layer)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.registry import ModuleContext


@pytest.fixture
def app_with_blockpages(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with SASE module and blockpages API registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with SASE module and blockpages blueprint registered.
    """
    # Set up key provider for token generation
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Mock DAL for blockpages manager
    app.config["DAL"] = mock_db

    # Register SASE module
    from hub_api.modules.sase import module as sase_module

    sase_contract = sase_module()
    app.registry.register(sase_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def sase_write_token(app_with_blockpages: Quart) -> str:
    """Generate a valid JWT token with sase:write scope for tenant-a.

    Args:
        app_with_blockpages: App with key provider.

    Returns:
        Encoded JWT token with sase:write scope.
    """
    provider = app_with_blockpages.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "sase:write sase:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def sase_read_token(app_with_blockpages: Quart) -> str:
    """Generate a valid JWT token with sase:read scope only for tenant-a.

    Args:
        app_with_blockpages: App with key provider.

    Returns:
        Encoded JWT token with sase:read scope.
    """
    provider = app_with_blockpages.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "sase:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def sase_write_token_tenant_b(app_with_blockpages: Quart) -> str:
    """Generate a valid JWT token with sase:write scope for tenant-b (cross-tenant test).

    Args:
        app_with_blockpages: App with key provider.

    Returns:
        Encoded JWT token for tenant-b.
    """
    provider = app_with_blockpages.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user-b",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-b",
        "scope": "sase:write sase:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


# ===== Cross-Tenant Regression Tests =====


@pytest.mark.asyncio
async def test_create_page_cross_tenant_body_mismatch(
    app_with_blockpages: Quart, sase_write_token: str
) -> None:
    """Regression: POST /pages with body tenant != JWT tenant → 403.

    regression: cross-tenant
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Attempt to create a page with a mismatched tenant in the body
        response = await client.post(
            "/api/v1/sase/blockpages/pages",
            headers={"Authorization": f"Bearer {sase_write_token}"},
            json={
                "tenant": "tenant-b",  # Mismatch: JWT says tenant-a
                "name": "Malicious Page",
                "markdown": "# Hacked",
            },
        )

        # Must reject with 403, not create under body tenant
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_pages_cross_tenant_isolation(
    app_with_blockpages: Quart,
    sase_read_token: str,
    sase_write_token_tenant_b: str,
) -> None:
    """Regression: page created by tenant-a is NOT visible to tenant-b.

    regression: cross-tenant
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Create a page as tenant-a (mock the manager)
        with patch("hub_api.modules.sase.security.blockpages.api.BlockPageManager") as MockManager:
            mock_manager = AsyncMock()
            MockManager.return_value = mock_manager

            # List pages as tenant-a (should see empty list for test setup)
            response_a = await client.get(
                "/api/v1/sase/blockpages/pages",
                headers={"Authorization": f"Bearer {sase_read_token}"},
            )
            assert response_a.status_code == 200

            # Tenant-b tries to list (should not see tenant-a's pages)
            response_b = await client.get(
                "/api/v1/sase/blockpages/pages",
                headers={"Authorization": f"Bearer {sase_write_token_tenant_b}"},
            )
            assert response_b.status_code == 200

            # Verify manager was called with correct tenants (separate calls)
            calls = mock_manager.list_pages.call_args_list
            assert len(calls) == 2
            assert calls[0][1]["tenant"] == "tenant-a"
            assert calls[1][1]["tenant"] == "tenant-b"


# ===== Flag OFF → 402 Tests =====


@pytest.mark.asyncio
async def test_create_page_flag_off(app_with_blockpages: Quart, sase_write_token: str) -> None:
    """Test POST /pages returns 402 when blockpages flag OFF.

    regression: flag
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False  # Flag OFF

        response = await client.post(
            "/api/v1/sase/blockpages/pages",
            headers={"Authorization": f"Bearer {sase_write_token}"},
            json={
                "name": "Block Page",
                "markdown": "# Blocked",
            },
        )

        # require_feature returns 402 when flag is off
        assert response.status_code == 402


@pytest.mark.asyncio
async def test_list_pages_flag_off(app_with_blockpages: Quart, sase_read_token: str) -> None:
    """Test GET /pages returns 402 when blockpages flag OFF.

    regression: flag
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False  # Flag OFF

        response = await client.get(
            "/api/v1/sase/blockpages/pages",
            headers={"Authorization": f"Bearer {sase_read_token}"},
        )

        assert response.status_code == 402


@pytest.mark.asyncio
async def test_upsert_routes_flag_off(app_with_blockpages: Quart, sase_write_token: str) -> None:
    """Test PUT /routes returns 402 when blockpages flag OFF.

    regression: flag
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False  # Flag OFF

        response = await client.put(
            "/api/v1/sase/blockpages/routes",
            headers={"Authorization": f"Bearer {sase_write_token}"},
            json={"routes": []},
        )

        assert response.status_code == 402


# ===== DTO Field Set Validation =====


@pytest.mark.asyncio
async def test_create_page_dto_fields(app_with_blockpages: Quart, sase_write_token: str) -> None:
    """Test POST /pages returns BlockPageDTO with exact documented field set.

    regression: dto
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        with patch("hub_api.modules.sase.security.blockpages.api.BlockPageManager") as MockManager:
            from hub_api.modules.sase.security.blockpages.models import BlockPage, PageStatus
            from datetime import datetime

            mock_manager = AsyncMock()
            MockManager.return_value = mock_manager

            # Mock the create method to return a BlockPage
            mock_page = BlockPage(
                id="page-123",
                tenant="tenant-a",
                name="Test Page",
                markdown="# Blocked",
                status=PageStatus.draft,
                version=1,
                created_by="test-user",
                updated_by=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            mock_manager.create.return_value = mock_page

            response = await client.post(
                "/api/v1/sase/blockpages/pages",
                headers={"Authorization": f"Bearer {sase_write_token}"},
                json={
                    "name": "Test Page",
                    "markdown": "# Blocked",
                },
            )

            assert response.status_code == 201
            data = await response.get_json()

            # Verify exact DTO field set (no raw model passthrough)
            expected_fields = {
                "id",
                "tenant",
                "name",
                "markdown",
                "status",
                "version",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
            }
            assert set(data.keys()) == expected_fields
            assert data["status"] == "draft"
            assert data["version"] == 1
            assert data["name"] == "Test Page"


@pytest.mark.asyncio
async def test_list_routes_dto_fields(app_with_blockpages: Quart, sase_read_token: str) -> None:
    """Test GET /routes returns BlockRouteDTO with exact documented field set.

    regression: dto
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        with patch("hub_api.modules.sase.security.blockpages.api.BlockRouteManager") as MockManager:
            mock_manager = AsyncMock()
            MockManager.return_value = mock_manager

            # Mock a route response
            from hub_api.modules.sase.security.blockpages.models import RouteDest, BlockRoute
            from datetime import datetime

            mock_route = BlockRoute(
                id="route-123",
                tenant="tenant-a",
                source_type="web-category:gambling",
                destination_kind=RouteDest.page,
                page_id="page-456",
                external_url=None,
                created_at=datetime.utcnow(),
                created_by="user-123",
                updated_by=None,
                ticket=None,
                notes=None,
                expiry=None,
                review_date=None,
                scope=None,
                risk=None,
            )
            mock_manager.get_routes.return_value = [mock_route]

            response = await client.get(
                "/api/v1/sase/blockpages/routes",
                headers={"Authorization": f"Bearer {sase_read_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()

            # Verify routes list and exact DTO field set
            assert "routes" in data
            assert len(data["routes"]) > 0

            route = data["routes"][0]
            expected_fields = {
                "id",
                "tenant",
                "source_type",
                "destination_kind",
                "page_id",
                "external_url",
                "created_at",
                "created_by",
                "updated_by",
                "ticket",
                "notes",
                "expiry",
                "review_date",
                "scope",
                "risk",
            }
            assert set(route.keys()) == expected_fields


# ===== Scope Validation Tests =====


@pytest.mark.asyncio
async def test_create_page_requires_write_scope(
    app_with_blockpages: Quart, sase_read_token: str
) -> None:
    """Test POST /pages requires sase:write scope (read-only token → 403).

    regression: scope
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/sase/blockpages/pages",
            headers={"Authorization": f"Bearer {sase_read_token}"},
            json={
                "name": "Test Page",
                "markdown": "# Blocked",
            },
        )

        # Missing sase:write scope → 403
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_pages_requires_read_scope(
    app_with_blockpages: Quart,
) -> None:
    """Test GET /pages requires sase:read scope (no scopes token → 403).

    regression: scope
    """
    client = app_with_blockpages.test_client()
    provider = app_with_blockpages.config["KEY_PROVIDER"]

    # Create token with no scopes
    claims = {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "",  # No scopes
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get(
            "/api/v1/sase/blockpages/pages",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Missing scopes → 403
        assert response.status_code == 403


# ===== X-Block-* Headers (External Route Contract) =====


@pytest.mark.asyncio
async def test_upsert_external_route_contract(
    app_with_blockpages: Quart, sase_write_token: str
) -> None:
    """Test that external routes can be configured and carry the documented contract.

    regression: contract
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        with patch("hub_api.modules.sase.security.blockpages.api.BlockRouteManager") as MockManager:
            mock_manager = AsyncMock()
            MockManager.return_value = mock_manager

            # Mock external route response
            from hub_api.modules.sase.security.blockpages.models import RouteDest, BlockRoute
            from datetime import datetime

            mock_route = BlockRoute(
                id="route-ext",
                tenant="tenant-a",
                source_type="malware",
                destination_kind=RouteDest.external,
                page_id=None,
                external_url="https://customer.example.com/block",
                created_at=datetime.utcnow(),
                created_by="user-123",
                updated_by=None,
                ticket=None,
                notes=None,
                expiry=None,
                review_date=None,
                scope=None,
                risk=None,
            )
            mock_manager.set_route.return_value = mock_route

            response = await client.put(
                "/api/v1/sase/blockpages/routes",
                headers={"Authorization": f"Bearer {sase_write_token}"},
                json={
                    "routes": [
                        {
                            "source_type": "malware",
                            "destination_kind": "external",
                            "external_url": "https://customer.example.com/block",
                            "metadata": {"created_by": "user-123"},
                        }
                    ]
                },
            )

            assert response.status_code == 200
            data = await response.get_json()

            # Verify external route is returned with correct destination_kind
            assert "routes" in data
            assert len(data["routes"]) > 0
            route = data["routes"][0]
            assert route["destination_kind"] == "external"
            assert route["external_url"] == "https://customer.example.com/block"


# ===== Invalid Input → 400 Tests =====


@pytest.mark.asyncio
async def test_create_page_missing_name_400(app_with_blockpages: Quart, sase_write_token: str) -> None:
    """Test POST /pages returns 400 when name is missing.

    regression: validation
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/sase/blockpages/pages",
            headers={"Authorization": f"Bearer {sase_write_token}"},
            json={
                "markdown": "# Blocked",
                # name is missing
            },
        )

        assert response.status_code == 400
        data = await response.get_json()
        assert "error" in data


@pytest.mark.asyncio
async def test_create_page_missing_markdown_400(
    app_with_blockpages: Quart, sase_write_token: str
) -> None:
    """Test POST /pages returns 400 when markdown is missing.

    regression: validation
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/sase/blockpages/pages",
            headers={"Authorization": f"Bearer {sase_write_token}"},
            json={
                "name": "Test Page",
                # markdown is missing
            },
        )

        assert response.status_code == 400


@pytest.mark.asyncio
async def test_upsert_routes_missing_source_type_400(
    app_with_blockpages: Quart, sase_write_token: str
) -> None:
    """Test PUT /routes returns 400 when source_type is missing.

    regression: validation
    """
    client = app_with_blockpages.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.put(
            "/api/v1/sase/blockpages/routes",
            headers={"Authorization": f"Bearer {sase_write_token}"},
            json={
                "routes": [
                    {
                        # source_type is missing
                        "destination_kind": "page",
                        "page_id": "page-123",
                    }
                ]
            },
        )

        assert response.status_code == 400
