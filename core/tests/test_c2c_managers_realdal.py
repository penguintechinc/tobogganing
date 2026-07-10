"""Integration tests for C2C managers using real penguin-dal AsyncDB.

Tests using the real_dal fixture exercise the actual async penguin-dal API,
ensuring managers work correctly against a real (sqlite) database with proper schema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from core.modules.waddleperf_c2c.services.endpoint_manager import (
    EndpointManager,
    authenticate_node_global,
)
from core.modules.waddleperf_c2c.services.run_manager import RunManager
from core.modules.waddleperf_c2c.services.matrix_service import MatrixService


# ============================================================================
# EndpointManager Real DAL Tests
# ============================================================================


@pytest.mark.asyncio
async def test_endpoint_manager_create_endpoint_real_dal(real_dal: object) -> None:
    """Test creating and retrieving an endpoint with real DAL."""
    tenant = "test-tenant-1"
    manager = EndpointManager(real_dal, tenant)

    # Create endpoint with generated API key
    endpoint, raw_key = await manager.create_endpoint(
        region="us-east-1",
        name="test-ep-1",
        engine_url="http://localhost:8080",
        target="target.example.com",
        api_key=None,
    )

    assert endpoint["id"] is not None
    assert endpoint["region"] == "us-east-1"
    assert endpoint["name"] == "test-ep-1"
    assert endpoint["enabled"] is True
    assert raw_key is not None  # Generated key should be returned once

    # Retrieve it back
    retrieved = await manager.get_endpoint(endpoint["id"])
    assert retrieved is not None
    assert retrieved["id"] == endpoint["id"]
    assert retrieved["name"] == "test-ep-1"


@pytest.mark.asyncio
async def test_endpoint_manager_tenant_isolation_real_dal(real_dal: object) -> None:
    """Test tenant isolation - endpoints are not visible across tenants."""
    tenant1 = "tenant-1"
    tenant2 = "tenant-2"

    mgr1 = EndpointManager(real_dal, tenant1)
    mgr2 = EndpointManager(real_dal, tenant2)

    # Create endpoint in tenant1
    ep1, _ = await mgr1.create_endpoint(
        region="us-east-1",
        name="shared-name",
        engine_url="http://engine1",
        target="target1",
    )

    # Try to retrieve in tenant2 - should not find it
    not_found = await mgr2.get_endpoint(ep1["id"])
    assert not_found is None

    # List in tenant2 - should be empty
    endpoints_t2 = await mgr2.list_endpoints()
    assert len(endpoints_t2) == 0

    # List in tenant1 - should have the endpoint
    endpoints_t1 = await mgr1.list_endpoints()
    assert len(endpoints_t1) == 1
    assert endpoints_t1[0]["id"] == ep1["id"]


@pytest.mark.asyncio
async def test_endpoint_manager_reject_empty_api_key_real_dal(real_dal: object) -> None:
    """Test that empty/blank api_key is rejected (finding #4)."""
    tenant = "test-tenant"
    manager = EndpointManager(real_dal, tenant)

    # Blank string should be rejected
    with pytest.raises(ValueError, match="cannot be empty"):
        await manager.create_endpoint(
            region="us-east-1",
            name="test",
            engine_url="http://engine",
            target="target",
            api_key="   ",  # Blank after strip
        )

    # Only whitespace should be rejected
    with pytest.raises(ValueError, match="cannot be empty"):
        await manager.create_endpoint(
            region="us-east-1",
            name="test",
            engine_url="http://engine",
            target="target",
            api_key="\t\n",
        )


@pytest.mark.asyncio
async def test_authenticate_node_global_real_dal(real_dal: object) -> None:
    """Test global node authentication across tenants."""
    tenant1 = "tenant-1"
    mgr1 = EndpointManager(real_dal, tenant1)

    # Create endpoint with explicit API key
    ep1, _ = await mgr1.create_endpoint(
        region="us-east-1",
        name="auth-test",
        engine_url="http://engine1",
        target="target1",
        api_key="my-secret-key-12345",
    )

    # Authenticate globally using the raw key
    result = await authenticate_node_global(real_dal, "my-secret-key-12345")
    assert result is not None

    endpoint_dict, returned_tenant = result
    assert endpoint_dict["id"] == ep1["id"]
    assert returned_tenant == tenant1


@pytest.mark.asyncio
async def test_authenticate_node_global_reject_empty_key_real_dal(
    real_dal: object,
) -> None:
    """Test that authenticate_node_global rejects empty keys (finding #4)."""
    result = await authenticate_node_global(real_dal, "")
    assert result is None

    result = await authenticate_node_global(real_dal, "   ")
    assert result is None


# ============================================================================
# RunManager Real DAL Tests
# ============================================================================


@pytest.mark.asyncio
async def test_run_manager_create_run_real_dal(real_dal: object) -> None:
    """Test creating a run with real DAL."""
    tenant = "test-tenant"

    # First create 2 endpoints
    ep_mgr = EndpointManager(real_dal, tenant)
    ep1, _ = await ep_mgr.create_endpoint(
        region="us-east-1", name="ep1", engine_url="http://e1", target="t1"
    )
    ep2, _ = await ep_mgr.create_endpoint(
        region="us-west-1", name="ep2", engine_url="http://e2", target="t2"
    )

    # Create run
    run_mgr = RunManager(real_dal, tenant)
    run, pairs = await run_mgr.create_run(
        test_types=["latency", "throughput"],
        endpoint_ids=[ep1["id"], ep2["id"]],
        created_by="user-1",
    )

    assert run["id"] is not None
    assert run["status"] == "pending"
    assert run["total_pairs"] == 4  # 2 endpoints * 2 directions * 1 (pairs same but test_types=2)
    # Actually: (2 * 1) * 2 test_types = 4 pairs (e1->e2, e2->e1) * 2 test_types


@pytest.mark.asyncio
async def test_run_manager_record_pair_result_atomic_increment_real_dal(
    real_dal: object,
) -> None:
    """Test that pair result recording uses atomic counter increment (finding #2)."""
    tenant = "test-tenant"

    # Create endpoints
    ep_mgr = EndpointManager(real_dal, tenant)
    ep1, _ = await ep_mgr.create_endpoint(
        region="us-east-1", name="ep1", engine_url="http://e1", target="t1"
    )
    ep2, _ = await ep_mgr.create_endpoint(
        region="us-west-1", name="ep2", engine_url="http://e2", target="t2"
    )

    # Create run
    run_mgr = RunManager(real_dal, tenant)
    run, pairs = await run_mgr.create_run(
        test_types=["latency"],
        endpoint_ids=[ep1["id"], ep2["id"]],
    )

    run_id = run["id"]

    # Record one successful result
    result1 = await run_mgr.record_pair_result(
        run_id=run_id,
        source_id=ep1["id"],
        dest_id=ep2["id"],
        source_region="us-east-1",
        dest_region="us-west-1",
        test_type="latency",
        status="success",
        latency_ms=10.0,
    )

    assert result1["status"] == "success"

    # Check run was updated (atomic increment)
    updated_run = await run_mgr.get_run(run_id)
    assert updated_run is not None
    assert updated_run["completed_pairs"] == 1

    # Record one failed result
    result2 = await run_mgr.record_pair_result(
        run_id=run_id,
        source_id=ep2["id"],
        dest_id=ep1["id"],
        source_region="us-west-1",
        dest_region="us-east-1",
        test_type="latency",
        status="failed",
    )

    # Check run was updated (failed_pairs atomic increment)
    updated_run = await run_mgr.get_run(run_id)
    assert updated_run["completed_pairs"] == 2
    assert updated_run["failed_pairs"] == 1


@pytest.mark.asyncio
async def test_run_manager_record_pair_result_idempotent_real_dal(
    real_dal: object,
) -> None:
    """Test that recording the same pair result twice is idempotent."""
    tenant = "test-tenant"

    ep_mgr = EndpointManager(real_dal, tenant)
    ep1, _ = await ep_mgr.create_endpoint(
        region="us-east-1", name="ep1", engine_url="http://e1", target="t1"
    )
    ep2, _ = await ep_mgr.create_endpoint(
        region="us-west-1", name="ep2", engine_url="http://e2", target="t2"
    )

    run_mgr = RunManager(real_dal, tenant)
    run, _ = await run_mgr.create_run(
        test_types=["latency"],
        endpoint_ids=[ep1["id"], ep2["id"]],
    )

    run_id = run["id"]

    # Record result once
    result1 = await run_mgr.record_pair_result(
        run_id=run_id,
        source_id=ep1["id"],
        dest_id=ep2["id"],
        source_region="us-east-1",
        dest_region="us-west-1",
        test_type="latency",
        status="success",
        latency_ms=10.0,
    )

    # Record the same result again
    result2 = await run_mgr.record_pair_result(
        run_id=run_id,
        source_id=ep1["id"],
        dest_id=ep2["id"],
        source_region="us-east-1",
        dest_region="us-west-1",
        test_type="latency",
        status="success",
        latency_ms=10.0,
    )

    # Should return same result without incrementing counters again
    assert result1["id"] == result2["id"]

    # Check completed_pairs was only incremented once
    updated_run = await run_mgr.get_run(run_id)
    assert updated_run["completed_pairs"] == 1


# ============================================================================
# MatrixService Real DAL Tests
# ============================================================================


@pytest.mark.asyncio
async def test_matrix_service_latest_matrix_real_dal(real_dal: object) -> None:
    """Test building a latest matrix from pair results."""
    tenant = "test-tenant"

    # Create endpoints
    ep_mgr = EndpointManager(real_dal, tenant)
    ep1, _ = await ep_mgr.create_endpoint(
        region="us-east-1", name="ep1", engine_url="http://e1", target="t1"
    )
    ep2, _ = await ep_mgr.create_endpoint(
        region="us-west-1", name="ep2", engine_url="http://e2", target="t2"
    )

    # Create run and record results
    run_mgr = RunManager(real_dal, tenant)
    run, _ = await run_mgr.create_run(
        test_types=["latency"],
        endpoint_ids=[ep1["id"], ep2["id"]],
    )

    await run_mgr.record_pair_result(
        run_id=run["id"],
        source_id=ep1["id"],
        dest_id=ep2["id"],
        source_region="us-east-1",
        dest_region="us-west-1",
        test_type="latency",
        status="success",
        latency_ms=10.0,
    )

    # Get latest matrix
    svc = MatrixService(real_dal, tenant)
    matrix = await svc.latest_matrix("latency")

    assert matrix["test_type"] == "latency"
    assert "us-east-1" in matrix["regions"]
    assert "us-west-1" in matrix["regions"]
    assert len(matrix["cells"]) > 0


@pytest.mark.asyncio
async def test_matrix_service_run_matrix_real_dal(real_dal: object) -> None:
    """Test building a run matrix from pair results."""
    tenant = "test-tenant"

    ep_mgr = EndpointManager(real_dal, tenant)
    ep1, _ = await ep_mgr.create_endpoint(
        region="us-east-1", name="ep1", engine_url="http://e1", target="t1"
    )
    ep2, _ = await ep_mgr.create_endpoint(
        region="us-west-1", name="ep2", engine_url="http://e2", target="t2"
    )

    run_mgr = RunManager(real_dal, tenant)
    run, _ = await run_mgr.create_run(
        test_types=["latency"],
        endpoint_ids=[ep1["id"], ep2["id"]],
    )

    await run_mgr.record_pair_result(
        run_id=run["id"],
        source_id=ep1["id"],
        dest_id=ep2["id"],
        source_region="us-east-1",
        dest_region="us-west-1",
        test_type="latency",
        status="success",
        latency_ms=10.0,
    )

    svc = MatrixService(real_dal, tenant)
    matrix = await svc.run_matrix(run["id"])

    assert matrix["run_id"] == run["id"]
    assert "latency" in matrix["test_types"]
    assert len(matrix["cells"]) > 0
