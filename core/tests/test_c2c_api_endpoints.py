"""Tests for C2C endpoints API."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_create_endpoint_success(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test successful endpoint creation."""
    client = app_with_c2c.test_client()
    mock_db = app_with_c2c.db

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        endpoint_dict = {
            "id": "ep-1",
            "tenant": "test-tenant",
            "region": "us-west-2",
            "name": "primary-node",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
            "api_key_hash": "hash123",
            "enabled": True,
            "created_at": "2026-07-10T00:00:00Z",
            "updated_at": "2026-07-10T00:00:00Z",
        }
        mock_mgr.create_endpoint = MagicMock(return_value=(endpoint_dict, "raw-key-123"))

        response = await client.post(
            "/api/v1/waddleperf_c2c/endpoints",
            json={
                "region": "us-west-2",
                "name": "primary-node",
                "engine_url": "http://engine.local:8080",
                "target": "node.example.com",
            },
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == "ep-1"
        assert data["region"] == "us-west-2"
        assert data["api_key"] == "raw-key-123"
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_create_endpoint_missing_fields(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test endpoint creation fails with missing fields."""
    client = app_with_c2c.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary-node",
            # Missing engine_url and target
        },
        headers={"Authorization": f"Bearer {c2c_write_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_create_endpoint_duplicate(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test endpoint creation fails on duplicate."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.create_endpoint = MagicMock(
            side_effect=ValueError("Endpoint with tenant=test-tenant, region=us-west-2, name=primary-node already exists")
        )

        response = await client.post(
            "/api/v1/waddleperf_c2c/endpoints",
            json={
                "region": "us-west-2",
                "name": "primary-node",
                "engine_url": "http://engine.local:8080",
                "target": "node.example.com",
            },
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_endpoints_success(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test listing endpoints."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        endpoints = [
            {
                "id": "ep-1",
                "tenant": "test-tenant",
                "region": "us-west-2",
                "name": "primary",
                "engine_url": "http://engine1.local:8080",
                "target": "node1.example.com",
                "api_key_hash": "hash1",
                "enabled": True,
                "created_at": "2026-07-10T00:00:00Z",
                "updated_at": "2026-07-10T00:00:00Z",
            }
        ]
        mock_mgr.list_endpoints = MagicMock(return_value=endpoints)

        response = await client.get(
            "/api/v1/waddleperf_c2c/endpoints",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["endpoints"]) == 1
        assert data["endpoints"][0]["id"] == "ep-1"


@pytest.mark.asyncio
async def test_list_endpoints_enabled_filter(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test listing endpoints with enabled filter."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.list_endpoints = MagicMock(return_value=[])

        response = await client.get(
            "/api/v1/waddleperf_c2c/endpoints?enabled=true",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        mock_mgr.list_endpoints.assert_called_once_with(enabled_only=True)


@pytest.mark.asyncio
async def test_get_endpoint_success(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting a single endpoint."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        endpoint = {
            "id": "ep-1",
            "tenant": "test-tenant",
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
            "api_key_hash": "hash1",
            "enabled": True,
            "created_at": "2026-07-10T00:00:00Z",
            "updated_at": "2026-07-10T00:00:00Z",
        }
        mock_mgr.get_endpoint = MagicMock(return_value=endpoint)

        response = await client.get(
            "/api/v1/waddleperf_c2c/endpoints/ep-1",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "ep-1"
        assert data["name"] == "primary"


@pytest.mark.asyncio
async def test_get_endpoint_not_found(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting non-existent endpoint."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.get_endpoint = MagicMock(return_value=None)

        response = await client.get(
            "/api/v1/waddleperf_c2c/endpoints/ep-invalid",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_endpoint_success(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test updating an endpoint."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        updated_endpoint = {
            "id": "ep-1",
            "tenant": "test-tenant",
            "region": "us-west-2",
            "name": "primary-updated",
            "engine_url": "http://engine-new.local:8080",
            "target": "node.example.com",
            "api_key_hash": "hash1",
            "enabled": False,
            "created_at": "2026-07-10T00:00:00Z",
            "updated_at": "2026-07-10T01:00:00Z",
        }
        mock_mgr.update_endpoint = MagicMock(return_value=updated_endpoint)

        response = await client.patch(
            "/api/v1/waddleperf_c2c/endpoints/ep-1",
            json={"name": "primary-updated", "enabled": False},
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["name"] == "primary-updated"
        assert data["enabled"] is False


@pytest.mark.asyncio
async def test_update_endpoint_not_found(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test updating non-existent endpoint."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.update_endpoint = MagicMock(return_value=None)

        response = await client.patch(
            "/api/v1/waddleperf_c2c/endpoints/ep-invalid",
            json={"name": "updated"},
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_endpoint_success(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test deleting an endpoint."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.delete_endpoint = MagicMock(return_value=True)

        response = await client.delete(
            "/api/v1/waddleperf_c2c/endpoints/ep-1",
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_endpoint_not_found(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test deleting non-existent endpoint."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.delete_endpoint = MagicMock(return_value=False)

        response = await client.delete(
            "/api/v1/waddleperf_c2c/endpoints/ep-invalid",
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_endpoint_read_only_token_forbidden(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test that read-only token cannot create endpoint."""
    client = app_with_c2c.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_readonly_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_endpoint_no_token_forbidden() -> None:
    """Test that missing token returns 403."""
    # This test uses a minimal app without fixtures since we're testing auth rejection
    from core.app import create_app
    from unittest.mock import MagicMock, patch

    with patch("core.db.init_dal"), patch("core.db.get_db"):
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        # Register c2c module
        from core.modules.waddleperf_c2c import module as c2c_module
        from core.registry import ModuleContext
        from core.crypto import InAppKeyProvider, generate_rsa_key_pair

        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)
        app.config["KEY_PROVIDER"] = provider

        c2c_contract = c2c_module()
        app.registry.register(c2c_contract)

        mock_db = MagicMock()
        ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
        app.registry.apply_to(app, ctx)

        response = await client.get(
            "/api/v1/waddleperf_c2c/endpoints",
        )

        # Should be 403 (missing auth)
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_endpoint_with_api_key(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test creating endpoint with provided API key (no raw key returned)."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        endpoint_dict = {
            "id": "ep-1",
            "tenant": "test-tenant",
            "region": "us-west-2",
            "name": "primary-node",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
            "api_key_hash": "hash123",
            "enabled": True,
            "created_at": "2026-07-10T00:00:00Z",
            "updated_at": "2026-07-10T00:00:00Z",
        }
        # When api_key is provided, return_value is None (not echoed)
        mock_mgr.create_endpoint = MagicMock(return_value=(endpoint_dict, None))

        response = await client.post(
            "/api/v1/waddleperf_c2c/endpoints",
            json={
                "region": "us-west-2",
                "name": "primary-node",
                "engine_url": "http://engine.local:8080",
                "target": "node.example.com",
                "api_key": "my-custom-key",
            },
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == "ep-1"
        # Raw key should NOT be in response
        assert "api_key" not in data


@pytest.mark.asyncio
async def test_update_endpoint_no_fields(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test updating endpoint with no valid fields returns current state."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        endpoint = {
            "id": "ep-1",
            "tenant": "test-tenant",
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
            "api_key_hash": "hash1",
            "enabled": True,
            "created_at": "2026-07-10T00:00:00Z",
            "updated_at": "2026-07-10T00:00:00Z",
        }
        mock_mgr.get_endpoint = MagicMock(return_value=endpoint)
        mock_mgr.update_endpoint = MagicMock(return_value=None)

        response = await client.patch(
            "/api/v1/waddleperf_c2c/endpoints/ep-1",
            json={"invalid_field": "value"},
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "ep-1"


@pytest.mark.asyncio
async def test_create_endpoint_exception(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test handling of unexpected exceptions during endpoint creation."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.create_endpoint = MagicMock(side_effect=Exception("DB error"))

        response = await client.post(
            "/api/v1/waddleperf_c2c/endpoints",
            json={
                "region": "us-west-2",
                "name": "primary",
                "engine_url": "http://engine.local:8080",
                "target": "node.example.com",
            },
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 500
        data = await response.get_json()
        assert "error" in data


@pytest.mark.asyncio
async def test_list_endpoints_exception(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test handling of unexpected exceptions during list endpoints."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.list_endpoints = MagicMock(side_effect=Exception("DB error"))

        response = await client.get(
            "/api/v1/waddleperf_c2c/endpoints",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_endpoint_exception(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test handling of unexpected exceptions during get endpoint."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.get_endpoint = MagicMock(side_effect=Exception("DB error"))

        response = await client.get(
            "/api/v1/waddleperf_c2c/endpoints/ep-1",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 500


@pytest.mark.asyncio
async def test_update_endpoint_exception(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test handling of unexpected exceptions during endpoint update."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.update_endpoint = MagicMock(side_effect=Exception("DB error"))

        response = await client.patch(
            "/api/v1/waddleperf_c2c/endpoints/ep-1",
            json={"name": "updated"},
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 500


@pytest.mark.asyncio
async def test_delete_endpoint_exception(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test handling of unexpected exceptions during endpoint deletion."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.endpoints.EndpointManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.delete_endpoint = MagicMock(side_effect=Exception("DB error"))

        response = await client.delete(
            "/api/v1/waddleperf_c2c/endpoints/ep-1",
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 500
