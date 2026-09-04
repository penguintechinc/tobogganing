"""Real-DAL tests for netsvcs analytics endpoints' success-path data logic.

tests/test_netsvcs_analytics.py only ever verifies auth/scope/feature-flag
gating against a mock DB that never returns real rows, so the actual
aggregation logic (query totals, percentile calc, per-server stats, tenant
summary counts) in modules/netsvcs/api/analytics.py was never exercised.
This file drives the real blueprint handlers against a migrated real_dal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    """Patch get_db() to real_dal wherever the analytics blueprint imports it."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app

    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.netsvcs.api.analytics

    monkeypatch.setattr(hub_api.modules.netsvcs.api.analytics, "get_db", get_db_func)

    app_with_netsvcs.db = real_dal
    return app_with_netsvcs


@pytest_asyncio.fixture
async def tenant_token(app_with_netsvcs_realdal: Quart) -> str:
    """JWT for a fresh tenant with dns:read scope."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-analytics",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": f"tenant-analytics-{uuid4()}",
        "scope": "dns:read",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


def _tenant_from_token(token: str, provider: Any) -> str:
    import jwt as pyjwt

    decoded = pyjwt.decode(token, options={"verify_signature": False})
    return decoded["tenant"]


async def _seed_server_and_metrics(real_dal: AsyncDB, tenant_id: str) -> str:
    """Seed one DNS server plus a metrics row within the last hour; return server_id."""
    now = datetime.now(timezone.utc)
    server_id = str(uuid4())
    await real_dal.dns_servers.async_insert(
        id=server_id,
        tenant=tenant_id,
        name="resolver-1",
        status="online",
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_server_metrics.async_insert(
        id=str(uuid4()),
        tenant=tenant_id,
        server_id=server_id,
        timestamp=now,
        queries_total=1000,
        cache_hits=800,
        errors=5,
        avg_response_ms=12.5,
        created_at=now,
    )
    return server_id


@pytest.mark.asyncio
async def test_queries_analytics_invalid_hours_defaults_to_24(
    app_with_netsvcs_realdal: Quart, tenant_token: str, real_dal: AsyncDB
) -> None:
    """A non-numeric hours param falls back to 24 and still returns 200."""
    import jwt as pyjwt

    tenant_id = pyjwt.decode(tenant_token, options={"verify_signature": False})["tenant"]
    await _seed_server_and_metrics(real_dal, tenant_id)

    client = app_with_netsvcs_realdal.test_client()
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
        response = await client.get(
            "/api/v1/netsvcs/analytics/queries?hours=notanumber",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["total_queries"] == 1000
    assert data["cache_hit_rate"] == 80.0


@pytest.mark.asyncio
async def test_performance_analytics_computes_percentiles(
    app_with_netsvcs_realdal: Quart, tenant_token: str, real_dal: AsyncDB
) -> None:
    """performance endpoint computes avg/min/max/percentiles from real metrics rows."""
    import jwt as pyjwt

    tenant_id = pyjwt.decode(tenant_token, options={"verify_signature": False})["tenant"]
    await _seed_server_and_metrics(real_dal, tenant_id)

    client = app_with_netsvcs_realdal.test_client()
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
        response = await client.get(
            "/api/v1/netsvcs/analytics/performance?hours=notanumber",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )

    assert response.status_code == 200
    data = await response.get_json()
    metric_names = {m["metric"] for m in data["metrics"]}
    assert "avg_response_ms" in metric_names
    assert "p95_response_ms" in metric_names


@pytest.mark.asyncio
async def test_performance_analytics_no_data_returns_zeros(
    app_with_netsvcs_realdal: Quart, tenant_token: str
) -> None:
    """performance endpoint returns all-zero metrics when there's no data yet."""
    client = app_with_netsvcs_realdal.test_client()
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
        response = await client.get(
            "/api/v1/netsvcs/analytics/performance",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )

    assert response.status_code == 200
    data = await response.get_json()
    assert all(m["value"] == 0.0 for m in data["metrics"])


@pytest.mark.asyncio
async def test_servers_analytics_aggregates_per_server(
    app_with_netsvcs_realdal: Quart, tenant_token: str, real_dal: AsyncDB
) -> None:
    """servers endpoint returns per-server aggregated stats from real rows."""
    import jwt as pyjwt

    tenant_id = pyjwt.decode(tenant_token, options={"verify_signature": False})["tenant"]
    server_id = await _seed_server_and_metrics(real_dal, tenant_id)

    client = app_with_netsvcs_realdal.test_client()
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
        response = await client.get(
            "/api/v1/netsvcs/analytics/servers?hours=bogus",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )

    assert response.status_code == 200
    data = await response.get_json()
    assert len(data["servers"]) == 1
    assert data["servers"][0]["server_id"] == server_id
    assert data["servers"][0]["queries"] == 1000


@pytest.mark.asyncio
async def test_summary_analytics_counts_zones_records_servers_queries(
    app_with_netsvcs_realdal: Quart, tenant_token: str, real_dal: AsyncDB
) -> None:
    """summary endpoint returns zone/record/server/query counts for this tenant only."""
    import jwt as pyjwt

    tenant_id = pyjwt.decode(tenant_token, options={"verify_signature": False})["tenant"]
    now = datetime.now(timezone.utc)

    zone_id = str(uuid4())
    await real_dal.dns_zones.async_insert(
        id=zone_id,
        tenant=tenant_id,
        name="summary.com",
        visibility="public",
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_records.async_insert(
        id=str(uuid4()),
        tenant=tenant_id,
        zone_id=zone_id,
        name="www",
        type="A",
        value="1.2.3.4",
        ttl=300,
        created_at=now,
        updated_at=now,
    )
    await _seed_server_and_metrics(real_dal, tenant_id)

    client = app_with_netsvcs_realdal.test_client()
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
        response = await client.get(
            "/api/v1/netsvcs/analytics/summary",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )

    assert response.status_code == 200
    data = await response.get_json()
    metrics = {m["key"]: m["value"] for m in data["metrics"]}
    assert metrics["zones"] == 1
    assert metrics["records"] == 1
    assert metrics["servers"] == 1
    assert metrics["queries_24h"] == 1000
