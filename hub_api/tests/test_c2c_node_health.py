"""Tests for C2C node health sweep using real penguin-dal."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from quart import Quart
from penguin_dal import AsyncDB

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.modules.perftest_cluster.services.engine_client import EngineError


@pytest_asyncio.fixture
async def app_with_c2c_node_health_realdal(
    app_with_c2c: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Create test app with C2C module using real_dal."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app
    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.perftest_c2c.api.recurring
    monkeypatch.setattr(hub_api.modules.perftest_c2c.api.recurring, "get_db", get_db_func)

    app_with_c2c.db = real_dal
    return app_with_c2c


@pytest_asyncio.fixture
async def c2c_write_token_node_health(app_with_c2c_node_health_realdal: Quart) -> str:
    """Generate write token for node health tests."""
    provider = app_with_c2c_node_health_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read c2c:write",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


# ============================================================================
# Recurring API: job_type Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_recurring_job_type_matrix_run_default(
    app_with_c2c_node_health_realdal: Quart,
    c2c_write_token_node_health: str,
    monkeypatch: Any,
) -> None:
    """POST /recurring without job_type defaults to 'matrix_run'."""
    import shared.licensing.entitlements
    import hub_api.entitlements.gate

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.perftest_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    original_is_licensed = hub_api.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(hub_api.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_node_health_realdal.test_client()

    resp = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"endpoint_ids": ["ep-1"], "interval_seconds": 300},
        headers={"Authorization": f"Bearer {c2c_write_token_node_health}"},
    )
    assert resp.status_code == 201
    data = await resp.get_json()
    job_id = data.get("job_id")

    # Verify the job has job_type='matrix_run'
    from hub_api.scheduler.job_manager import JobManager

    job_mgr = JobManager(app_with_c2c_node_health_realdal.db)
    job = await job_mgr.get_job("test-tenant", job_id)
    assert job is not None
    assert job["job_type"] == "matrix_run"


@pytest.mark.asyncio
async def test_recurring_job_type_node_health_requires_regions_flag(
    app_with_c2c_node_health_realdal: Quart,
    c2c_write_token_node_health: str,
    monkeypatch: Any,
) -> None:
    """POST /recurring with job_type='node_health' without regions flag → 402."""
    import shared.licensing.entitlements
    import hub_api.entitlements.gate

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        # Enable recurring_runs but NOT regions
        if flag_key == "tobogganing.perftest_c2c.recurring_runs":
            return True
        if flag_key == "tobogganing.perftest_c2c.regions":
            return False
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    original_is_licensed = hub_api.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(hub_api.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_node_health_realdal.test_client()

    resp = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"interval_seconds": 300, "job_type": "node_health"},
        headers={"Authorization": f"Bearer {c2c_write_token_node_health}"},
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_recurring_job_type_invalid_value(
    app_with_c2c_node_health_realdal: Quart,
    c2c_write_token_node_health: str,
    monkeypatch: Any,
) -> None:
    """POST /recurring with invalid job_type → 400."""
    import shared.licensing.entitlements
    import hub_api.entitlements.gate

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.perftest_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    original_is_licensed = hub_api.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(hub_api.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_node_health_realdal.test_client()

    resp = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"interval_seconds": 300, "job_type": "invalid_type"},
        headers={"Authorization": f"Bearer {c2c_write_token_node_health}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_recurring_job_type_node_health_with_regions_flag(
    app_with_c2c_node_health_realdal: Quart,
    c2c_write_token_node_health: str,
    monkeypatch: Any,
) -> None:
    """POST /recurring with job_type='node_health' + regions flag → 201."""
    import shared.licensing.entitlements
    import hub_api.entitlements.gate

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.perftest_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    original_is_licensed = hub_api.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(hub_api.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_node_health_realdal.test_client()

    resp = await client.post(
        "/api/v1/perftest_c2c/recurring",
        json={"interval_seconds": 300, "job_type": "node_health"},
        headers={"Authorization": f"Bearer {c2c_write_token_node_health}"},
    )
    assert resp.status_code == 201
    data = await resp.get_json()
    job_id = data.get("job_id")

    # Verify the job has job_type='node_health'
    from hub_api.scheduler.job_manager import JobManager

    job_mgr = JobManager(app_with_c2c_node_health_realdal.db)
    job = await job_mgr.get_job("test-tenant", job_id)
    assert job is not None
    assert job["job_type"] == "node_health"


# ============================================================================
# Worker Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_node_health_healthy_endpoint(real_dal: AsyncDB) -> None:
    """node_health task marks endpoint as healthy on 200 response."""
    from hub_api.modules.perftest_c2c.worker.tasks import _node_health

    tenant = "test-tenant"
    endpoint_id = "ep-1"

    # Create test endpoint
    await real_dal.c2c_endpoints.async_insert(
        id=endpoint_id,
        tenant=tenant,
        region="us-west-2",
        name="Test Endpoint",
        engine_url="http://localhost:9000",
        target="192.168.1.1",
        api_key_hash="hash123",
        enabled=True,
        visibility="private",
        provider=None,
        health_status="unknown",
        last_health_check=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Mock engine factory that returns a healthy response
    class MockEngineClient:
        async def health(self) -> bool:
            return True

        async def close(self) -> None:
            pass

    def mock_engine_factory(ep: dict[str, Any]) -> MockEngineClient:
        return MockEngineClient()

    # Run the task
    await _node_health(
        job_id="test-job-1",
        tenant=tenant,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
        engine_factory=mock_engine_factory,
    )

    # Verify endpoint was updated
    rowset = await real_dal(
        (real_dal.c2c_endpoints.id == endpoint_id)
        & (real_dal.c2c_endpoints.tenant == tenant)
    ).select()
    endpoint = rowset.first()
    assert endpoint is not None
    assert endpoint.health_status == "healthy"
    assert endpoint.last_health_check is not None


@pytest.mark.asyncio
async def test_node_health_unhealthy_endpoint(real_dal: AsyncDB) -> None:
    """node_health task marks endpoint as unhealthy on non-200 response."""
    from hub_api.modules.perftest_c2c.worker.tasks import _node_health

    tenant = "test-tenant"
    endpoint_id = "ep-2"

    # Create test endpoint
    await real_dal.c2c_endpoints.async_insert(
        id=endpoint_id,
        tenant=tenant,
        region="us-west-2",
        name="Test Endpoint",
        engine_url="http://localhost:9000",
        target="192.168.1.2",
        api_key_hash="hash123",
        enabled=True,
        visibility="private",
        provider=None,
        health_status="healthy",
        last_health_check=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Mock engine factory that returns an unhealthy response
    class MockEngineClient:
        async def health(self) -> bool:
            return False

        async def close(self) -> None:
            pass

    def mock_engine_factory(ep: dict[str, Any]) -> MockEngineClient:
        return MockEngineClient()

    # Run the task
    await _node_health(
        job_id="test-job-2",
        tenant=tenant,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
        engine_factory=mock_engine_factory,
    )

    # Verify endpoint was updated
    rowset = await real_dal(
        (real_dal.c2c_endpoints.id == endpoint_id)
        & (real_dal.c2c_endpoints.tenant == tenant)
    ).select()
    endpoint = rowset.first()
    assert endpoint is not None
    assert endpoint.health_status == "unhealthy"
    assert endpoint.last_health_check is not None


@pytest.mark.asyncio
async def test_node_health_failing_endpoint_continues(real_dal: AsyncDB) -> None:
    """node_health: one failing endpoint doesn't stop sweep, others still updated."""
    from hub_api.modules.perftest_c2c.worker.tasks import _node_health

    tenant = "test-tenant"

    # Create two endpoints
    for i in range(1, 3):
        await real_dal.c2c_endpoints.async_insert(
            id=f"ep-{i}",
            tenant=tenant,
            region="us-west-2",
            name=f"Test Endpoint {i}",
            engine_url=f"http://localhost:900{i}",
            target=f"192.168.1.{i}",
            api_key_hash="hash123",
            enabled=True,
            visibility="private",
            provider=None,
            health_status="unknown",
            last_health_check=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    # Mock engine factory: first raises, second returns healthy
    call_count = [0]

    class MockEngineClient:
        def __init__(self, endpoint_id: str):
            self.endpoint_id = endpoint_id

        async def health(self) -> bool:
            call_count[0] += 1
            if "ep-1" in self.endpoint_id:
                raise EngineError("Connection refused", status_code=500)
            return True

        async def close(self) -> None:
            pass

    def mock_engine_factory(ep: dict[str, Any]) -> MockEngineClient:
        return MockEngineClient(ep["id"])

    # Run the task (should not raise even if one fails)
    await _node_health(
        job_id="test-job-3",
        tenant=tenant,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
        engine_factory=mock_engine_factory,
    )

    # Verify first endpoint is marked unhealthy (caught exception)
    rowset = await real_dal(
        (real_dal.c2c_endpoints.id == "ep-1")
        & (real_dal.c2c_endpoints.tenant == tenant)
    ).select()
    endpoint1 = rowset.first()
    assert endpoint1 is not None
    assert endpoint1.health_status == "unhealthy"

    # Verify second endpoint is marked healthy
    rowset = await real_dal(
        (real_dal.c2c_endpoints.id == "ep-2")
        & (real_dal.c2c_endpoints.tenant == tenant)
    ).select()
    endpoint2 = rowset.first()
    assert endpoint2 is not None
    assert endpoint2.health_status == "healthy"


@pytest.mark.asyncio
async def test_node_health_foreign_tenant_endpoints_untouched(real_dal: AsyncDB) -> None:
    """node_health: foreign-tenant endpoints are not updated."""
    from hub_api.modules.perftest_c2c.worker.tasks import _node_health

    tenant_a = "tenant-a"
    tenant_b = "tenant-b"

    # Create endpoints for both tenants
    await real_dal.c2c_endpoints.async_insert(
        id="ep-a",
        tenant=tenant_a,
        region="us-west-2",
        name="Endpoint A",
        engine_url="http://localhost:9001",
        target="192.168.1.1",
        api_key_hash="hash123",
        enabled=True,
        visibility="private",
        provider=None,
        health_status="unknown",
        last_health_check=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    await real_dal.c2c_endpoints.async_insert(
        id="ep-b",
        tenant=tenant_b,
        region="us-west-2",
        name="Endpoint B",
        engine_url="http://localhost:9002",
        target="192.168.1.2",
        api_key_hash="hash456",
        enabled=True,
        visibility="private",
        provider=None,
        health_status="healthy",
        last_health_check=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Mock engine factory
    class MockEngineClient:
        async def health(self) -> bool:
            return True

        async def close(self) -> None:
            pass

    def mock_engine_factory(ep: dict[str, Any]) -> MockEngineClient:
        return MockEngineClient()

    # Run node_health for tenant_a only
    await _node_health(
        job_id="test-job-4",
        tenant=tenant_a,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
        engine_factory=mock_engine_factory,
    )

    # Verify tenant_a endpoint was updated
    rowset = await real_dal(
        (real_dal.c2c_endpoints.id == "ep-a")
        & (real_dal.c2c_endpoints.tenant == tenant_a)
    ).select()
    endpoint_a = rowset.first()
    assert endpoint_a is not None
    assert endpoint_a.health_status == "healthy"

    # Verify tenant_b endpoint was NOT updated (still has old status)
    rowset = await real_dal(
        (real_dal.c2c_endpoints.id == "ep-b")
        & (real_dal.c2c_endpoints.tenant == tenant_b)
    ).select()
    endpoint_b = rowset.first()
    assert endpoint_b is not None
    assert endpoint_b.health_status == "healthy"  # Unchanged
