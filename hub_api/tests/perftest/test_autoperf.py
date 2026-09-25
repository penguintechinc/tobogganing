"""Coverage backfill for AutoPerf API (api/autoperf.py) and manager service
(services/autoperf_manager.py).

Exercises policy CRUD over HTTP, the tiered escalation/de-escalation state
machine, interval validation, and the scheduler-job retune paths against a
real migrated sqlite DAL.
"""

from __future__ import annotations

from typing import Any

import pytest
from quart import Quart

from hub_api.modules.perftest_cluster.services.autoperf_manager import (
    AutoPerfManager,
)

# ---------------------------------------------------------------------------
# API: create_policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_policy_requires_body(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """POST with no JSON body returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_policy_missing_name(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """Missing required 'name' field returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={"device_id": "dev-1", "target": "1.1.1.1"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "name" in data["error"]


@pytest.mark.asyncio
async def test_create_policy_missing_device_id(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """Missing required 'device_id' field returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={"name": "p", "target": "1.1.1.1"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "device_id" in data["error"]


@pytest.mark.asyncio
async def test_create_policy_missing_target(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """Missing required 'target' field returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={"name": "p", "device_id": "dev-1"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "target" in data["error"]


@pytest.mark.asyncio
async def test_create_policy_interval_too_low(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """Interval below the 30s floor returns 400 at the API layer."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "p",
            "device_id": "dev-1",
            "target": "1.1.1.1",
            "t1_interval_seconds": 10,
        },
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "30" in data["error"]


@pytest.mark.asyncio
async def test_create_policy_tier_order_violation(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """t3 > t2 > t1 ordering violation returns 400."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "p",
            "device_id": "dev-1",
            "target": "1.1.1.1",
            "t1_interval_seconds": 60,
            "t2_interval_seconds": 90,
            "t3_interval_seconds": 120,
        },
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "t3_interval" in data["error"]


@pytest.mark.asyncio
async def test_create_policy_success(app_all_perftest_realdal: Quart, pf_write_token: str) -> None:
    """Valid payload creates a policy and returns 201 with full fields."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "critical-uplink",
            "device_id": "dev-1",
            "target": "8.8.8.8",
            "t1_interval_seconds": 300,
            "t2_interval_seconds": 120,
            "t3_interval_seconds": 60,
        },
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 201
    data = await resp.get_json()
    assert data["name"] == "critical-uplink"
    assert data["t1_interval_seconds"] == 300


@pytest.mark.asyncio
async def test_create_policy_readonly_forbidden(
    app_all_perftest_realdal: Quart, pf_readonly_token: str
) -> None:
    """A read-only token cannot create a policy (403)."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={"name": "p", "device_id": "dev-1", "target": "1.1.1.1"},
        headers={"Authorization": f"Bearer {pf_readonly_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# API: list / get / delete / state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_get_delete_state_roundtrip(
    app_all_perftest_realdal: Quart, pf_write_token: str
) -> None:
    """Full roundtrip: create -> list -> get -> get_state -> delete -> 404s."""
    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={"name": "rt-policy", "device_id": "dev-2", "target": "9.9.9.9"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    policy_id = (await create_resp.get_json())["id"]

    list_resp = await client.get("/api/v1/perftest_cluster/autoperf/policies", headers=headers)
    assert list_resp.status_code == 200
    listed = await list_resp.get_json()
    assert any(p["id"] == policy_id for p in listed["policies"])

    get_resp = await client.get(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}", headers=headers
    )
    assert get_resp.status_code == 200
    assert (await get_resp.get_json())["id"] == policy_id

    state_resp = await client.get(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}/state",
        headers=headers,
    )
    assert state_resp.status_code == 200
    state = await state_resp.get_json()
    assert state["current_tier"] == 1

    del_resp = await client.delete(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}", headers=headers
    )
    assert del_resp.status_code == 204

    get_after_delete = await client.get(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}", headers=headers
    )
    assert get_after_delete.status_code == 404

    state_after_delete = await client.get(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}/state",
        headers=headers,
    )
    assert state_after_delete.status_code == 404

    del_again = await client.delete(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}", headers=headers
    )
    assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_get_policy_not_found(app_all_perftest_realdal: Quart, pf_write_token: str) -> None:
    """GET on an unknown policy id returns 404."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/autoperf/policies/does-not-exist",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_policies_empty(app_all_perftest_realdal: Quart, pf_write_token: str) -> None:
    """Listing with no policies returns an empty list, not an error."""
    client = app_all_perftest_realdal.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/autoperf/policies",
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["policies"] == []


# ---------------------------------------------------------------------------
# Service: AutoPerfManager direct tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manager_requires_db() -> None:
    """AutoPerfManager raises ValueError when constructed without a db."""
    with pytest.raises(ValueError, match="Database instance cannot be None"):
        AutoPerfManager(None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_manager_create_policy_interval_validation(real_dal: Any) -> None:
    """Each interval independently enforces the >=30s floor."""
    mgr = AutoPerfManager(real_dal)

    with pytest.raises(ValueError, match="t1_interval_seconds"):
        await mgr.create_policy(
            tenant="t1", name="p", device_id="d", target="x", t1_interval_seconds=5
        )
    with pytest.raises(ValueError, match="t2_interval_seconds"):
        await mgr.create_policy(
            tenant="t1", name="p", device_id="d", target="x", t2_interval_seconds=5
        )
    with pytest.raises(ValueError, match="t3_interval_seconds"):
        await mgr.create_policy(
            tenant="t1", name="p", device_id="d", target="x", t3_interval_seconds=5
        )
    with pytest.raises(ValueError, match="t3_interval_seconds"):
        await mgr.create_policy(
            tenant="t1",
            name="p",
            device_id="d",
            target="x",
            t1_interval_seconds=60,
            t2_interval_seconds=90,
            t3_interval_seconds=120,
        )


@pytest.mark.asyncio
async def test_manager_record_cycle_not_found(real_dal: Any) -> None:
    """record_cycle raises RuntimeError for an unknown policy_id."""
    mgr = AutoPerfManager(real_dal)
    with pytest.raises(RuntimeError, match="not found"):
        await mgr.record_cycle("tenant-x", "no-such-policy", breached=False)


@pytest.mark.asyncio
async def test_manager_escalation_state_machine(real_dal: Any) -> None:
    """Breach escalates tier (capped at 3); clean cycles de-escalate after N."""
    mgr = AutoPerfManager(real_dal)
    tenant = "tenant-escalate"

    policy = await mgr.create_policy(
        tenant=tenant,
        name="escalation-test",
        device_id="dev-esc",
        target="1.2.3.4",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=2,
    )
    policy_id = policy["id"]

    state = await mgr.get_state(tenant, policy_id)
    assert state["current_tier"] == 1

    # Breach: tier 1 -> 2
    state = await mgr.record_cycle(tenant, policy_id, breached=True)
    assert state["current_tier"] == 2
    assert state["clean_cycles"] == 0
    assert state["escalated_at"] is not None

    # Breach again: tier 2 -> 3
    state = await mgr.record_cycle(tenant, policy_id, breached=True)
    assert state["current_tier"] == 3

    # Breach again: capped at 3 (min(tier+1, 3))
    state = await mgr.record_cycle(tenant, policy_id, breached=True)
    assert state["current_tier"] == 3

    # Clean cycle 1: not enough to de-escalate yet (need 2)
    state = await mgr.record_cycle(tenant, policy_id, breached=False)
    assert state["current_tier"] == 3
    assert state["clean_cycles"] == 1

    # Clean cycle 2: de-escalate tier 3 -> 2, clean_cycles resets
    state = await mgr.record_cycle(tenant, policy_id, breached=False)
    assert state["current_tier"] == 2
    assert state["clean_cycles"] == 0


@pytest.mark.asyncio
async def test_manager_clean_cycle_at_tier_one_stays(real_dal: Any) -> None:
    """Clean cycles at tier 1 never de-escalate below the floor."""
    mgr = AutoPerfManager(real_dal)
    tenant = "tenant-floor"

    policy = await mgr.create_policy(
        tenant=tenant,
        name="floor-test",
        device_id="dev-floor",
        target="1.2.3.4",
        deescalate_after_clean=1,
    )
    policy_id = policy["id"]

    state = await mgr.record_cycle(tenant, policy_id, breached=False)
    assert state["current_tier"] == 1
    assert state["clean_cycles"] == 1


@pytest.mark.asyncio
async def test_manager_delete_policy_not_found(real_dal: Any) -> None:
    """delete_policy returns False when the policy/state doesn't exist."""
    mgr = AutoPerfManager(real_dal)
    result = await mgr.delete_policy("tenant-x", "no-such-policy")
    assert result is False


@pytest.mark.asyncio
async def test_manager_delete_policy_removes_job(real_dal: Any) -> None:
    """delete_policy removes the associated scheduler job, state, and policy."""
    mgr = AutoPerfManager(real_dal)
    tenant = "tenant-del"

    policy = await mgr.create_policy(
        tenant=tenant, name="del-test", device_id="dev-del", target="1.2.3.4"
    )
    policy_id = policy["id"]

    jobs = await mgr.job_manager.list_jobs(tenant, "perftest_cluster")
    assert any(
        j["job_type"] == "autoperf_cycle" and j["payload"].get("policy_id") == policy_id
        for j in jobs
    )

    deleted = await mgr.delete_policy(tenant, policy_id)
    assert deleted is True

    jobs_after = await mgr.job_manager.list_jobs(tenant, "perftest_cluster")
    assert not any(
        j["job_type"] == "autoperf_cycle" and j["payload"].get("policy_id") == policy_id
        for j in jobs_after
    )

    state_after = await mgr.get_state(tenant, policy_id)
    assert state_after is None


@pytest.mark.asyncio
async def test_manager_update_job_interval_missing_job_logs_warning(
    real_dal: Any,
) -> None:
    """_update_job_interval logs a warning (does not raise) if no matching job exists."""
    mgr = AutoPerfManager(real_dal)
    # No policy/job created for this tenant/policy_id combo.
    await mgr._update_job_interval("tenant-nowhere", "ghost-policy", 60)


def test_manager_tier_to_interval_mapping() -> None:
    """_tier_to_interval maps tier 1/2/3+ to t1/t2/t3 respectively."""
    # Construct with a throwaway truthy db (never awaited in this sync test).
    mgr = AutoPerfManager(db=object())
    assert mgr._tier_to_interval(1, 300, 120, 60) == 300
    assert mgr._tier_to_interval(2, 300, 120, 60) == 120
    assert mgr._tier_to_interval(3, 300, 120, 60) == 60
    assert mgr._tier_to_interval(99, 300, 120, 60) == 60


# ---------------------------------------------------------------------------
# API: exception handlers (manager-raised ValueError / generic Exception)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_policy_manager_value_error_returns_400(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A ValueError raised by the manager (not caught by handler pre-validation)
    is translated to a 400 with the error message."""
    import hub_api.modules.perftest_cluster.api.autoperf as autoperf_api

    async def _boom(self: Any, **kwargs: Any) -> None:
        raise ValueError("manager-level validation failed")

    monkeypatch.setattr(autoperf_api.AutoPerfManager, "create_policy", _boom)

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={"name": "p", "device_id": "d", "target": "x"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 400
    assert "manager-level validation failed" in (await resp.get_json())["error"]


@pytest.mark.asyncio
async def test_autoperf_handlers_generic_exception_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """create/list/get/delete/state all catch unexpected exceptions -> 500."""
    import hub_api.modules.perftest_cluster.api.autoperf as autoperf_api

    async def _boom_get_db() -> Any:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(autoperf_api, "get_db", _boom_get_db)

    client = app_all_perftest_realdal.test_client()
    headers = {"Authorization": f"Bearer {pf_write_token}"}

    create_resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={"name": "p", "device_id": "d", "target": "x"},
        headers=headers,
    )
    assert create_resp.status_code == 500

    list_resp = await client.get("/api/v1/perftest_cluster/autoperf/policies", headers=headers)
    assert list_resp.status_code == 500

    get_resp = await client.get("/api/v1/perftest_cluster/autoperf/policies/x", headers=headers)
    assert get_resp.status_code == 500

    delete_resp = await client.delete(
        "/api/v1/perftest_cluster/autoperf/policies/x", headers=headers
    )
    assert delete_resp.status_code == 500

    state_resp = await client.get(
        "/api/v1/perftest_cluster/autoperf/policies/x/state", headers=headers
    )
    assert state_resp.status_code == 500
