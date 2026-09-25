"""Tests for threatintel blocklist entry management API endpoints (real_dal)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

from hub_api.modules.threatintel.blocklist.entry_manager import BlocklistEntryManager


@pytest.fixture
def app_with_threatintel(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with threatintel module registered (mock_db wiring)."""
    from hub_api.cache.client import CacheClient
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["CACHE"] = CacheClient(
        host="127.0.0.1", port=6399
    )  # Unreachable; in-memory fallback

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
    """Swap in real_dal for get_db everywhere blocklist api.py imports it."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app

    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.threatintel.blocklist.api

    monkeypatch.setattr(hub_api.modules.threatintel.blocklist.api, "get_db", get_db_func)

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
    return await encode_access_token(
        _token_claims("tenant-a", "threatintel:read"), provider, ttl_hours=1
    )


@pytest_asyncio.fixture
async def tenant_a_write_token(app_with_threatintel_realdal: Quart) -> str:
    """JWT for tenant-a with threatintel:read + threatintel:write scopes."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_threatintel_realdal.config["KEY_PROVIDER"]
    return await encode_access_token(
        _token_claims("tenant-a", "threatintel:read threatintel:write"),
        provider,
        ttl_hours=1,
    )


@pytest_asyncio.fixture
async def tenant_b_write_token(app_with_threatintel_realdal: Quart) -> str:
    """JWT for tenant-b with threatintel:read + threatintel:write scopes."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_threatintel_realdal.config["KEY_PROVIDER"]
    return await encode_access_token(
        _token_claims("tenant-b", "threatintel:read threatintel:write"),
        provider,
        ttl_hours=1,
    )


def _flag_on() -> Any:
    """Patch context manager forcing require_feature's flag check ON."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=True)


def _flag_off() -> Any:
    """Patch context manager forcing require_feature's flag check OFF."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=False)


# --- CRUD happy path -------------------------------------------------------


@pytest.mark.asyncio
async def test_list_blocklist_entries_empty(
    app_with_threatintel_realdal: Quart, tenant_a_read_token: str
) -> None:
    """GET /blocklist returns an empty list + meta when no entries exist."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.get(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["entries"] == []
        assert data["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_add_and_list_blocklist_entry(
    app_with_threatintel_realdal: Quart,
    tenant_a_write_token: str,
    tenant_a_read_token: str,
) -> None:
    """POST /blocklist adds an entry; GET /blocklist then lists it."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "domain", "value": "malicious.example.com"},
        )
        assert create_resp.status_code == 201
        created = await create_resp.get_json()
        assert set(created.keys()) == {
            "id",
            "indicator_type",
            "value",
            "source",
            "confidence",
            "active",
            "created_at",
            "updated_at",
        }
        assert created["value"] == "malicious.example.com"
        assert created["source"] == "manual"
        assert created["confidence"] == 100

        list_resp = await client.get(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
        )
        data = await list_resp.get_json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_add_blocklist_entry_invalid_type(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """POST /blocklist rejects an indicator_type outside IOC_TYPES."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "mac_address", "value": "aa:bb:cc:dd:ee:ff"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_add_blocklist_entry_duplicate(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """POST /blocklist rejects a duplicate (value, source) within the same tenant."""
    client = app_with_threatintel_realdal.test_client()
    body = {"indicator_type": "ip", "value": "203.0.113.5"}

    with _flag_on():
        first = await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json=body,
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json=body,
        )
        assert second.status_code == 400


@pytest.mark.asyncio
async def test_remove_blocklist_entry_success(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """DELETE /blocklist/{id} removes an existing entry."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "hash", "value": "a" * 64},
        )
        entry_id = (await create_resp.get_json())["id"]

        delete_resp = await client.delete(
            f"/api/v1/threatintel/blocklist/{entry_id}",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert delete_resp.status_code == 200

        list_resp = await client.get(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert (await list_resp.get_json())["entries"] == []


@pytest.mark.asyncio
async def test_remove_blocklist_entry_not_found(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """DELETE /blocklist/{id} returns 404 for an unknown id."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.delete(
            f"/api/v1/threatintel/blocklist/{uuid4()}",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert response.status_code == 404


# --- Filters + pagination ---------------------------------------------------


@pytest.mark.asyncio
async def test_list_blocklist_entries_filter_by_indicator_type(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """GET /blocklist?indicator_type=ip returns only ip entries."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "ip", "value": "198.51.100.7"},
        )
        await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "domain", "value": "bad.example.com"},
        )

        response = await client.get(
            "/api/v1/threatintel/blocklist?indicator_type=ip",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        data = await response.get_json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["indicator_type"] == "ip"


@pytest.mark.asyncio
async def test_list_blocklist_entries_filter_by_source(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """GET /blocklist?source=manual filters by source."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "ip", "value": "198.51.100.8", "source": "manual"},
        )
        await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "ip", "value": "198.51.100.9", "source": "analyst-review"},
        )

        response = await client.get(
            "/api/v1/threatintel/blocklist?source=analyst-review",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        data = await response.get_json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["source"] == "analyst-review"


@pytest.mark.asyncio
async def test_list_blocklist_entries_pagination(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """GET /blocklist?limit=&offset= paginates results; total reflects full count."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        for i in range(5):
            await client.post(
                "/api/v1/threatintel/blocklist",
                headers={"Authorization": f"Bearer {tenant_a_write_token}"},
                json={"indicator_type": "domain", "value": f"bad-{i}.example.com"},
            )

        page1 = await client.get(
            "/api/v1/threatintel/blocklist?limit=2&offset=0",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        page1_data = await page1.get_json()
        assert len(page1_data["entries"]) == 2
        assert page1_data["meta"]["total"] == 5

        page2 = await client.get(
            "/api/v1/threatintel/blocklist?limit=2&offset=4",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        page2_data = await page2.get_json()
        assert len(page2_data["entries"]) == 1


@pytest.mark.asyncio
async def test_list_blocklist_entries_empty_filter_result(
    app_with_threatintel_realdal: Quart, tenant_a_write_token: str
) -> None:
    """GET /blocklist with a filter matching nothing returns an empty list, not an error."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "domain", "value": "bad.example.com"},
        )

        response = await client.get(
            "/api/v1/threatintel/blocklist?indicator_type=hash",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["entries"] == []


@pytest.mark.asyncio
async def test_list_blocklist_entries_invalid_pagination_params(
    app_with_threatintel_realdal: Quart, tenant_a_read_token: str
) -> None:
    """GET /blocklist with non-integer limit/offset returns 400, not a 500."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.get(
            "/api/v1/threatintel/blocklist?limit=abc",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
        )
        assert response.status_code == 400


# --- Tenant isolation (real_dal, not mocks) -----------------------------


@pytest.mark.asyncio
async def test_blocklist_entry_manager_tenant_isolation(real_dal: AsyncDB) -> None:
    """BlocklistEntryManager: tenant-b cannot see, fetch, or delete tenant-a's entry."""
    manager_a = BlocklistEntryManager(real_dal, "tenant-a")
    manager_b = BlocklistEntryManager(real_dal, "tenant-b")

    entry = await manager_a.add_entry(indicator_type="domain", value="isolated.example.com")
    assert entry is not None

    entries_b, total_b = await manager_b.list_entries()
    assert entries_b == []
    assert total_b == 0

    assert await manager_b.get_entry(entry.id) is None
    assert await manager_b.remove_entry(entry.id) is False

    entries_a, total_a = await manager_a.list_entries()
    assert total_a == 1


@pytest.mark.asyncio
async def test_blocklist_entry_manager_rejects_invalid_indicator_type(
    real_dal: AsyncDB,
) -> None:
    """BlocklistEntryManager.add_entry returns None for a type outside IOC_TYPES."""
    manager = BlocklistEntryManager(real_dal, "tenant-a")

    result = await manager.add_entry(indicator_type="mac_address", value="aa:bb:cc:dd:ee:ff")

    assert result is None


@pytest.mark.asyncio
async def test_blocklist_entry_manager_writethrough_failure_does_not_raise(
    real_dal: AsyncDB,
) -> None:
    """A cache write-through error is swallowed (logged), never raised to the caller.

    Passes a store whose .put() always raises, proving add_entry still
    succeeds (DB insert is the source of truth; cache is best-effort).
    """
    from unittest.mock import AsyncMock

    broken_store = AsyncMock()
    broken_store.put.side_effect = RuntimeError("cache unavailable")

    manager = BlocklistEntryManager(real_dal, "tenant-a", store=broken_store)

    entry = await manager.add_entry(indicator_type="ip", value="8.8.4.4")

    assert entry is not None
    broken_store.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_blocklist_entry_cross_tenant_denied_route(
    app_with_threatintel_realdal: Quart,
    tenant_a_write_token: str,
    tenant_b_write_token: str,
) -> None:
    """DELETE /blocklist/{id} as tenant-b on tenant-a's entry -> 404, entry unaffected."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        create_resp = await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "domain", "value": "tenant-a-only.example.com"},
        )
        entry_id = (await create_resp.get_json())["id"]

        cross_delete = await client.delete(
            f"/api/v1/threatintel/blocklist/{entry_id}",
            headers={"Authorization": f"Bearer {tenant_b_write_token}"},
        )
        assert cross_delete.status_code == 404

        list_resp = await client.get(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
        )
        list_data = await list_resp.get_json()
        assert len(list_data["entries"]) == 1


@pytest.mark.asyncio
async def test_list_blocklist_entries_cross_tenant_isolated_route(
    app_with_threatintel_realdal: Quart,
    tenant_a_write_token: str,
    tenant_b_write_token: str,
) -> None:
    """GET /blocklist as tenant-b never returns tenant-a's entries."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_write_token}"},
            json={"indicator_type": "domain", "value": "a-only.example.com"},
        )

        response = await client.get(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_b_write_token}"},
        )
        data = await response.get_json()
        assert data["entries"] == []


# --- Scope enforcement ---------------------------------------------------


@pytest.mark.asyncio
async def test_list_blocklist_entries_requires_auth(
    app_with_threatintel_realdal: Quart,
) -> None:
    """GET /blocklist without a token -> 403."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.get("/api/v1/threatintel/blocklist")
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_blocklist_entry_requires_write_scope(
    app_with_threatintel_realdal: Quart, tenant_a_read_token: str
) -> None:
    """POST /blocklist with only threatintel:read scope -> 403."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_on():
        response = await client.post(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
            json={"indicator_type": "ip", "value": "203.0.113.9"},
        )
        assert response.status_code == 403


# --- Feature flag gating --------------------------------------------------


@pytest.mark.asyncio
async def test_list_blocklist_entries_flag_off(
    app_with_threatintel_realdal: Quart, tenant_a_read_token: str
) -> None:
    """GET /blocklist returns 402 when the blocklist flag is OFF."""
    client = app_with_threatintel_realdal.test_client()

    with _flag_off():
        response = await client.get(
            "/api/v1/threatintel/blocklist",
            headers={"Authorization": f"Bearer {tenant_a_read_token}"},
        )
        assert response.status_code == 402
