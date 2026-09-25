"""Coverage backfill for the remaining perftest_cluster/c2c/client API gaps:
tests.py, scheduled_tests.py, org_units.py, stats.py, api/schedules.py
(client), api/client_config.py, api/version.py, c2c/api/endpoints.py,
c2c/api/recurring.py, c2c/api/regions.py.

Targets not-found branches and the generic ``except Exception -> 500``
handlers not already exercised by the existing per-module test files.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from quart import Quart

from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.org_unit_manager import OrgUnitManager
from hub_api.modules.perftest_cluster.services.test_manager import TestManager

# ---------------------------------------------------------------------------
# perftest_cluster/api/tests.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_test_not_found(app_all_perftest_realdal: Quart, pf_write_token: str) -> None:
    """GET on an unknown test_id returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/tests/ghost",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_test_list_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A TestManager failure during create_test is caught and returns 500."""
    import hub_api.modules.perftest_cluster.api.tests as tests_api

    async def _boom(self: Any, data: dict) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tests_api.TestManager, "create_test", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/tests",
        json={"device_id": "d", "test_type": "http"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_tests_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A TestManager failure during list_results is caught and returns 500."""
    import hub_api.modules.perftest_cluster.api.tests as tests_api

    async def _boom(self: Any, **kwargs: Any) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tests_api.TestManager, "list_results", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/tests",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_test_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A TestManager failure during get_test is caught and returns 500."""
    import hub_api.modules.perftest_cluster.api.tests as tests_api

    async def _boom(self: Any, test_id: str) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tests_api.TestManager, "get_test", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/tests/x",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_record_result_full_flow_and_errors(
    app_all_perftest_realdal: Quart, real_dal: Any
) -> None:
    """record_result: no auth, invalid key, missing body, device mismatch, not-found, success."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, api_key = await dev_mgr.register_device({"name": "d", "serial": "SN"})
    other_device, other_key = await dev_mgr.register_device({"name": "d2", "serial": "SN2"})

    test_mgr = TestManager(real_dal, "test-tenant")
    test_obj = await test_mgr.create_test(
        {"device_id": device.id, "test_type": "http", "status": "pending"}
    )
    other_test = await test_mgr.create_test(
        {"device_id": other_device.id, "test_type": "http", "status": "pending"}
    )

    client = app_all_perftest_realdal.test_client()

    no_auth = await client.post(f"/api/v1/perftest_cluster/tests/{test_obj.id}/results")
    assert no_auth.status_code == 401

    bad_auth = await client.post(
        f"/api/v1/perftest_cluster/tests/{test_obj.id}/results",
        headers={"Authorization": "Bearer garbage"},
    )
    assert bad_auth.status_code == 401

    no_body = await client.post(
        f"/api/v1/perftest_cluster/tests/{test_obj.id}/results",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert no_body.status_code == 400

    device_mismatch = await client.post(
        f"/api/v1/perftest_cluster/tests/{test_obj.id}/results",
        json={"device_id": other_device.id, "status": "completed"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert device_mismatch.status_code == 403

    not_found = await client.post(
        "/api/v1/perftest_cluster/tests/ghost-test/results",
        json={"device_id": device.id, "status": "completed"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert not_found.status_code == 404

    idor = await client.post(
        f"/api/v1/perftest_cluster/tests/{other_test.id}/results",
        json={"device_id": other_device.id, "status": "completed"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert idor.status_code == 403

    success = await client.post(
        f"/api/v1/perftest_cluster/tests/{test_obj.id}/results",
        json={"device_id": device.id, "status": "completed", "latency_ms": 5.0},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert success.status_code == 200
    data = await success.get_json()
    assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# perftest_cluster/api/scheduled_tests.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_scheduled_test_not_found(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """DELETE on an unknown scheduled test job returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.delete(
        "/api/v1/perftest_cluster/scheduled-tests/ghost",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_scheduled_test_missing_enabled_field(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """PATCH without an 'enabled' field returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.patch(
        "/api/v1/perftest_cluster/scheduled-tests/whatever",
        json={},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_scheduled_test_not_found(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """PATCH on an unknown job returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.patch(
        "/api/v1/perftest_cluster/scheduled-tests/ghost",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_scheduled_test_success_and_update_roundtrip(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create -> update enabled=False roundtrip exercises the success PATCH path."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_cluster/scheduled-tests",
        json={
            "device_id": "d",
            "test_type": "http",
            "target": "x",
            "interval_seconds": 60,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    job_id = (await create_resp.get_json())["id"]

    update_resp = await client.patch(
        f"/api/v1/perftest_cluster/scheduled-tests/{job_id}",
        json={"enabled": False},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert (await update_resp.get_json())["enabled"] is False


@pytest.mark.asyncio
async def test_create_scheduled_test_field_validation(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create_scheduled_test validates test_type/target are non-empty strings."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    bad_test_type = await client.post(
        "/api/v1/perftest_cluster/scheduled-tests",
        json={"device_id": "d", "test_type": "  ", "target": "x", "interval_seconds": 60},
        headers=headers,
    )
    assert bad_test_type.status_code == 400
    assert "test_type" in (await bad_test_type.get_json())["error"]

    bad_target = await client.post(
        "/api/v1/perftest_cluster/scheduled-tests",
        json={"device_id": "d", "test_type": "http", "target": "", "interval_seconds": 60},
        headers=headers,
    )
    assert bad_target.status_code == 400
    assert "target" in (await bad_target.get_json())["error"]


@pytest.mark.asyncio
async def test_scheduled_tests_manager_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """create/list/delete/update all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_cluster.api.scheduled_tests as st_api

    async def _boom_get_db() -> Any:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(st_api, "get_db", _boom_get_db)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_cluster/scheduled-tests",
        json={"device_id": "d", "test_type": "http", "target": "x", "interval_seconds": 60},
        headers=headers,
    )
    assert create_resp.status_code == 500

    list_resp = await client.get("/api/v1/perftest_cluster/scheduled-tests", headers=headers)
    assert list_resp.status_code == 500

    delete_resp = await client.delete("/api/v1/perftest_cluster/scheduled-tests/x", headers=headers)
    assert delete_resp.status_code == 500

    update_resp = await client.patch(
        "/api/v1/perftest_cluster/scheduled-tests/x",
        json={"enabled": True},
        headers=headers,
    )
    assert update_resp.status_code == 500


# ---------------------------------------------------------------------------
# perftest_cluster/api/org_units.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_units_not_found_paths(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """get/update/delete on an unknown OU id all return 404."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    get_resp = await client.get("/api/v1/perftest_cluster/org-units/ghost", headers=headers)
    assert get_resp.status_code == 404

    update_resp = await client.put(
        "/api/v1/perftest_cluster/org-units/ghost", json={"name": "x"}, headers=headers
    )
    assert update_resp.status_code == 404

    delete_resp = await client.delete("/api/v1/perftest_cluster/org-units/ghost", headers=headers)
    assert delete_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_org_unit_missing_name(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create_org_unit without 'name' returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/org-units",
        json={},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_org_units_manager_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A manager failure during list_ous is caught and returns 500."""
    import hub_api.modules.perftest_cluster.api.org_units as org_units_api

    async def _boom(self: Any, **kwargs: Any) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(org_units_api.OrgUnitManager, "list_ous", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/org-units",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_org_units_create_get_update_delete_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """create/get/update/delete all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_cluster.api.org_units as org_units_api

    async def _boom_get_db() -> Any:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(org_units_api, "get_db", _boom_get_db)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_cluster/org-units", json={"name": "x"}, headers=headers
    )
    assert create_resp.status_code == 500

    get_resp = await client.get("/api/v1/perftest_cluster/org-units/x", headers=headers)
    assert get_resp.status_code == 500

    update_resp = await client.put(
        "/api/v1/perftest_cluster/org-units/x", json={"name": "y"}, headers=headers
    )
    assert update_resp.status_code == 500

    delete_resp = await client.delete("/api/v1/perftest_cluster/org-units/x", headers=headers)
    assert delete_resp.status_code == 500


@pytest.mark.asyncio
async def test_update_org_unit_no_body(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """update_org_unit with no JSON body returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.put(
        "/api/v1/perftest_cluster/org-units/whatever",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# perftest_cluster/api/stats.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_summary_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A StatsManager failure during summary() is caught and returns 500."""
    import hub_api.modules.perftest_cluster.api.stats as stats_api

    async def _boom(self: Any, **kwargs: Any) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(stats_api.StatsManager, "summary", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/stats/summary",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_stats_other_endpoints_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """by-device / by-type / trends / recent all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_cluster.api.stats as stats_api

    async def _boom(self: Any, **kwargs: Any) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(stats_api.StatsManager, "by_device", _boom)
    monkeypatch.setattr(stats_api.StatsManager, "by_type", _boom)
    monkeypatch.setattr(stats_api.StatsManager, "trends", _boom)
    monkeypatch.setattr(stats_api.StatsManager, "recent", _boom)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    by_device_resp = await client.get("/api/v1/perftest_cluster/stats/by-device", headers=headers)
    assert by_device_resp.status_code == 500

    by_type_resp = await client.get("/api/v1/perftest_cluster/stats/by-type", headers=headers)
    assert by_type_resp.status_code == 500

    trends_resp = await client.get("/api/v1/perftest_cluster/stats/trends", headers=headers)
    assert trends_resp.status_code == 500

    recent_resp = await client.get("/api/v1/perftest_cluster/stats/recent", headers=headers)
    assert recent_resp.status_code == 500


# ---------------------------------------------------------------------------
# perftest_client/api/schedules.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_schedules_not_found_paths(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """get/update/delete on an unknown schedule id all return 404."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    get_resp = await client.get("/api/v1/perftest_client/schedules/ghost", headers=headers)
    assert get_resp.status_code == 404

    update_resp = await client.put(
        "/api/v1/perftest_client/schedules/ghost", json={"enabled": False}, headers=headers
    )
    assert update_resp.status_code == 404

    delete_resp = await client.delete("/api/v1/perftest_client/schedules/ghost", headers=headers)
    assert delete_resp.status_code == 404


@pytest.mark.asyncio
async def test_client_schedules_missing_required_fields(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create_schedule without required fields returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_client/schedules",
        json={"test_type": "http"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_client_schedules_manager_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A ScheduleManager failure during list_schedules is caught and returns 500."""
    import hub_api.modules.perftest_client.api.schedules as schedules_api

    async def _boom(self: Any, **kwargs: Any) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(schedules_api.ScheduleManager, "list_schedules", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_client/schedules",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_client_schedules_create_get_update_delete_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """create/get/update/delete all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_client.api.schedules as schedules_api

    async def _boom_get_db() -> Any:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(schedules_api, "get_db", _boom_get_db)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_client/schedules",
        json={"test_type": "http", "target": "x", "interval_seconds": 60},
        headers=headers,
    )
    assert create_resp.status_code == 500

    get_resp = await client.get("/api/v1/perftest_client/schedules/x", headers=headers)
    assert get_resp.status_code == 500

    update_resp = await client.put(
        "/api/v1/perftest_client/schedules/x", json={"enabled": False}, headers=headers
    )
    assert update_resp.status_code == 500

    delete_resp = await client.delete("/api/v1/perftest_client/schedules/x", headers=headers)
    assert delete_resp.status_code == 500


# ---------------------------------------------------------------------------
# perftest_client/api/client_config.py + api/version.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_config_error_returns_500(
    app_all_perftest_realdal: Quart, real_dal: Any, monkeypatch: Any
) -> None:
    """An unexpected exception in get_client_config is caught and returns 500."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, api_key = await dev_mgr.register_device({"name": "d", "serial": "SN"})

    import hub_api.modules.perftest_client.api.client_config as cc_api

    monkeypatch.setattr(
        cc_api,
        "authenticate_device_global",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_client/config",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_version_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """An unexpected exception in get_version is caught and returns 500."""
    import hub_api.modules.perftest_client.api.version as version_api

    monkeypatch.setattr(
        version_api, "current_claims", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_client/version",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# perftest_c2c/api/endpoints.py, recurring.py, regions.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c2c_endpoints_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A manager failure during list_endpoints is caught and returns 500."""
    import hub_api.modules.perftest_c2c.api.endpoints as endpoints_api

    async def _boom(self: Any, **kwargs: Any) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(endpoints_api.EndpointManager, "list_endpoints", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_c2c/endpoints",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_c2c_endpoints_create_get_update_delete_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """create/get/update/delete all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_c2c.api.endpoints as endpoints_api

    async def _boom_get_db() -> Any:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(endpoints_api, "get_db", _boom_get_db)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_c2c/endpoints",
        json={"region": "us-east", "name": "e", "engine_url": "http://e", "target": "t"},
        headers=headers,
    )
    assert create_resp.status_code == 500

    get_resp = await client.get("/api/v1/perftest_c2c/endpoints/x", headers=headers)
    assert get_resp.status_code == 500

    update_resp = await client.patch(
        "/api/v1/perftest_c2c/endpoints/x", json={"name": "y"}, headers=headers
    )
    assert update_resp.status_code == 500

    delete_resp = await client.delete("/api/v1/perftest_c2c/endpoints/x", headers=headers)
    assert delete_resp.status_code == 500


@pytest.mark.asyncio
async def test_c2c_endpoints_create_validation_and_duplicate(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create_endpoint validates required fields, blank api_key, and duplicates."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    missing_fields = await client.post(
        "/api/v1/perftest_c2c/endpoints", json={"region": "us-east"}, headers=headers
    )
    assert missing_fields.status_code == 400

    blank_api_key = await client.post(
        "/api/v1/perftest_c2c/endpoints",
        json={
            "region": "us-east",
            "name": "e1",
            "engine_url": "http://e1",
            "target": "t1",
            "api_key": "   ",
        },
        headers=headers,
    )
    assert blank_api_key.status_code == 400

    first = await client.post(
        "/api/v1/perftest_c2c/endpoints",
        json={"region": "us-east", "name": "dupe", "engine_url": "http://e", "target": "t"},
        headers=headers,
    )
    assert first.status_code == 201

    duplicate = await client.post(
        "/api/v1/perftest_c2c/endpoints",
        json={"region": "us-east", "name": "dupe", "engine_url": "http://e", "target": "t"},
        headers=headers,
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_c2c_endpoints_get_not_found(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """GET on an unknown c2c endpoint returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_c2c/endpoints/ghost",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_c2c_endpoints_update_not_found(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """PATCH on an unknown c2c endpoint returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.patch(
        "/api/v1/perftest_c2c/endpoints/ghost",
        json={"name": "x"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_c2c_endpoints_delete_not_found(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """DELETE on an unknown c2c endpoint returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.delete(
        "/api/v1/perftest_c2c/endpoints/ghost",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_c2c_recurring_list_and_not_found(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """list_recurring (empty), delete/patch on unknown job all behave correctly."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    list_resp = await client.get("/api/v1/perftest_c2c/recurring", headers=headers)
    assert list_resp.status_code == 200
    assert (await list_resp.get_json())["jobs"] == []

    delete_resp = await client.delete("/api/v1/perftest_c2c/recurring/ghost", headers=headers)
    assert delete_resp.status_code == 404

    patch_resp = await client.patch(
        "/api/v1/perftest_c2c/recurring/ghost", json={"enabled": True}, headers=headers
    )
    assert patch_resp.status_code == 404


@pytest.mark.asyncio
async def test_c2c_recurring_invalid_enabled_type(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """patch_recurring rejects a non-bool 'enabled' value."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.patch(
        "/api/v1/perftest_c2c/recurring/whatever",
        json={"enabled": "yes"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_c2c_recurring_create_validation(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """create_recurring validates job_type, node_health feature gate, and
    interval_seconds/endpoint_ids types."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    bad_job_type = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"interval_seconds": 60, "job_type": "not-a-type"},
        headers=headers,
    )
    assert bad_job_type.status_code == 400

    missing_interval = await client.post("/api/v1/perftest_c2c/recurring", json={}, headers=headers)
    assert missing_interval.status_code == 400

    too_short_interval = await client.post(
        "/api/v1/perftest_c2c/recurring", json={"interval_seconds": 5}, headers=headers
    )
    assert too_short_interval.status_code == 400

    empty_endpoint_ids = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"interval_seconds": 60, "endpoint_ids": []},
        headers=headers,
    )
    assert empty_endpoint_ids.status_code == 400

    non_string_endpoint_ids = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"interval_seconds": 60, "endpoint_ids": [123]},
        headers=headers,
    )
    assert non_string_endpoint_ids.status_code == 400

    not_a_list = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"interval_seconds": 60, "endpoint_ids": "not-a-list"},
        headers=headers,
    )
    assert not_a_list.status_code == 400


@pytest.mark.asyncio
async def test_c2c_recurring_manager_errors_return_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """create/list/delete/patch all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_c2c.api.recurring as recurring_api

    async def _boom_get_db() -> Any:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(recurring_api, "get_db", _boom_get_db)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_c2c/recurring", json={"interval_seconds": 60}, headers=headers
    )
    assert create_resp.status_code == 500

    list_resp = await client.get("/api/v1/perftest_c2c/recurring", headers=headers)
    assert list_resp.status_code == 500

    delete_resp = await client.delete("/api/v1/perftest_c2c/recurring/x", headers=headers)
    assert delete_resp.status_code == 500

    patch_resp = await client.patch(
        "/api/v1/perftest_c2c/recurring/x", json={"enabled": True}, headers=headers
    )
    assert patch_resp.status_code == 500


@pytest.mark.asyncio
async def test_c2c_regions_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A manager failure during list_regions is caught and returns 500."""
    import hub_api.modules.perftest_c2c.api.regions as regions_api

    async def _boom(self: Any, tenant: str) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(regions_api.EndpointManager, "list_regions", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_c2c/regions",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_c2c_regions_nodes_error_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A manager failure during visible_endpoints is caught and returns 500."""
    import hub_api.modules.perftest_c2c.api.regions as regions_api

    async def _boom(self: Any, tenant: str, region: str | None = None) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(regions_api.EndpointManager, "visible_endpoints", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_c2c/regions/nodes",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500
