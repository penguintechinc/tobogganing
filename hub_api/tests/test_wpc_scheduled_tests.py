"""Tests for WaddlePerf Cluster scheduled server tests API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from quart import Quart


@pytest_asyncio.fixture
async def app_with_wpc_st(
    real_dal: Any, monkeypatch: Any
) -> Quart:
    """Create a test app with WaddlePerf Cluster module and real async database.

    This fixture patches get_db to return the real AsyncDB from real_dal,
    allowing end-to-end tests against a migrated SQLite database.

    Args:
        real_dal: Real AsyncDB fixture from conftest.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        Quart app with WaddlePerf Cluster module and real database.
    """
    from hub_api.auth.jwt import encode_access_token
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext
    from hub_api.app import create_app
    import hub_api.db

    # Create a fresh app without mocking db.init_dal
    test_app = create_app()
    test_app.config["TESTING"] = True

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    test_app.config["KEY_PROVIDER"] = provider

    # Patch get_db to return the real AsyncDB
    monkeypatch.setattr(hub_api.db, "get_db", lambda: real_dal)
    import hub_api.app as app_module
    monkeypatch.setattr(app_module, "get_db", lambda: real_dal)

    # Patch the tests API module to use real DAL too
    import hub_api.modules.perftest_cluster.api.tests as tests_api
    monkeypatch.setattr(tests_api, "get_db", lambda: real_dal)

    # Patch scheduled_tests API module
    import hub_api.modules.perftest_cluster.api.scheduled_tests as st_api
    monkeypatch.setattr(st_api, "get_db", lambda: real_dal)

    # Enable all wpc feature flags for tests (bypass flag server)
    import shared.licensing.entitlements
    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith(
            "tobogganing.perftest_cluster."
        ) or flag_key.startswith("tobogganing.perftest_client."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    # Register WaddlePerf Cluster module via registry
    from hub_api.modules.perftest_cluster import module as wpc_module
    from hub_api.modules.perftest_client import module as wpcl_module

    wpc_contract = wpc_module()
    wpcl_contract = wpcl_module()
    test_app.registry.register(wpc_contract)
    test_app.registry.register(wpcl_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=test_app.config_obj, db=real_dal, key_provider=provider)
    test_app.registry.apply_to(test_app, ctx)

    return test_app


@pytest_asyncio.fixture
async def st_write_token(app_with_wpc_st: Quart) -> str:
    """Generate a JWT token with full write scopes for real-DAL tests.

    Args:
        app_with_wpc_st: App with real database and key provider.

    Returns:
        Encoded JWT token with write scopes.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_wpc_st.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def st_read_token(app_with_wpc_st: Quart) -> str:
    """Generate a read-only JWT token.

    Args:
        app_with_wpc_st: App with real database.

    Returns:
        JWT token with read-only scope.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_wpc_st.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user-ro",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:read",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_scheduled_tests_flag_off(
    app_with_wpc: Quart,
    monkeypatch: Any,
    wpc_write_token: str,
) -> None:
    """Flag off → 402 on POST to create scheduled test.

    Args:
        app_with_wpc: App fixture.
        monkeypatch: Pytest monkeypatch.
        wpc_write_token: Write token.
    """
    import shared.licensing.entitlements

    # Mock flag to return False for scheduled_tests
    def mock_flag_off(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key == "tobogganing.perftest_cluster.scheduled_tests":
            return False
        return True

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_off)

    async with app_with_wpc.test_client() as client:
        response = await client.post(
            "/api/v1/perftest_cluster/scheduled-tests",
            json={
                "device_id": "dev1",
                "test_type": "http",
                "target": "https://example.com",
                "interval_seconds": 60,
            },
            headers={"Authorization": f"Bearer {wpc_write_token}"},
        )
        assert response.status_code == 402


@pytest.mark.asyncio
async def test_scheduled_tests_crud_round_trip(
    app_with_wpc_st: Quart,
    st_write_token: str,
    st_read_token: str,
) -> None:
    """Flag on → CRUD round-trip works.

    Args:
        app_with_wpc_st: App with real database.
        st_write_token: Write token.
        st_read_token: Read-only token.
    """
    async with app_with_wpc_st.test_client() as client:
        # POST: Create scheduled test
        response = await client.post(
            "/api/v1/perftest_cluster/scheduled-tests",
            json={
                "device_id": "dev-st-1",
                "test_type": "http",
                "target": "https://example.com/api",
                "interval_seconds": 60,
            },
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["device_id"] == "dev-st-1"
        assert data["test_type"] == "http"
        assert data["target"] == "https://example.com/api"
        assert data["interval_seconds"] == 60
        assert data["enabled"] is True
        job_id = data["id"]

        # GET: List scheduled tests
        response = await client.get(
            "/api/v1/perftest_cluster/scheduled-tests",
            headers={"Authorization": f"Bearer {st_read_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        jobs = data["jobs"]
        assert len(jobs) >= 1
        found = next((j for j in jobs if j["id"] == job_id), None)
        assert found is not None
        assert found["device_id"] == "dev-st-1"

        # PATCH: Disable job
        response = await client.patch(
            f"/api/v1/perftest_cluster/scheduled-tests/{job_id}",
            json={"enabled": False},
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["enabled"] is False

        # PATCH: Re-enable job
        response = await client.patch(
            f"/api/v1/perftest_cluster/scheduled-tests/{job_id}",
            json={"enabled": True},
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["enabled"] is True

        # DELETE: Remove job
        response = await client.delete(
            f"/api/v1/perftest_cluster/scheduled-tests/{job_id}",
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 204

        # GET: Verify job is gone
        response = await client.get(
            "/api/v1/perftest_cluster/scheduled-tests",
            headers={"Authorization": f"Bearer {st_read_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        jobs = data["jobs"]
        found = next((j for j in jobs if j["id"] == job_id), None)
        assert found is None


@pytest.mark.asyncio
async def test_scheduled_tests_input_validation(
    app_with_wpc_st: Quart,
    st_write_token: str,
) -> None:
    """Input validation: non-empty strings, interval >= 30.

    Args:
        app_with_wpc_st: App with real database.
        st_write_token: Write token.
    """
    async with app_with_wpc_st.test_client() as client:
        # Missing required field
        response = await client.post(
            "/api/v1/perftest_cluster/scheduled-tests",
            json={
                "device_id": "dev1",
                "test_type": "http",
                # missing target and interval_seconds
            },
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 400

        # Empty device_id
        response = await client.post(
            "/api/v1/perftest_cluster/scheduled-tests",
            json={
                "device_id": "",
                "test_type": "http",
                "target": "https://example.com",
                "interval_seconds": 60,
            },
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 400

        # interval_seconds < 30
        response = await client.post(
            "/api/v1/perftest_cluster/scheduled-tests",
            json={
                "device_id": "dev1",
                "test_type": "http",
                "target": "https://example.com",
                "interval_seconds": 15,
            },
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 400

        # interval_seconds as string (should fail type check)
        response = await client.post(
            "/api/v1/perftest_cluster/scheduled-tests",
            json={
                "device_id": "dev1",
                "test_type": "http",
                "target": "https://example.com",
                "interval_seconds": "60",
            },
            headers={"Authorization": f"Bearer {st_write_token}"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_scheduled_tests_cross_tenant_isolation(
    app_with_wpc_st: Quart,
    monkeypatch: Any,
) -> None:
    """Cross-tenant DELETE → 404.

    Args:
        app_with_wpc_st: App with real database.
        monkeypatch: Pytest monkeypatch.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_wpc_st.config["KEY_PROVIDER"]

    # Create token for tenant-1
    claims_t1 = {
        "sub": "user-t1",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant-1",
        "scope": "*:*",
    }
    token_t1 = await encode_access_token(claims_t1, provider, ttl_hours=1)

    # Create token for tenant-2
    claims_t2 = {
        "sub": "user-t2",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant-2",
        "scope": "*:*",
    }
    token_t2 = await encode_access_token(claims_t2, provider, ttl_hours=1)

    async with app_with_wpc_st.test_client() as client:
        # Tenant 1: Create job
        response = await client.post(
            "/api/v1/perftest_cluster/scheduled-tests",
            json={
                "device_id": "dev-t1",
                "test_type": "http",
                "target": "https://example.com",
                "interval_seconds": 60,
            },
            headers={"Authorization": f"Bearer {token_t1}"},
        )
        assert response.status_code == 201
        data = await response.get_json()
        job_id = data["id"]

        # Tenant 2: Try to delete tenant 1's job
        response = await client.delete(
            f"/api/v1/perftest_cluster/scheduled-tests/{job_id}",
            headers={"Authorization": f"Bearer {token_t2}"},
        )
        assert response.status_code == 404

        # Tenant 1: Verify job still exists
        response = await client.get(
            "/api/v1/perftest_cluster/scheduled-tests",
            headers={"Authorization": f"Bearer {token_t1}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        jobs = data["jobs"]
        found = next((j for j in jobs if j["id"] == job_id), None)
        assert found is not None


@pytest.mark.asyncio
async def test_scheduled_tests_job_due_visibility(
    real_dal: Any,
) -> None:
    """Created job visible to JobManager.due_jobs after interval.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)

    now = datetime.now(timezone.utc)
    past = now - timedelta(seconds=60)  # In the past, so it's due

    # Create a job with next_run_at in the past
    job = await manager.create_job(
        tenant="test-tenant-job",
        module="perftest_cluster",
        job_type="server_test",
        payload={"device_id": "dev1", "test_type": "http", "target": "example.com"},
        interval_seconds=30,
        enabled=True,
    )

    # Manually set next_run_at to the past to make it due
    await real_dal(
        (real_dal.scheduled_jobs.id == job["id"]) &
        (real_dal.scheduled_jobs.tenant == "test-tenant-job")
    ).update(next_run_at=past)

    # Query due jobs
    due = await manager.due_jobs(now)

    # Find our job in due jobs
    found = next(
        (j for j in due
         if j["id"] == job["id"] and j["tenant"] == "test-tenant-job"),
        None,
    )
    assert found is not None
    assert found["enabled"] is True
    assert found["job_type"] == "server_test"


@pytest.mark.asyncio
async def test_run_server_test_task_stores_result(
    real_dal: Any,
) -> None:
    """run_server_test task with fake engine creates result row.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    from hub_api.modules.perftest_cluster.worker.tasks import _run_server_test_async
    from hub_api.modules.perftest_cluster.services.test_manager import TestManager
    from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager

    tenant = "test-tenant-task"

    # Create a device first
    dev_mgr = DeviceManager(real_dal, tenant)
    device_info = {
        "name": "test-device",
        "serial": "SN12345",
        "hostname": "testhost",
        "os": "Linux",
    }
    device, api_key = await dev_mgr.register_device(device_info)

    # Create a fake engine factory that returns a mocked engine
    def fake_engine_factory(device_row: dict[str, Any]):
        mock_engine = MagicMock()
        async def mock_run_test(test_type: str, target: str):
            return {
                "latency_ms": 42.5,
                "throughput": 100.0,
                "output": "Test completed successfully",
            }
        mock_engine.run_test = mock_run_test
        return mock_engine

    # Execute the task
    await _run_server_test_async(
        job_id="test-job-1",
        tenant=tenant,
        module="perftest_cluster",
        job_type="server_test",
        payload={
            "device_id": device.id,
            "test_type": "http",
            "target": "https://example.com",
        },
        db=real_dal,
        engine_factory=fake_engine_factory,
    )

    # Verify result was stored
    test_mgr = TestManager(real_dal, tenant)
    results = await test_mgr.list_results(device_id=device.id)
    assert len(results) >= 1
    result = results[0]
    assert result.device_id == device.id
    assert result.test_type == "http"
    assert result.target == "https://example.com"
    assert result.status == "completed"
    assert result.latency_ms == 42.5
    assert result.throughput == 100.0


@pytest.mark.asyncio
async def test_run_server_test_task_engine_error(
    real_dal: Any,
) -> None:
    """run_server_test with engine error records failed result.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    from hub_api.modules.perftest_cluster.worker.tasks import _run_server_test_async
    from hub_api.modules.perftest_cluster.services.test_manager import TestManager
    from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
    from hub_api.modules.perftest_cluster.services.engine_client import EngineError

    tenant = "test-tenant-error"

    # Create a device
    dev_mgr = DeviceManager(real_dal, tenant)
    device_info = {
        "name": "test-device-err",
        "serial": "SN99999",
        "hostname": "errhost",
        "os": "Linux",
    }
    device, api_key = await dev_mgr.register_device(device_info)

    # Create a fake engine factory that raises an error
    def fake_engine_factory(device_row: dict[str, Any]):
        mock_engine = MagicMock()
        async def mock_run_test_error(test_type: str, target: str):
            raise EngineError("Connection refused", status_code=500)
        mock_engine.run_test = mock_run_test_error
        return mock_engine

    # Execute the task
    await _run_server_test_async(
        job_id="test-job-error",
        tenant=tenant,
        module="perftest_cluster",
        job_type="server_test",
        payload={
            "device_id": device.id,
            "test_type": "http",
            "target": "https://example.com",
        },
        db=real_dal,
        engine_factory=fake_engine_factory,
    )

    # Verify failed result was stored
    test_mgr = TestManager(real_dal, tenant)
    results = await test_mgr.list_results(device_id=device.id)
    assert len(results) >= 1
    result = results[0]
    assert result.status == "failed"
    assert "Engine error" in result.test_output
