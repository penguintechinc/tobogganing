"""Coverage backfill for perftest_cluster devices.py and enrollment.py APIs.

Covers device listing/get/heartbeat/config (API-key authenticated, IDOR
protected) and enrollment secret CRUD plus the public enroll_device flow,
including the Professional-tier >5-device gate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from quart import Quart

from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.enrollment_manager import (
    EnrollmentManager,
)

# ---------------------------------------------------------------------------
# devices.py: list / get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_devices_empty(app_all_perftest_realdal: Quart, pf_write_token: str) -> None:
    """Listing devices with none registered returns an empty list."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/devices",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["devices"] == []


@pytest.mark.asyncio
async def test_list_and_get_device(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any
) -> None:
    """A registered device shows up in list and get."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _api_key = await dev_mgr.register_device(
        {"name": "sensor-1", "serial": "SN-1", "hostname": "h1", "os": "linux"}
    )

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    list_resp = await client.get("/api/v1/perftest_cluster/devices", headers=headers)
    assert list_resp.status_code == 200
    listed = await list_resp.get_json()
    assert any(d["id"] == device.id for d in listed["devices"])

    get_resp = await client.get(f"/api/v1/perftest_cluster/devices/{device.id}", headers=headers)
    assert get_resp.status_code == 200
    got = await get_resp.get_json()
    assert got["device"]["id"] == device.id
    assert got["device"]["serial"] == "SN-1"


@pytest.mark.asyncio
async def test_get_device_not_found(app_all_perftest_realdal: Quart, pf_write_token: str) -> None:
    """GET on an unknown device_id returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/devices/ghost-device",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# devices.py: heartbeat / config (API-key authenticated, no JWT)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_missing_auth_header(app_all_perftest_realdal: Quart) -> None:
    """Heartbeat without an Authorization header returns 401."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post("/api/v1/perftest_cluster/devices/some-id/heartbeat")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_heartbeat_invalid_api_key(app_all_perftest_realdal: Quart) -> None:
    """Heartbeat with a bogus API key returns 401."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/devices/some-id/heartbeat",
        headers={"Authorization": "Bearer not-a-real-key"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_heartbeat_and_config_success(app_all_perftest_realdal: Quart, real_dal: Any) -> None:
    """A device authenticates with its own API key and can heartbeat + fetch config."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, api_key = await dev_mgr.register_device({"name": "sensor-2", "serial": "SN-2"})

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {api_key}"}

    hb_resp = await client.post(
        f"/api/v1/perftest_cluster/devices/{device.id}/heartbeat", headers=headers
    )
    assert hb_resp.status_code == 200
    hb_data = await hb_resp.get_json()
    assert hb_data["status"] == "heartbeat_recorded"

    cfg_resp = await client.get(
        f"/api/v1/perftest_cluster/devices/{device.id}/config", headers=headers
    )
    assert cfg_resp.status_code == 200
    cfg_data = await cfg_resp.get_json()
    assert cfg_data["device_id"] == device.id
    assert "config" in cfg_data


@pytest.mark.asyncio
async def test_heartbeat_idor_device_id_mismatch(
    app_all_perftest_realdal: Quart, real_dal: Any
) -> None:
    """A device's API key cannot be used to heartbeat a different device_id (403)."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device_a, api_key_a = await dev_mgr.register_device({"name": "a", "serial": "SN-A"})
    device_b, _api_key_b = await dev_mgr.register_device({"name": "b", "serial": "SN-B"})

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        f"/api/v1/perftest_cluster/devices/{device_b.id}/heartbeat",
        headers={"Authorization": f"Bearer {api_key_a}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_config_idor_device_id_mismatch(
    app_all_perftest_realdal: Quart, real_dal: Any
) -> None:
    """A device's API key cannot be used to fetch another device's config (403)."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device_a, api_key_a = await dev_mgr.register_device({"name": "a2", "serial": "SN-A2"})
    device_b, _api_key_b = await dev_mgr.register_device({"name": "b2", "serial": "SN-B2"})

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        f"/api/v1/perftest_cluster/devices/{device_b.id}/config",
        headers={"Authorization": f"Bearer {api_key_a}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_config_missing_and_invalid_auth(app_all_perftest_realdal: Quart) -> None:
    """Config endpoint enforces the same API-key auth as heartbeat."""
    client = app_all_perftest_realdal.test_client()

    no_auth = await client.get("/api/v1/perftest_cluster/devices/x/config")
    assert no_auth.status_code == 401

    bad_auth = await client.get(
        "/api/v1/perftest_cluster/devices/x/config",
        headers={"Authorization": "Bearer garbage"},
    )
    assert bad_auth.status_code == 401


# ---------------------------------------------------------------------------
# enrollment.py: secrets CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrollment_secrets_crud(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """Full lifecycle: list (empty) -> create -> list (1) -> delete -> 404."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    empty = await client.get("/api/v1/perftest_cluster/enrollment/secrets", headers=headers)
    assert empty.status_code == 200
    assert (await empty.get_json())["secrets"] == []

    create_resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/secrets/ou-1",
        json={"expires_at": "2099-01-01T00:00:00Z"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    created = await create_resp.get_json()
    secret_id = created["secret"]["id"]
    raw_secret = created["secret"]["raw"]
    assert raw_secret

    listed = await client.get("/api/v1/perftest_cluster/enrollment/secrets", headers=headers)
    listed_data = await listed.get_json()
    assert any(s["id"] == secret_id for s in listed_data["secrets"])

    del_resp = await client.delete(
        f"/api/v1/perftest_cluster/enrollment/secrets/{secret_id}", headers=headers
    )
    assert del_resp.status_code == 200

    del_again = await client.delete(
        f"/api/v1/perftest_cluster/enrollment/secrets/{secret_id}", headers=headers
    )
    assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_create_secret_invalid_expires_at(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """A malformed expires_at value returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/secrets/ou-2",
        json={"expires_at": "not-a-date"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_secret_no_body_no_expires(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """Creating a secret with no body (no expires_at) still succeeds."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/secrets/ou-3",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# enrollment.py: enroll_device (public endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enroll_device_missing_fields(app_all_perftest_realdal: Quart) -> None:
    """enroll_device validates required fields one at a time."""
    client = app_all_perftest_realdal.test_client()

    no_body = await client.post("/api/v1/perftest_cluster/enrollment/enroll")
    assert no_body.status_code == 400

    missing_secret = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={"name": "n", "serial": "s"},
    )
    assert missing_secret.status_code == 400

    missing_name = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={"secret": "x", "serial": "s"},
    )
    assert missing_name.status_code == 400

    missing_serial = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={"secret": "x", "name": "n"},
    )
    assert missing_serial.status_code == 400


@pytest.mark.asyncio
async def test_enroll_device_invalid_secret(app_all_perftest_realdal: Quart) -> None:
    """An unknown/invalid enrollment secret returns 401."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={"secret": "does-not-exist", "name": "n", "serial": "s"},
        headers={"X-Tenant-ID": "default"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enroll_device_success(app_all_perftest_realdal: Quart, real_dal: Any) -> None:
    """A valid secret enrolls a device and returns its one-time API key."""
    enroll_mgr = EnrollmentManager(real_dal, "default")
    _secret_obj, raw_secret = await enroll_mgr.create_secret(
        org_unit_id="ou-enroll", expires_at=None, created_by=None
    )

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={
            "secret": raw_secret,
            "name": "new-device",
            "serial": "SN-NEW",
            "hostname": "h",
            "os": "linux",
        },
    )
    assert resp.status_code == 201
    data = await resp.get_json()
    assert data["device"]["serial"] == "SN-NEW"
    assert data["device"]["api_key"]
    assert data["device"]["org_unit_id"] == "ou-enroll"


@pytest.mark.asyncio
async def test_enroll_device_ignores_client_tenant_header(
    app_all_perftest_realdal: Quart, real_dal: Any
) -> None:
    """X-Tenant-ID is ignored — tenant is derived from the validated secret.

    regression: security-review finding HIGH-B (tenant isolation collapse).
    A secret created under tenant "real-secret-tenant" is presented with a
    forged X-Tenant-ID for a different tenant. Enrollment must still land
    the device in the secret's TRUE tenant, never the header's claimed one.
    """
    enroll_mgr = EnrollmentManager(real_dal, "real-secret-tenant")
    _secret_obj, raw_secret = await enroll_mgr.create_secret(
        org_unit_id="ou-real", expires_at=None, created_by=None
    )

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={
            "secret": raw_secret,
            "name": "spoof-device",
            "serial": "SN-SPOOF",
        },
        headers={"X-Tenant-ID": "attacker-claimed-tenant"},
    )
    assert resp.status_code == 201
    data = await resp.get_json()
    device_id = data["device"]["id"]

    # The device must be reachable in the secret's real tenant...
    real_tenant_mgr = DeviceManager(real_dal, "real-secret-tenant")
    await real_tenant_mgr.initialize()
    assert await real_tenant_mgr.get_device(device_id) is not None

    # ...and completely invisible to the tenant the client merely claimed.
    spoofed_tenant_mgr = DeviceManager(real_dal, "attacker-claimed-tenant")
    await spoofed_tenant_mgr.initialize()
    assert await spoofed_tenant_mgr.get_device(device_id) is None


@pytest.mark.asyncio
async def test_enroll_device_limit_reached_without_professional(
    app_all_perftest_realdal: Quart, monkeypatch: Any
) -> None:
    """Without a Professional license, enrollment is capped at 5 active devices.

    Mocks EnrollmentManager/DeviceManager directly at the API module to isolate
    the tier-gate branch from database wiring.
    """
    import hub_api.modules.perftest_cluster.api.enrollment as enrollment_api
    from hub_api.modules.perftest_cluster.services.enrollment_manager import (
        EnrollmentSecret,
    )

    stub_secret = EnrollmentSecret(
        id="secret-1",
        tenant="limited-tenant",
        org_unit_id="ou-x",
        secret_hash="unused",
        expires_at=None,
        created_at=datetime.now(timezone.utc),
        created_by=None,
    )
    monkeypatch.setattr(
        enrollment_api,
        "verify_secret_any_tenant",
        AsyncMock(return_value=stub_secret),
    )

    mock_dev_mgr = MagicMock()
    mock_dev_mgr.initialize = AsyncMock()
    mock_dev_mgr.count_active_devices = AsyncMock(return_value=5)
    monkeypatch.setattr(enrollment_api, "DeviceManager", lambda db, tenant: mock_dev_mgr)
    monkeypatch.setattr(enrollment_api, "_is_licensed_for_tier", lambda tier: False)

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={"secret": "raw-secret", "name": "d6", "serial": "SN-6"},
    )
    assert resp.status_code == 402
    data = await resp.get_json()
    assert "limit" in data["error"].lower()


@pytest.mark.asyncio
async def test_enroll_device_limit_bypassed_with_professional(
    app_all_perftest_realdal: Quart, monkeypatch: Any
) -> None:
    """With a Professional license, the 5-device cap is bypassed (201)."""
    import hub_api.modules.perftest_cluster.api.enrollment as enrollment_api
    from hub_api.modules.perftest_cluster.services.device_manager import Device
    from hub_api.modules.perftest_cluster.services.enrollment_manager import (
        EnrollmentSecret,
    )

    stub_secret = EnrollmentSecret(
        id="secret-2",
        tenant="unlimited-tenant",
        org_unit_id="ou-x",
        secret_hash="unused",
        expires_at=None,
        created_at=datetime.now(timezone.utc),
        created_by=None,
    )
    monkeypatch.setattr(
        enrollment_api,
        "verify_secret_any_tenant",
        AsyncMock(return_value=stub_secret),
    )

    registered_device = Device(
        id="new-device-id",
        tenant="unlimited-tenant",
        org_unit_id="ou-x",
        name="u6",
        serial="USN-6",
        hostname=None,
        os=None,
        status="online",
        last_heartbeat=None,
        device_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_dev_mgr = MagicMock()
    mock_dev_mgr.initialize = AsyncMock()
    mock_dev_mgr.count_active_devices = AsyncMock(return_value=5)
    mock_dev_mgr.register_device = AsyncMock(return_value=(registered_device, "generated-api-key"))
    monkeypatch.setattr(enrollment_api, "DeviceManager", lambda db, tenant: mock_dev_mgr)
    monkeypatch.setattr(enrollment_api, "_is_licensed_for_tier", lambda tier: True)

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/enrollment/enroll",
        json={"secret": "raw-secret", "name": "u6", "serial": "USN-6"},
    )
    assert resp.status_code == 201
    data = await resp.get_json()
    assert data["device"]["serial"] == "USN-6"
    assert data["device"]["api_key"] == "generated-api-key"
