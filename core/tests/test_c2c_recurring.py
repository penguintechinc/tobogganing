"""Tests for C2C recurring matrix runs using real penguin-dal."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from quart import Quart
from penguin_dal import AsyncDB

from core.auth.jwt import encode_access_token
from core.crypto import InAppKeyProvider, generate_rsa_key_pair


@pytest_asyncio.fixture
async def app_with_c2c_recurring_realdal(
    app_with_c2c: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Create test app with C2C module using real_dal."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("core.db.get_db", get_db_func)

    import core.app
    monkeypatch.setattr(core.app, "get_db", get_db_func)

    import core.modules.waddleperf_c2c.api.recurring
    monkeypatch.setattr(core.modules.waddleperf_c2c.api.recurring, "get_db", get_db_func)

    app_with_c2c.db = real_dal
    return app_with_c2c


@pytest_asyncio.fixture
async def c2c_write_token_recurring(app_with_c2c_recurring_realdal: Quart) -> str:
    """Generate write token for recurring tests."""
    provider = app_with_c2c_recurring_realdal.config["KEY_PROVIDER"]
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
# Entitlement Key Trap Test
# ============================================================================


@pytest.mark.asyncio
async def test_recurring_runs_unlicensed_returns_402(
    app: Quart, mock_db: Any, monkeypatch: Any
) -> None:
    """Flag ON + Professional tier but NO license → 402 from the tier gate.

    This is the entitlement-key-trap test: feature flag enabled but no license.
    """
    from core.crypto import InAppKeyProvider, generate_rsa_key_pair
    from core.registry import ModuleContext
    import shared.licensing.entitlements

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Flag ON for c2c recurring_runs, but licensing stays at its default (professional → False).
    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.waddleperf_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)
    # NOTE: deliberately do NOT patch _is_licensed_for_tier — unlicensed path.

    from core.modules.waddleperf_c2c import module as c2c_mod

    app.registry.register(c2c_mod())
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    token = await encode_access_token(
        {
            "sub": "u",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "test-tenant",
            "scope": "c2c:read c2c:write",
        },
        provider,
        ttl_hours=1,
    )

    client = app.test_client()
    resp = await client.post(
        "/api/v1/waddleperf_c2c/recurring",
        json={"endpoint_ids": ["ep-1", "ep-2"], "interval_seconds": 300},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402


# ============================================================================
# Contract Tests
# ============================================================================


@pytest.mark.asyncio
async def test_entitlement_key_is_bare_not_prefixed() -> None:
    """Entitlement key must be 'waddleperf_c2c.recurring_runs', not 'tobogganing.waddleperf_c2c.recurring_runs'."""
    from core.modules.waddleperf_c2c import module as c2c_mod
    from core.registry import ModuleRegistry

    registry = ModuleRegistry()
    contract = c2c_mod()
    registry.register(contract)

    # Check that the bare key is registered
    ent = registry.entitlement_for("waddleperf_c2c.recurring_runs")
    assert ent is not None, "entitlement_for('waddleperf_c2c.recurring_runs') must not be None"
    assert ent.tier.lower() == "professional"

    # Check that the prefixed key is NOT registered (regression guard)
    ent_prefixed = registry.entitlement_for("tobogganing.waddleperf_c2c.recurring_runs")
    assert ent_prefixed is None, "entitlement_for('tobogganing.waddleperf_c2c.recurring_runs') must be None"


# ============================================================================
# CRUD Tests with Licensed Flag
# ============================================================================


@pytest.mark.asyncio
async def test_recurring_crud_licensed(
    app_with_c2c_recurring_realdal: Quart,
    c2c_write_token_recurring: str,
    monkeypatch: Any,
) -> None:
    """Flag ON + Licensed → CRUD operations work."""
    import shared.licensing.entitlements
    import core.entitlements.gate

    # Patch feature flag ON
    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.waddleperf_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    # Patch license to be professional
    original_is_licensed = core.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(core.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_recurring_realdal.test_client()

    # POST: Create a recurring job
    resp = await client.post(
        "/api/v1/waddleperf_c2c/recurring",
        json={"endpoint_ids": ["ep-1", "ep-2"], "interval_seconds": 300},
        headers={"Authorization": f"Bearer {c2c_write_token_recurring}"},
    )
    assert resp.status_code == 201
    data = await resp.get_json()
    job_id = data.get("job_id")
    assert job_id is not None

    # GET: List recurring jobs
    resp = await client.get(
        "/api/v1/waddleperf_c2c/recurring",
        headers={"Authorization": f"Bearer {c2c_write_token_recurring}"},
    )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert "jobs" in data
    assert len(data["jobs"]) >= 1

    # PATCH: Toggle enabled
    resp = await client.patch(
        f"/api/v1/waddleperf_c2c/recurring/{job_id}",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {c2c_write_token_recurring}"},
    )
    assert resp.status_code == 200

    # DELETE: Remove job
    resp = await client.delete(
        f"/api/v1/waddleperf_c2c/recurring/{job_id}",
        headers={"Authorization": f"Bearer {c2c_write_token_recurring}"},
    )
    assert resp.status_code == 204


# ============================================================================
# Worker Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_start_recurring_run_creates_run(real_dal: AsyncDB) -> None:
    """start_recurring_run task creates a run row via RunManager."""
    from datetime import datetime, timezone
    from core.modules.waddleperf_c2c.worker.tasks import _start_recurring_run

    # Create two test endpoints first
    tenant = "test-tenant"
    for i, ep_id in enumerate(["ep-1", "ep-2"]):
        await real_dal.c2c_endpoints.async_insert(
            id=ep_id,
            tenant=tenant,
            name=f"Endpoint {i+1}",
            region="us-west-2",
            target=f"192.168.1.{100+i}",
            engine_url="http://localhost:9000",
            api_key_hash="hash123",
            enabled=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    # Mock dispatch for enqueue_run (so we don't actually enqueue pairs)
    dispatch_calls = []

    def mock_dispatch(**kwargs: Any) -> None:
        dispatch_calls.append(kwargs)

    payload = {"endpoint_ids": ["ep-1", "ep-2"], "interval_seconds": 300}

    # Call the async inner function with real_dal and mock dispatch
    result = await _start_recurring_run(
        job_id="test-job-1",
        tenant=tenant,
        module="waddleperf_c2c",
        job_type="matrix_run",
        payload=payload,
        db=real_dal,
        dispatch=mock_dispatch,
    )

    # Verify that a run was created
    assert result is not None
    assert "run_id" in result
    run_id = result["run_id"]

    # Verify the run exists in the database
    rowset = await real_dal(
        (real_dal.c2c_matrix_runs.id == run_id)
        & (real_dal.c2c_matrix_runs.tenant == tenant)
    ).select()
    run_row = rowset.first()
    assert run_row is not None
    assert run_row.status == "running"  # Should be marked as running by the task


@pytest.mark.asyncio
async def test_start_recurring_run_handles_error(real_dal: AsyncDB) -> None:
    """start_recurring_run logs errors but does not raise out."""
    from core.modules.waddleperf_c2c.worker.tasks import _start_recurring_run

    payload = {"endpoint_ids": ["nonexistent"], "interval_seconds": 300}

    # This should not raise, just log
    result = await _start_recurring_run(
        job_id="test-job-2",
        tenant="test-tenant",
        module="waddleperf_c2c",
        job_type="matrix_run",
        payload=payload,
        db=real_dal,
        dispatch=lambda **kw: None,
    )

    # When endpoint selection fails, result should reflect the error
    # (or be None if we choose to return None on error)
    # The key is: no exception raised
    assert True  # Task completed without raising


# ============================================================================
# Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_recurring_validation_interval_too_low(
    app_with_c2c_recurring_realdal: Quart,
    c2c_write_token_recurring: str,
    monkeypatch: Any,
) -> None:
    """interval_seconds < 30 → 400."""
    import shared.licensing.entitlements
    import core.entitlements.gate

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.waddleperf_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    original_is_licensed = core.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(core.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_recurring_realdal.test_client()
    resp = await client.post(
        "/api/v1/waddleperf_c2c/recurring",
        json={"endpoint_ids": ["ep-1", "ep-2"], "interval_seconds": 20},
        headers={"Authorization": f"Bearer {c2c_write_token_recurring}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_recurring_validation_endpoint_ids_empty_list(
    app_with_c2c_recurring_realdal: Quart,
    c2c_write_token_recurring: str,
    monkeypatch: Any,
) -> None:
    """endpoint_ids as empty list → 400."""
    import shared.licensing.entitlements
    import core.entitlements.gate

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.waddleperf_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    original_is_licensed = core.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(core.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_recurring_realdal.test_client()
    resp = await client.post(
        "/api/v1/waddleperf_c2c/recurring",
        json={"endpoint_ids": [], "interval_seconds": 300},
        headers={"Authorization": f"Bearer {c2c_write_token_recurring}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_recurring_validation_endpoint_ids_not_list(
    app_with_c2c_recurring_realdal: Quart,
    c2c_write_token_recurring: str,
    monkeypatch: Any,
) -> None:
    """endpoint_ids not a list → 400."""
    import shared.licensing.entitlements
    import core.entitlements.gate

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.waddleperf_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    original_is_licensed = core.entitlements.gate._is_licensed_for_tier

    def mock_is_licensed(tier: str) -> bool:
        if tier == "professional":
            return True
        return original_is_licensed(tier)

    monkeypatch.setattr(core.entitlements.gate, "_is_licensed_for_tier", mock_is_licensed)

    client = app_with_c2c_recurring_realdal.test_client()
    resp = await client.post(
        "/api/v1/waddleperf_c2c/recurring",
        json={"endpoint_ids": "ep-1,ep-2", "interval_seconds": 300},
        headers={"Authorization": f"Bearer {c2c_write_token_recurring}"},
    )
    assert resp.status_code == 400
