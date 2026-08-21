"""Tests for threatintel feed source management API endpoints (real_dal)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

from hub_api.modules.threatintel.feeds.source_manager import FeedSourceManager


@pytest.fixture
def app_with_threatintel(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with threatintel module registered (mock_db wiring)."""
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    from hub_api.modules.threatintel import module as threatintel_module

    contract = threatintel_module()
    app.registry.register(contract)

    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def app_with_threatintel_realdal(
    app_with_threatintel: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Swap in real_dal for get_db everywhere feeds/blocklist api.py imports it."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app

    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.threatintel.feeds.api

    monkeypatch.setattr(hub_api.modules.threatintel.feeds.api, "get_db", get_db_func)

    app_with_threatintel.db = real_dal
    return app_with_threatintel


def _token_claims(tenant: str, scope: str) -> dict[str, str]:
    return {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": tenant,
        "scope": scope,
    }


@pytest_asyncio.fixture
async def tenant_a_read_token(app_with_threatintel_realdal: Quart) -> str:
    """JWT for tenant-a with threatintel:read scope."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_threatintel_realdal.config["KEY_PROVIDER"]
    token = await encode_access_token(
        _token_claims("tenant-a", "threatintel:read"), provider, ttl_hours=1
    )
    return token


@pytest_asyncio.fixture
async def tenant_a_write_token(app_with_threatintel_realdal: Quart) -> str:
    """JWT for tenant-a with threatintel:read + threatintel:write scopes."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_threatintel_realdal.config["KEY_PROVIDER"]
    token = await encode_access_token(
        _token_claims("tenant-a", "threatintel:read threatintel:write"),
        provider,
        ttl_hours=1,
    )
    return token


@pytest_asyncio.fixture
async def tenant_b_write_token(app_with_threatintel_realdal: Quart) -> str:
    """JWT for tenant-b with threatintel:read + threatintel:write scopes."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_threatintel_realdal.config["KEY_PROVIDER"]
    token = await encode_access_token(
        _token_claims("tenant-b", "threatintel:read threatintel:write"),
        provider,
        ttl_hours=1,
    )
    return token


def _flag_on() -> Any:
    """Patch context manager forcing require_feature's flag check ON."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=True)


def _flag_off() -> Any:
    """Patch context manager forcing require_feature's flag check OFF."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=False)


# --- CRUD happy path -------------------------------------------------------


@pytest.mark.asyncio
async def test_list_feed_sources_empty(
    app_with_threatintel_realdal: Quart, tenant_a_read_token: str
) -> None:
    """GET /feeds returns an empty list + meta when no sources exist."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.get(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["sources"] == []
        assert set(data["meta"].keys()) == {"version", "timestamp"}


@pytest.mark.asyncio
async def test_create_and_list_feed_source(
    app_with_threatintel_realdal: Quart,
    tenant_a_write_token: str,
    tenant_a_read_token: str,
) -> None:
    """POST /feeds creates a source; GET /feeds then lists it."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={
                "name": "my-misp",
                "source_type": "misp",
                "url": "https://misp.example.com/export.json",
                "enabled": True,
            },
        )
        assert create_resp.status_code == 201
        created = await create_resp.get_json()
        assert set(created.keys()) == {
            "id",
            "name",
            "source_type",
            "url",
            "enabled",
            "last_refresh_at",
            "last_refresh_status",
            "last_refresh_error",
            "created_at",
        }
        assert created["name"] == "my-misp"
        assert created["source_type"] == "misp"
        assert created["last_refresh_at"] is None

        list_resp = await client.get(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
        )
        assert list_resp.status_code == 200
        data = await list_resp.get_json()
        assert len(data["sources"]) == 1
        assert data["sources"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_create_feed_source_invalid_type(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """POST /feeds rejects an unsupported source_type."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"name": "bad", "source_type": "carbonblack", "url": "https://x.example/feed"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_feed_source_invalid_url(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """POST /feeds rejects a non-http(s) URL."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"name": "bad-url", "source_type": "csv", "url": "ftp://x.example/feed.csv"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_feed_source_duplicate_name(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """POST /feeds rejects a duplicate name within the same tenant."""
    client = app_with_threatintel_realdal.test_client()
    body = {"name": "dup-source", "source_type": "csv", "url": "https://x.example/feed.csv"}

    with _flag_on():
        first = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json=body,
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json=body,
        )
        assert second.status_code == 400


@pytest.mark.asyncio
async def test_delete_feed_source_success(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """DELETE /feeds/{id} removes an existing source."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"name": "to-delete", "source_type": "stix", "url": "https://x.example/stix.json"},
        )
        source_id = (await create_resp.get_json())["id"]

        delete_resp = await client.delete(
            f"/api/v1/threatintel/feeds/{source_id}",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert delete_resp.status_code == 200

        list_resp = await client.get(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert (await list_resp.get_json())["sources"] == []


@pytest.mark.asyncio
async def test_delete_feed_source_not_found(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """DELETE /feeds/{id} returns 404 for an unknown id."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.delete(
            f"/api/v1/threatintel/feeds/{uuid4()}",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert response.status_code == 404


# --- Refresh -----------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_feed_source_success(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str, real_dal: AsyncDB
) -> None:
    """POST /feeds/{id}/refresh ingests and records last_refresh_status=completed."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"name": "refresh-me", "source_type": "csv", "url": "https://x.example/feed.csv"},
        )
        source_id = (await create_resp.get_json())["id"]

        with patch(
            "hub_api.modules.threatintel.feeds.api.ingest_feed_source",
            new=AsyncMock(return_value={"added": 3, "updated": 1, "errors": 0}),
        ):
            refresh_resp = await client.post(
                f"/api/v1/threatintel/feeds/{source_id}/refresh",
                headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            )

        assert refresh_resp.status_code == 200
        data = await refresh_resp.get_json()
        assert data["status"] == "completed"
        assert data["added"] == 3
        assert data["updated"] == 1
        assert data["errors"] == 0

        manager = FeedSourceManager(real_dal, "tenant-a")
        record = await manager.get_source(source_id)
        assert record.last_refresh_status == "completed"
        assert record.last_refresh_at is not None


@pytest.mark.asyncio
async def test_refresh_feed_source_failure_recorded(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str, real_dal: AsyncDB
) -> None:
    """POST /feeds/{id}/refresh records failure without 500ing the caller."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={
                "name": "flaky-feed",
                "source_type": "misp",
                "url": "https://x.example/feed.json",
            },
        )
        source_id = (await create_resp.get_json())["id"]

        with patch(
            "hub_api.modules.threatintel.feeds.api.ingest_feed_source",
            new=AsyncMock(side_effect=RuntimeError("HTTP 503 from feed source")),
        ):
            refresh_resp = await client.post(
                f"/api/v1/threatintel/feeds/{source_id}/refresh",
                headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            )

        assert refresh_resp.status_code == 200
        data = await refresh_resp.get_json()
        assert data["status"] == "failed"
        assert data["errors"] == 1

        manager = FeedSourceManager(real_dal, "tenant-a")
        record = await manager.get_source(source_id)
        assert record.last_refresh_status == "failed"
        assert "503" in (record.last_refresh_error or "")


@pytest.mark.asyncio
async def test_refresh_feed_source_not_found(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """POST /feeds/{id}/refresh returns 404 for an unknown id."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.post(
            f"/api/v1/threatintel/feeds/{uuid4()}/refresh",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert response.status_code == 404


# --- Tenant isolation (real_dal, not mocks) -----------------------------


@pytest.mark.asyncio
async def test_feed_source_manager_tenant_isolation(real_dal: AsyncDB) -> None:
    """FeedSourceManager: tenant-b cannot see or delete tenant-a's source."""
    manager_a = FeedSourceManager(real_dal, "tenant-a")
    manager_b = FeedSourceManager(real_dal, "tenant-b")

    created = await manager_a.create_source(
        name="isolated-source", source_type="taxii", url="https://x.example/taxii"
    )
    assert created is not None

    # tenant-b sees nothing
    sources_b = await manager_b.list_sources()
    assert sources_b == []

    # tenant-b cannot fetch it directly
    assert await manager_b.get_source(created.id) is None

    # tenant-b cannot delete it
    assert await manager_b.delete_source(created.id) is False

    # tenant-a still has it
    sources_a = await manager_a.list_sources()
    assert len(sources_a) == 1


@pytest.mark.asyncio
async def test_feed_source_manager_rejects_invalid_source_type(real_dal: AsyncDB) -> None:
    """FeedSourceManager.create_source returns None for an unsupported source_type."""
    manager = FeedSourceManager(real_dal, "tenant-a")

    result = await manager.create_source(
        name="bad-type", source_type="openioc", url="https://x.example/feed"
    )

    assert result is None


@pytest.mark.asyncio
async def test_delete_feed_source_cross_tenant_denied_route(
    app_with_threatintel_realdal: Quart,
    tenant_a_write_token: str,
    tenant_b_write_token: str,
) -> None:
    """DELETE /feeds/{id} as tenant-b on tenant-a's source route -> 404 (not found from tenant-b's view)."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={
                "name": "tenant-a-only",
                "source_type": "csv",
                "url": "https://x.example/feed.csv",
            },
        )
        source_id = (await create_resp.get_json())["id"]

        cross_delete = await client.delete(
            f"/api/v1/threatintel/feeds/{source_id}",
            headers={"Authorization": f"Bearer {tenant_b_write_token}"},
        )
        assert cross_delete.status_code == 404

        # Still present for tenant-a
        list_resp = await client.get(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        list_data = await list_resp.get_json()
        assert len(list_data["sources"]) == 1


# --- Scope enforcement ---------------------------------------------------


@pytest.mark.asyncio
async def test_list_feed_sources_requires_auth(app_with_threatintel_realdal: Quart) -> None:
    """GET /feeds without a token -> 403."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.get("/api/v1/threatintel/feeds")
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_feed_source_requires_write_scope(
    app_with_threatintel_realdal: Quart, tenant_a_read_token: str
) -> None:
    """POST /feeds with only threatintel:read scope -> 403."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.post(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
            json={"name": "no-write", "source_type": "csv", "url": "https://x.example/feed.csv"},
        )
        assert response.status_code == 403


# --- Feature flag gating --------------------------------------------------


@pytest.mark.asyncio
async def test_list_feed_sources_flag_off(
    app_with_threatintel_realdal: Quart, tenant_a_read_token: str
) -> None:
    """GET /feeds returns 402 when the feeds flag is OFF."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_off():
        response = await client.get(
            "/api/v1/threatintel/feeds",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
        )
        assert response.status_code == 402
