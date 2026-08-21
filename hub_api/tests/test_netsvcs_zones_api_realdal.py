"""Real-DAL tests for netsvcs zones API endpoint success/error branches.

tests/test_netsvcs_zones.py mocks ZoneManager/ConfigService entirely, so the
blueprint's own success-path serialization (get_zone, update_zone,
list_records success, create/update_record, delete_record, delete_zone) was
never exercised end-to-end. This file drives the real blueprint + real
ZoneManager against a migrated real_dal.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Test app with netsvcs module registered (mock_db swapped for real_dal below)."""
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = "default"

    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def app_with_netsvcs_realdal(
    app_with_netsvcs: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Patch get_db() to real_dal wherever the zones blueprint imports it."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app

    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.netsvcs.api.zones

    monkeypatch.setattr(hub_api.modules.netsvcs.api.zones, "get_db", get_db_func)

    app_with_netsvcs.db = real_dal
    return app_with_netsvcs


@pytest_asyncio.fixture
async def tenant_token(app_with_netsvcs_realdal: Quart) -> str:
    """JWT for a fresh tenant with dns:read + dns:write scope."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-zones",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": f"tenant-zones-{uuid4()}",
        "scope": "dns:read dns:write",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest.fixture(autouse=True)
def _feature_flag_on() -> Any:
    """Keep the netsvcs.zones feature flag enabled for every test in this file."""
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True) as m:
        yield m


@pytest.mark.asyncio
async def test_zone_and_record_full_lifecycle(
    app_with_netsvcs_realdal: Quart, tenant_token: str
) -> None:
    """Drives create -> get -> update -> list_records -> create_record -> update_record
    -> delete_record -> delete_zone through the real blueprint + real ZoneManager."""
    client = app_with_netsvcs_realdal.test_client()
    headers = {"Authorization": f"Bearer {tenant_token}"}

    # Create
    create_resp = await client.post(
        "/api/v1/netsvcs/zones",
        headers=headers,
        json={"name": "lifecycle.com", "visibility": "public", "description": "test zone"},
    )
    assert create_resp.status_code == 201
    zone = await create_resp.get_json()
    zone_id = zone["id"]

    # Duplicate create -> 400
    dup_resp = await client.post(
        "/api/v1/netsvcs/zones", headers=headers, json={"name": "lifecycle.com"}
    )
    assert dup_resp.status_code == 400

    # Get success
    get_resp = await client.get(f"/api/v1/netsvcs/zones/{zone_id}", headers=headers)
    assert get_resp.status_code == 200
    assert (await get_resp.get_json())["name"] == "lifecycle.com"

    # Get not found
    missing_resp = await client.get("/api/v1/netsvcs/zones/nonexistent", headers=headers)
    assert missing_resp.status_code == 404

    # Update success
    update_resp = await client.put(
        f"/api/v1/netsvcs/zones/{zone_id}",
        headers=headers,
        json={"visibility": "internal"},
    )
    assert update_resp.status_code == 200
    assert (await update_resp.get_json())["visibility"] == "internal"

    # Update not found
    update_missing = await client.put(
        "/api/v1/netsvcs/zones/nonexistent", headers=headers, json={"name": "x"}
    )
    assert update_missing.status_code == 404

    # list_records empty
    list_empty = await client.get(f"/api/v1/netsvcs/zones/{zone_id}/records", headers=headers)
    assert list_empty.status_code == 200
    assert (await list_empty.get_json())["records"] == []

    # list_records zone not found
    list_missing = await client.get("/api/v1/netsvcs/zones/nonexistent/records", headers=headers)
    assert list_missing.status_code == 404

    # create_record success
    create_rec_resp = await client.post(
        f"/api/v1/netsvcs/zones/{zone_id}/records",
        headers=headers,
        json={"name": "www", "type": "A", "value": "1.2.3.4", "ttl": 300},
    )
    assert create_rec_resp.status_code == 201
    record = await create_rec_resp.get_json()
    record_id = record["id"]

    # create_record invalid type -> 400
    invalid_rec_resp = await client.post(
        f"/api/v1/netsvcs/zones/{zone_id}/records",
        headers=headers,
        json={"name": "bad", "type": "BOGUS", "value": "x"},
    )
    assert invalid_rec_resp.status_code == 400

    # list_records now has one entry
    list_resp = await client.get(f"/api/v1/netsvcs/zones/{zone_id}/records", headers=headers)
    assert len((await list_resp.get_json())["records"]) == 1

    # update_record success
    update_rec_resp = await client.put(
        f"/api/v1/netsvcs/zones/{zone_id}/records/{record_id}",
        headers=headers,
        json={"value": "5.6.7.8", "ttl": 600},
    )
    assert update_rec_resp.status_code == 200
    assert (await update_rec_resp.get_json())["value"] == "5.6.7.8"

    # update_record not found
    update_rec_missing = await client.put(
        f"/api/v1/netsvcs/zones/{zone_id}/records/nonexistent",
        headers=headers,
        json={"value": "x"},
    )
    assert update_rec_missing.status_code == 404

    # delete_record not found
    del_rec_missing = await client.delete(
        f"/api/v1/netsvcs/zones/{zone_id}/records/nonexistent", headers=headers
    )
    assert del_rec_missing.status_code == 404

    # delete_record success
    del_rec_resp = await client.delete(
        f"/api/v1/netsvcs/zones/{zone_id}/records/{record_id}", headers=headers
    )
    assert del_rec_resp.status_code == 200

    # delete_zone not found
    del_zone_missing = await client.delete("/api/v1/netsvcs/zones/nonexistent", headers=headers)
    assert del_zone_missing.status_code == 404

    # delete_zone success
    del_zone_resp = await client.delete(f"/api/v1/netsvcs/zones/{zone_id}", headers=headers)
    assert del_zone_resp.status_code == 200


@pytest.mark.asyncio
async def test_list_zones_success_with_data(
    app_with_netsvcs_realdal: Quart, tenant_token: str
) -> None:
    """list_zones returns the created zone with correct fields."""
    client = app_with_netsvcs_realdal.test_client()
    headers = {"Authorization": f"Bearer {tenant_token}"}

    await client.post("/api/v1/netsvcs/zones", headers=headers, json={"name": "listed.com"})

    response = await client.get("/api/v1/netsvcs/zones", headers=headers)
    assert response.status_code == 200
    data = await response.get_json()
    assert any(z["name"] == "listed.com" for z in data["zones"])
