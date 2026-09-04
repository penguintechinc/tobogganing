"""Coverage backfill for perftest_c2c services: endpoint_manager.py,
run_manager.py, matrix_service.py.

test_c2c_managers_realdal.py already covers create/tenant-isolation/atomic
increment/idempotent paths; this file targets update_endpoint validation,
list_regions/visible_endpoints aggregation, delete_endpoint, the remaining
authenticate_node_global branches, RunManager get/list/mark_failed, and
MatrixService.trends().
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_c2c.services.endpoint_manager import (
    EndpointManager,
    authenticate_node_global,
)
from hub_api.modules.perftest_c2c.services.matrix_service import MatrixService
from hub_api.modules.perftest_c2c.services.run_manager import RunManager

# ---------------------------------------------------------------------------
# EndpointManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_endpoint_invalid_visibility(real_dal: AsyncDB) -> None:
    """update_endpoint rejects an invalid visibility value."""
    mgr = EndpointManager(real_dal, "tenant-upd")
    endpoint, _key = await mgr.create_endpoint(
        region="us-east", name="e1", engine_url="http://e1", target="t1"
    )
    with pytest.raises(ValueError, match="visibility"):
        await mgr.update_endpoint(endpoint["id"], visibility="bogus")


@pytest.mark.asyncio
async def test_update_endpoint_no_valid_fields_returns_current(real_dal: AsyncDB) -> None:
    """update_endpoint with no recognized fields returns the unmodified endpoint."""
    mgr = EndpointManager(real_dal, "tenant-upd2")
    endpoint, _key = await mgr.create_endpoint(
        region="us-east", name="e2", engine_url="http://e2", target="t2"
    )
    result = await mgr.update_endpoint(endpoint["id"], not_a_real_field="x")
    assert result is not None
    assert result["id"] == endpoint["id"]


@pytest.mark.asyncio
async def test_update_endpoint_not_found(real_dal: AsyncDB) -> None:
    """update_endpoint returns None for an unknown endpoint id."""
    mgr = EndpointManager(real_dal, "tenant-upd3")
    result = await mgr.update_endpoint("ghost", name="x")
    assert result is None


@pytest.mark.asyncio
async def test_list_regions_aggregates_healthy_and_providers(real_dal: AsyncDB) -> None:
    """list_regions() counts healthy endpoints and collects distinct providers."""
    tenant = "tenant-regions"
    mgr = EndpointManager(real_dal, tenant)
    ep1, _ = await mgr.create_endpoint(
        region="us-east", name="e1", engine_url="http://e1", target="t1", provider="aws"
    )
    await real_dal(real_dal.c2c_endpoints.id == ep1["id"]).update(health_status="healthy")
    await mgr.create_endpoint(
        region="us-east", name="e2", engine_url="http://e2", target="t2", provider="gcp"
    )

    regions = await mgr.list_regions(tenant)
    us_east = next(r for r in regions if r["region"] == "us-east")
    assert us_east["node_count"] == 2
    assert us_east["healthy_count"] == 1
    assert set(us_east["providers"]) == {"aws", "gcp"}


@pytest.mark.asyncio
async def test_visible_endpoints_redacts_foreign_public(real_dal: AsyncDB) -> None:
    """visible_endpoints returns own endpoints fully + foreign public ones redacted."""
    own_tenant = "tenant-own"
    foreign_tenant = "tenant-foreign"

    own_mgr = EndpointManager(real_dal, own_tenant)
    own_ep, _ = await own_mgr.create_endpoint(
        region="us-east", name="own-ep", engine_url="http://own", target="own-t"
    )

    foreign_mgr = EndpointManager(real_dal, foreign_tenant)
    foreign_ep, _ = await foreign_mgr.create_endpoint(
        region="us-east",
        name="foreign-ep",
        engine_url="http://foreign",
        target="foreign-t",
        visibility="public",
    )

    visible = await own_mgr.visible_endpoints(own_tenant)
    own_result = next(e for e in visible if e["id"] == own_ep["id"])
    assert "engine_url" in own_result

    foreign_result = next(e for e in visible if e["id"] == foreign_ep["id"])
    assert "engine_url" not in foreign_result
    assert "target" not in foreign_result
    assert "api_key_hash" not in foreign_result

    # Region-filtered variant.
    filtered = await own_mgr.visible_endpoints(own_tenant, region="us-east")
    assert any(e["id"] == own_ep["id"] for e in filtered)


@pytest.mark.asyncio
async def test_delete_endpoint_not_found_and_success(real_dal: AsyncDB) -> None:
    """delete_endpoint returns False for unknown id, True + removes on success."""
    mgr = EndpointManager(real_dal, "tenant-del")
    assert await mgr.delete_endpoint("ghost") is False

    endpoint, _key = await mgr.create_endpoint(
        region="us-east", name="to-del", engine_url="http://x", target="t"
    )
    assert await mgr.delete_endpoint(endpoint["id"]) is True
    assert await mgr.get_endpoint(endpoint["id"]) is None


@pytest.mark.asyncio
async def test_authenticate_node_global_not_found(real_dal: AsyncDB) -> None:
    """An unknown API key returns None."""
    result = await authenticate_node_global(real_dal, "no-such-key")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_node_global_disabled_endpoint(real_dal: AsyncDB) -> None:
    """A disabled endpoint's API key fails authentication."""
    mgr = EndpointManager(real_dal, "tenant-disabled")
    endpoint, raw_key = await mgr.create_endpoint(
        region="us-east", name="disabled-ep", engine_url="http://x", target="t"
    )
    await mgr.update_endpoint(endpoint["id"], enabled=False)

    result = await authenticate_node_global(real_dal, raw_key)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_node_global_outer_exception_fail_closed() -> None:
    """A query error is caught and authentication fails closed (returns None)."""
    bad_db = MagicMock()
    bad_db.c2c_endpoints.api_key_hash = MagicMock()
    bad_db.c2c_endpoints.api_key_hash.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    result = await authenticate_node_global(bad_db, "some-key")
    assert result is None


# ---------------------------------------------------------------------------
# RunManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_not_found(real_dal: AsyncDB) -> None:
    """get_run returns None for an unknown run_id."""
    mgr = RunManager(real_dal, "tenant-run-nf")
    assert await mgr.get_run("ghost") is None


@pytest.mark.asyncio
async def test_list_runs_empty(real_dal: AsyncDB) -> None:
    """list_runs returns an empty list when no runs exist."""
    mgr = RunManager(real_dal, "tenant-run-empty")
    assert await mgr.list_runs() == []


@pytest.mark.asyncio
async def test_mark_failed(real_dal: AsyncDB) -> None:
    """mark_failed transitions a run to the failed status."""
    tenant = "tenant-run-failed"
    ep_mgr = EndpointManager(real_dal, tenant)
    ep_a, _ = await ep_mgr.create_endpoint(
        region="us-east", name="a", engine_url="http://a", target="a"
    )
    ep_b, _ = await ep_mgr.create_endpoint(
        region="us-west", name="b", engine_url="http://b", target="b"
    )

    run_mgr = RunManager(real_dal, tenant)
    run, _pairs = await run_mgr.create_run(
        test_types=["http"], endpoint_ids=[ep_a["id"], ep_b["id"]]
    )
    await run_mgr.mark_failed(run["id"])

    updated = await run_mgr.get_run(run["id"])
    assert updated["status"] == "failed"
    assert updated["completed_at"] is not None


@pytest.mark.asyncio
async def test_enqueue_run_import_error_reraises(real_dal: AsyncDB, monkeypatch: Any) -> None:
    """enqueue_run without a dispatch callable and unavailable Celery re-raises."""
    import builtins

    tenant = "tenant-run-import-err"
    run_mgr = RunManager(real_dal, tenant)

    real_import = builtins.__import__

    def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "hub_api.modules.perftest_c2c.worker.tasks":
            raise ImportError("celery not configured")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(ImportError):
        await run_mgr.enqueue_run("run-x", [("a", "b", "http")])


# ---------------------------------------------------------------------------
# MatrixService.trends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matrix_service_trends(real_dal: AsyncDB) -> None:
    """trends() returns the last `window` pair results oldest-to-newest."""
    tenant = "tenant-trends"
    ep_mgr = EndpointManager(real_dal, tenant)
    ep_a, _ = await ep_mgr.create_endpoint(
        region="us-east", name="a", engine_url="http://a", target="a"
    )
    ep_b, _ = await ep_mgr.create_endpoint(
        region="us-west", name="b", engine_url="http://b", target="b"
    )

    run_mgr = RunManager(real_dal, tenant)
    run, _pairs = await run_mgr.create_run(
        test_types=["http"], endpoint_ids=[ep_a["id"], ep_b["id"]]
    )
    await run_mgr.record_pair_result(
        run_id=run["id"],
        source_id=ep_a["id"],
        dest_id=ep_b["id"],
        source_region="us-east",
        dest_region="us-west",
        test_type="http",
        status="success",
        latency_ms=15.0,
        throughput=3.0,
        loss_pct=0.0,
    )

    service = MatrixService(real_dal, tenant)
    trends = await service.trends(
        source_region="us-east", dest_region="us-west", test_type="http", window=5
    )
    assert len(trends) == 1
    assert trends[0]["latency_ms"] == 15.0


@pytest.mark.asyncio
async def test_matrix_service_trends_empty(real_dal: AsyncDB) -> None:
    """trends() with no matching pair results returns an empty list."""
    service = MatrixService(real_dal, "tenant-trends-empty")
    trends = await service.trends(source_region="nowhere", dest_region="nowhere2", test_type="http")
    assert trends == []
