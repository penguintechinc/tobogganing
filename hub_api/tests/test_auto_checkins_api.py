"""Test AutoCheckIn REST API: flag/license gating, CRUD, tier validation."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB


@pytest_asyncio.fixture
async def auto_checkins_app(real_dal: AsyncDB, monkeypatch: pytest.MonkeyPatch):
    """Quart app with perftest_cluster mounted on a real DAL; flags off by default."""
    import hub_api.app as app_module
    import hub_api.db
    import shared.licensing.entitlements
    from hub_api.app import create_app
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    test_app = create_app()
    test_app.config["TESTING"] = True

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    test_app.config["KEY_PROVIDER"] = provider
    # Matches the "iss"/"aud" used by this file's token fixtures, so
    # _validate_and_store_token's aud/iss enforcement accepts them.
    test_app.config["PRODUCT_NAME"] = "test-app"

    monkeypatch.setattr(hub_api.db, "get_db", lambda: real_dal)
    monkeypatch.setattr(app_module, "get_db", lambda: real_dal)
    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    monkeypatch.setattr(auto_checkins_api, "get_db", lambda: real_dal)

    enabled_flags: set[str] = set()

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        return flag_key in enabled_flags

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    from hub_api.modules.perftest_cluster import module as wpc_module

    test_app.registry.register(wpc_module())
    ctx = ModuleContext(config=test_app.config_obj, db=real_dal, key_provider=provider)
    test_app.registry.apply_to(test_app, ctx)

    test_app._test_enabled_flags = enabled_flags  # type: ignore[attr-defined]
    return test_app


async def _token(app) -> str:
    from hub_api.auth.jwt import encode_access_token

    return await encode_access_token(
        {
            "sub": "checkin-tester",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant-checkin",
            "scope": "*:*",
        },
        app.config["KEY_PROVIDER"],
    )


@pytest.mark.asyncio
async def test_create_flag_off_returns_402(auto_checkins_app) -> None:
    """With the flag off, create must 402 before touching the DB."""
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_create_unlicensed_402_professional(auto_checkins_app) -> None:
    """Entitlement-key trap: flag ON but license unset -> 402 professional."""
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402
    body = await resp.get_json()
    assert body["tier"] == "professional"


@pytest.mark.asyncio
async def test_licensed_crud_roundtrip(auto_checkins_app, monkeypatch: pytest.MonkeyPatch) -> None:
    """Licensed Professional tier: create, list, get, patch, delete over HTTP."""
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "wifi-baseline",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
            "interval_minutes": 5,
            "jitter_pct": 10,
            "samples_per_run": 2,
            "threshold_stddev_max": 50.0,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    created = await resp.get_json()
    assert created["name"] == "wifi-baseline"
    assert created["test_types"] == ["http_trace", "traceroute", "udp", "http2"]  # tier-1 default
    checkin_id = created["id"]

    resp = await client.get("/api/v1/perftest_cluster/auto-checkins", headers=headers)
    assert resp.status_code == 200
    listed = await resp.get_json()
    assert len(listed["checkins"]) == 1

    resp = await client.get(f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", headers=headers)
    assert resp.status_code == 200

    resp = await client.get(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}/state", headers=headers
    )
    assert resp.status_code == 200
    state = await resp.get_json()
    assert state["last_breached"] is False

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}",
        json={"interval_minutes": 15},
        headers=headers,
    )
    assert resp.status_code == 200
    assert (await resp.get_json())["interval_minutes"] == 15

    resp = await client.delete(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", headers=headers
    )
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_missing_required_fields_400(auto_checkins_app, monkeypatch) -> None:
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={"name": "incomplete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_tier2_without_parent_400(auto_checkins_app, monkeypatch) -> None:
    """Manager ValueError (missing parent_checkin_id) surfaces as 400."""
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "orphan-tier2",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
            "tier": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_with_dependents_409(auto_checkins_app, monkeypatch) -> None:
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    device_id = str(uuid4())

    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "parent",
            "device_id": device_id,
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    parent_id = (await resp.get_json())["id"]

    await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "child",
            "device_id": device_id,
            "target_kind": "external",
            "target": "example.com",
            "tier": 2,
            "parent_checkin_id": parent_id,
            "test_types": ["throughput"],
        },
        headers=headers,
    )

    resp = await client.delete(
        f"/api/v1/perftest_cluster/auto-checkins/{parent_id}", headers=headers
    )
    assert resp.status_code == 409


async def _licensed_client(auto_checkins_app, monkeypatch: pytest.MonkeyPatch):
    """Flip the flag on + license true, mint a token, return (client, headers)."""
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    return client, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_empty_body_400(auto_checkins_app, monkeypatch) -> None:
    """An empty JSON object body is falsy -> 400 before field validation."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post("/api/v1/perftest_cluster/auto-checkins", json={}, headers=headers)
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "Request body is required" in body["error"]


@pytest.mark.asyncio
async def test_create_field_not_string_400(auto_checkins_app, monkeypatch) -> None:
    """A required field present but non-string -> 400 (isinstance check)."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": 123,
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "must be a non-empty string" in body["error"]


@pytest.mark.asyncio
async def test_create_tier_not_int_400(auto_checkins_app, monkeypatch) -> None:
    """tier present but non-int -> 400."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
            "tier": "two",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "tier must be an integer" in body["error"]


@pytest.mark.asyncio
async def test_create_test_types_not_list_400(auto_checkins_app, monkeypatch) -> None:
    """test_types present but not a list -> 400."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
            "test_types": "not-a-list",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "test_types must be a list of strings" in body["error"]


@pytest.mark.asyncio
async def test_create_unexpected_exception_500(auto_checkins_app, monkeypatch) -> None:
    """A non-ValueError raised by the manager surfaces as 500, not a traceback."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    async def _boom(self, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(auto_checkins_api.AutoCheckInManager, "create_checkin", _boom)

    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    assert resp.status_code == 500
    body = await resp.get_json()
    assert body["error"] == "Internal server error"


@pytest.mark.asyncio
async def test_list_unexpected_exception_500(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    async def _boom(self, tenant):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(auto_checkins_api.AutoCheckInManager, "list_checkins", _boom)

    resp = await client.get("/api/v1/perftest_cluster/auto-checkins", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_unexpected_exception_500(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    async def _boom(self, tenant, checkin_id):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(auto_checkins_api.AutoCheckInManager, "get_checkin", _boom)

    resp = await client.get(f"/api/v1/perftest_cluster/auto-checkins/{uuid4()}", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_state_not_found_404(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.get(
        f"/api/v1/perftest_cluster/auto-checkins/{uuid4()}/state", headers=headers
    )
    assert resp.status_code == 404
    body = await resp.get_json()
    assert body["error"] == "State not found"


@pytest.mark.asyncio
async def test_get_state_unexpected_exception_500(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    async def _boom(self, tenant, checkin_id):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(auto_checkins_api.AutoCheckInManager, "get_state", _boom)

    resp = await client.get(
        f"/api/v1/perftest_cluster/auto-checkins/{uuid4()}/state", headers=headers
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_update_empty_body_400(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    checkin_id = (await resp.get_json())["id"]

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", json={}, headers=headers
    )
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "Request body is required" in body["error"]


@pytest.mark.asyncio
async def test_update_test_types_not_list_400(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    checkin_id = (await resp.get_json())["id"]

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}",
        json={"test_types": "not-a-list"},
        headers=headers,
    )
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "test_types must be a list of strings" in body["error"]


@pytest.mark.asyncio
async def test_update_test_types_unsupported_400(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    checkin_id = (await resp.get_json())["id"]

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}",
        json={"test_types": ["not_a_real_type"]},
        headers=headers,
    )
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "Unsupported test_types" in body["error"]


@pytest.mark.asyncio
async def test_update_not_found_404(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{uuid4()}",
        json={"name": "ghost"},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_returns_none_after_existing_found_404(auto_checkins_app, monkeypatch) -> None:
    """existing found but manager.update_checkin races to None -> still 404."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    checkin_id = (await resp.get_json())["id"]

    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    async def _none(self, tenant, checkin_id, **fields):
        return None

    monkeypatch.setattr(auto_checkins_api.AutoCheckInManager, "update_checkin", _none)

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}",
        json={"name": "renamed"},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_value_error_400(auto_checkins_app, monkeypatch) -> None:
    """A manager ValueError (bound violation) on update surfaces as 400."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    checkin_id = (await resp.get_json())["id"]

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}",
        json={"interval_minutes": 999},
        headers=headers,
    )
    assert resp.status_code == 400
    body = await resp.get_json()
    assert "interval_minutes" in body["error"]


@pytest.mark.asyncio
async def test_update_unexpected_exception_500(auto_checkins_app, monkeypatch) -> None:
    """A non-ValueError raised by the manager on update surfaces as 500."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    checkin_id = (await resp.get_json())["id"]

    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    async def _boom(self, tenant, checkin_id, **fields):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(auto_checkins_api.AutoCheckInManager, "update_checkin", _boom)

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}",
        json={"name": "renamed"},
        headers=headers,
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_delete_not_found_404(auto_checkins_app, monkeypatch) -> None:
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.delete(f"/api/v1/perftest_cluster/auto-checkins/{uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_unexpected_exception_500(auto_checkins_app, monkeypatch) -> None:
    """A non-ValueError raised by the manager on delete surfaces as 500."""
    client, headers = await _licensed_client(auto_checkins_app, monkeypatch)
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "x",
            "device_id": str(uuid4()),
            "target_kind": "external",
            "target": "example.com",
        },
        headers=headers,
    )
    checkin_id = (await resp.get_json())["id"]

    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    async def _boom(self, tenant, checkin_id):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(auto_checkins_api.AutoCheckInManager, "delete_checkin", _boom)

    resp = await client.delete(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", headers=headers
    )
    assert resp.status_code == 500
