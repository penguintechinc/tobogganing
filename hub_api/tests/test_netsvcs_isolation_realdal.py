"""Real-DB tenant-isolation tests for netsvcs module using real_dal fixture.

REGRESSION TEST for analytics time-window filter bug:
The old comma-syntax query db(tenant==t, timestamp>=cutoff) silently dropped
the timestamp condition, causing analytics to return all-time data regardless
of the ?hours query parameter. The new & syntax fixes this.
This test FAILS on old comma-syntax, PASSES with the fix.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

from hub_api.modules.netsvcs.managers.zone_manager import ZoneManager
from hub_api.modules.netsvcs.managers.server_manager import ServerManager
from hub_api.modules.netsvcs.managers.config_service import ConfigService
from unittest.mock import MagicMock, patch


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with netsvcs module registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with netsvcs module and auth configured.
    """
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = "default"

    # Register netsvcs module via registry
    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def app_with_netsvcs_realdal(
    app_with_netsvcs: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Create test app with netsvcs module using real_dal fixture.

    Reuses app_with_netsvcs which has auth + module wiring already set up,
    but patches get_db to return real_dal instead of mock_db.
    """
    # Patch get_db everywhere it's imported
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app
    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.netsvcs.api.dns_servers
    monkeypatch.setattr(hub_api.modules.netsvcs.api.dns_servers, "get_db", get_db_func)

    import hub_api.modules.netsvcs.api.analytics
    monkeypatch.setattr(hub_api.modules.netsvcs.api.analytics, "get_db", get_db_func)

    import hub_api.modules.netsvcs.api.zones
    monkeypatch.setattr(hub_api.modules.netsvcs.api.zones, "get_db", get_db_func)

    app_with_netsvcs.db = real_dal
    return app_with_netsvcs


@pytest_asyncio.fixture
async def tenant_a_token_realdal(app_with_netsvcs_realdal: Quart) -> str:
    """Generate JWT token for tenant A for real_dal app.

    Args:
        app_with_netsvcs_realdal: Test app with netsvcs module and real_dal.

    Returns:
        Valid JWT token for tenant A.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs_realdal.config["KEY_PROVIDER"]

    claims = {
        "sub": "user-a",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-analytics-test",
        "scope": "dns:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def tenant_b_token_realdal(app_with_netsvcs_realdal: Quart) -> str:
    """Generate JWT token for tenant B for real_dal app.

    Args:
        app_with_netsvcs_realdal: Test app with netsvcs module and real_dal.

    Returns:
        Valid JWT token for tenant B.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs_realdal.config["KEY_PROVIDER"]

    claims = {
        "sub": "user-b",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-b",
        "scope": "dns:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_zones_list_cross_tenant_isolation(real_dal) -> None:
    """Test ZoneManager.list_zones() returns ONLY tenant-a zones, excludes tenant-b."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"

    # Seed two zones in tenant-a
    zone_a1_id = str(uuid4())
    zone_a2_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await real_dal.dns_zones.async_insert(
        id=zone_a1_id,
        tenant=tenant_a,
        name="example-a1.com",
        visibility="public",
        description="Zone A1",
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_zones.async_insert(
        id=zone_a2_id,
        tenant=tenant_a,
        name="example-a2.com",
        visibility="public",
        description="Zone A2",
        created_at=now,
        updated_at=now,
    )

    # Seed one zone in tenant-b
    zone_b1_id = str(uuid4())
    await real_dal.dns_zones.async_insert(
        id=zone_b1_id,
        tenant=tenant_b,
        name="example-b1.com",
        visibility="public",
        description="Zone B1",
        created_at=now,
        updated_at=now,
    )

    # List zones as tenant-a
    manager_a = ZoneManager(real_dal, tenant_a)
    zones_a = await manager_a.list_zones()

    # Verify tenant-a manager sees ONLY tenant-a zones
    assert len(zones_a) == 2
    zone_names_a = {z.name for z in zones_a}
    assert zone_names_a == {"example-a1.com", "example-a2.com"}
    assert all(z.tenant == tenant_a for z in zones_a)

    # List zones as tenant-b
    manager_b = ZoneManager(real_dal, tenant_b)
    zones_b = await manager_b.list_zones()

    # Verify tenant-b manager sees ONLY tenant-b zone
    assert len(zones_b) == 1
    assert zones_b[0].name == "example-b1.com"
    assert zones_b[0].tenant == tenant_b


@pytest.mark.asyncio
async def test_zones_get_cross_tenant_denied(real_dal) -> None:
    """Test ZoneManager.get_zone() returns None when accessing other tenant's zone."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"

    # Create a zone in tenant-a
    zone_a_id = str(uuid4())
    now = datetime.now(timezone.utc)
    await real_dal.dns_zones.async_insert(
        id=zone_a_id,
        tenant=tenant_a,
        name="protected.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )

    # Try to access it as tenant-b
    manager_b = ZoneManager(real_dal, tenant_b)
    zone = await manager_b.get_zone(zone_a_id)

    # Should return None (not found)
    assert zone is None


@pytest.mark.asyncio
async def test_zones_update_cross_tenant_denied(real_dal) -> None:
    """Test ZoneManager.update_zone() returns None when updating other tenant's zone."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"

    # Create a zone in tenant-a
    zone_a_id = str(uuid4())
    now = datetime.now(timezone.utc)
    await real_dal.dns_zones.async_insert(
        id=zone_a_id,
        tenant=tenant_a,
        name="protected.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )

    # Try to update it as tenant-b
    manager_b = ZoneManager(real_dal, tenant_b)
    result = await manager_b.update_zone(zone_a_id, name="modified.com")

    # Should return None (not found)
    assert result is None

    # Verify zone was NOT modified
    rowset = await real_dal(real_dal.dns_zones.id == zone_a_id).select()
    zone_row = rowset.first()
    assert zone_row.name == "protected.com"  # unchanged


@pytest.mark.asyncio
async def test_zones_delete_cross_tenant_denied(real_dal) -> None:
    """Test ZoneManager.delete_zone() returns False when deleting other tenant's zone."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"

    # Create a zone in tenant-a
    zone_a_id = str(uuid4())
    now = datetime.now(timezone.utc)
    await real_dal.dns_zones.async_insert(
        id=zone_a_id,
        tenant=tenant_a,
        name="protected.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )

    # Try to delete it as tenant-b
    manager_b = ZoneManager(real_dal, tenant_b)
    result = await manager_b.delete_zone(zone_a_id)

    # Should return False (not found)
    assert result is False

    # Verify zone was NOT deleted
    rowset = await real_dal(real_dal.dns_zones.id == zone_a_id).select()
    zone_row = rowset.first()
    assert zone_row is not None  # still exists


@pytest.mark.asyncio
async def test_records_list_cross_tenant_isolated(real_dal) -> None:
    """Test DNSRecordRecord.list_records() returns ONLY tenant's records, excludes other tenant's."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Create a zone in tenant-a
    zone_a_id = str(uuid4())
    await real_dal.dns_zones.async_insert(
        id=zone_a_id,
        tenant=tenant_a,
        name="example-a.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )

    # Create records in tenant-a's zone
    rec_a1_id = str(uuid4())
    rec_a2_id = str(uuid4())
    await real_dal.dns_records.async_insert(
        id=rec_a1_id,
        zone_id=zone_a_id,
        tenant=tenant_a,
        name="www",
        type="A",
        value="192.0.2.1",
        ttl=300,
        priority=None,
        weight=None,
        port=None,
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_records.async_insert(
        id=rec_a2_id,
        zone_id=zone_a_id,
        tenant=tenant_a,
        name="mail",
        type="A",
        value="192.0.2.2",
        ttl=300,
        priority=None,
        weight=None,
        port=None,
        created_at=now,
        updated_at=now,
    )

    # Create a zone in tenant-b (different zone)
    zone_b_id = str(uuid4())
    await real_dal.dns_zones.async_insert(
        id=zone_b_id,
        tenant=tenant_b,
        name="example-b.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )

    # Create a record in tenant-b's zone
    rec_b1_id = str(uuid4())
    await real_dal.dns_records.async_insert(
        id=rec_b1_id,
        zone_id=zone_b_id,
        tenant=tenant_b,
        name="www",
        type="A",
        value="198.51.100.1",
        ttl=300,
        priority=None,
        weight=None,
        port=None,
        created_at=now,
        updated_at=now,
    )

    # List records as tenant-a
    manager_a = ZoneManager(real_dal, tenant_a)
    records_a = await manager_a.list_records(zone_a_id)

    # Verify tenant-a sees ONLY their records
    assert len(records_a) == 2
    record_names_a = {r.name for r in records_a}
    assert record_names_a == {"www", "mail"}
    assert all(r.tenant == tenant_a for r in records_a)

    # List records as tenant-b (from their zone)
    manager_b = ZoneManager(real_dal, tenant_b)
    records_b = await manager_b.list_records(zone_b_id)

    # Verify tenant-b sees ONLY their record
    assert len(records_b) == 1
    assert records_b[0].name == "www"
    assert records_b[0].tenant == tenant_b


@pytest.mark.asyncio
async def test_records_create_cross_tenant_denied(real_dal) -> None:
    """Test create_record() in tenant-a's zone via tenant-b manager → None (cross-tenant denial)."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Create zone in tenant-a
    zone_a_id = str(uuid4())
    await real_dal.dns_zones.async_insert(
        id=zone_a_id,
        tenant=tenant_a,
        name="protected.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )

    # Try to create record in tenant-a's zone as tenant-b
    manager_b = ZoneManager(real_dal, tenant_b)
    record = await manager_b.create_record(
        zone_id=zone_a_id,
        name="www",
        type="A",
        value="192.0.2.1",
        ttl=300,
    )

    # Should return None (zone not found from tenant-b's perspective)
    assert record is None

    # Verify no record was created
    rowset = await real_dal(
        (real_dal.dns_records.zone_id == zone_a_id)
        & (real_dal.dns_records.name == "www")
    ).select()
    assert rowset.first() is None


@pytest.mark.asyncio
async def test_servers_list_cross_tenant_isolated(real_dal) -> None:
    """Test ServerManager.get_all_servers() returns ONLY tenant's servers, excludes other tenant's."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Create servers in tenant-a
    server_a1_id = str(uuid4())
    server_a2_id = str(uuid4())
    await real_dal.dns_servers.async_insert(
        id=server_a1_id,
        tenant=tenant_a,
        name="resolver-a1",
        status="online",
        version="1.0",
        region="us-west",
        hostname="resolver-a1.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_servers.async_insert(
        id=server_a2_id,
        tenant=tenant_a,
        name="resolver-a2",
        status="online",
        version="1.0",
        region="eu-central",
        hostname="resolver-a2.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )

    # Create server in tenant-b
    server_b1_id = str(uuid4())
    await real_dal.dns_servers.async_insert(
        id=server_b1_id,
        tenant=tenant_b,
        name="resolver-b1",
        status="online",
        version="1.0",
        region="us-east",
        hostname="resolver-b1.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )

    # List servers as tenant-a
    manager_a = ServerManager(real_dal, tenant_a)
    servers_a = await manager_a.get_all_servers()

    # Verify tenant-a sees ONLY their servers
    assert len(servers_a) == 2
    server_names_a = {s.name for s in servers_a}
    assert server_names_a == {"resolver-a1", "resolver-a2"}
    assert all(s.tenant == tenant_a for s in servers_a)

    # List servers as tenant-b
    manager_b = ServerManager(real_dal, tenant_b)
    servers_b = await manager_b.get_all_servers()

    # Verify tenant-b sees ONLY their server
    assert len(servers_b) == 1
    assert servers_b[0].name == "resolver-b1"
    assert servers_b[0].tenant == tenant_b


@pytest.mark.asyncio
async def test_analytics_metrics_cross_tenant_isolated(real_dal) -> None:
    """Test ServerManager.get_metrics() returns ONLY tenant's metrics, excludes other tenant's."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Create servers in both tenants
    server_a_id = str(uuid4())
    server_b_id = str(uuid4())

    await real_dal.dns_servers.async_insert(
        id=server_a_id,
        tenant=tenant_a,
        name="resolver-a",
        status="online",
        version="1.0",
        region="us-west",
        hostname="resolver-a.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_servers.async_insert(
        id=server_b_id,
        tenant=tenant_b,
        name="resolver-b",
        status="online",
        version="1.0",
        region="us-east",
        hostname="resolver-b.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )

    # Insert metrics for both servers
    metric_a_id = str(uuid4())
    metric_b_id = str(uuid4())

    await real_dal.dns_server_metrics.async_insert(
        id=metric_a_id,
        server_id=server_a_id,
        tenant=tenant_a,
        timestamp=now,
        queries_total=1000,
        cache_hits=800,
        errors=5,
        avg_response_ms=10.5,
        created_at=now,
    )
    await real_dal.dns_server_metrics.async_insert(
        id=metric_b_id,
        server_id=server_b_id,
        tenant=tenant_b,
        timestamp=now,
        queries_total=2000,
        cache_hits=1600,
        errors=10,
        avg_response_ms=12.0,
        created_at=now,
    )

    # Query metrics as tenant-a
    manager_a = ServerManager(real_dal, tenant_a)
    metrics_a = await manager_a.get_metrics(server_a_id, hours=24)

    # Verify tenant-a sees ONLY their metrics
    assert len(metrics_a) == 1
    assert metrics_a[0].server_id == server_a_id
    assert metrics_a[0].queries_total == 1000

    # Query metrics as tenant-b
    manager_b = ServerManager(real_dal, tenant_b)
    metrics_b = await manager_b.get_metrics(server_b_id, hours=24)

    # Verify tenant-b sees ONLY their metrics
    assert len(metrics_b) == 1
    assert metrics_b[0].server_id == server_b_id
    assert metrics_b[0].queries_total == 2000


@pytest.mark.asyncio
async def test_config_service_cross_tenant_isolated(real_dal) -> None:
    """Test ConfigService.get_server_config() returns ONLY tenant's zones and records."""
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Create zone and records in tenant-a
    zone_a_id = str(uuid4())
    rec_a_id = str(uuid4())

    await real_dal.dns_zones.async_insert(
        id=zone_a_id,
        tenant=tenant_a,
        name="config-test-a.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_records.async_insert(
        id=rec_a_id,
        zone_id=zone_a_id,
        tenant=tenant_a,
        name="api",
        type="A",
        value="192.0.2.10",
        ttl=300,
        priority=None,
        weight=None,
        port=None,
        created_at=now,
        updated_at=now,
    )

    # Create zone and records in tenant-b
    zone_b_id = str(uuid4())
    rec_b_id = str(uuid4())

    await real_dal.dns_zones.async_insert(
        id=zone_b_id,
        tenant=tenant_b,
        name="config-test-b.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_records.async_insert(
        id=rec_b_id,
        zone_id=zone_b_id,
        tenant=tenant_b,
        name="api",
        type="A",
        value="198.51.100.10",
        ttl=300,
        priority=None,
        weight=None,
        port=None,
        created_at=now,
        updated_at=now,
    )

    # Get config as tenant-a
    config_svc_a = ConfigService(real_dal, tenant_a)
    config_a = await config_svc_a.get_server_config()

    # Verify tenant-a config contains ONLY their zone
    assert len(config_a.zones) == 1
    assert config_a.zones[0].name == "config-test-a.com"
    assert len(config_a.zones[0].records) == 1
    assert config_a.zones[0].records[0].name == "api"
    assert config_a.zones[0].records[0].value == "192.0.2.10"

    # Get config as tenant-b
    config_svc_b = ConfigService(real_dal, tenant_b)
    config_b = await config_svc_b.get_server_config()

    # Verify tenant-b config contains ONLY their zone
    assert len(config_b.zones) == 1
    assert config_b.zones[0].name == "config-test-b.com"
    assert len(config_b.zones[0].records) == 1
    assert config_b.zones[0].records[0].name == "api"
    assert config_b.zones[0].records[0].value == "198.51.100.10"


@pytest.mark.asyncio
async def test_analytics_time_window_filter_route_realdal(
    app_with_netsvcs_realdal: Quart,
    real_dal: AsyncDB,
    tenant_a_token_realdal: str,
    tenant_b_token_realdal: str,
) -> None:
    """REGRESSION: Test that analytics route time-window filter actually works.

    The old comma-syntax query db(tenant==t, timestamp>=cutoff) silently
    dropped the timestamp condition, causing analytics to return all-time
    data regardless of the ?hours query parameter.

    This test hits the actual GET /api/v1/netsvcs/analytics/queries?hours=1 route
    to verify it enforces tenant isolation AND time-window filtering through
    the route, not just the underlying query logic.
    """
    tenant_a_id = "tenant-analytics-test"
    tenant_b_id = "tenant-b"
    now = datetime.now(timezone.utc)
    in_window_time = now - timedelta(minutes=10)  # 10 minutes ago
    out_of_window_time = now - timedelta(hours=48)  # 48 hours ago

    # Create a server for tenant-a
    server_a_id = str(uuid4())
    await real_dal.dns_servers.async_insert(
        id=server_a_id,
        tenant=tenant_a_id,
        name="test-resolver-a",
        status="online",
        version="1.0",
        region="us-west",
        hostname="test-a.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )

    # Seed a metric INSIDE the 1-hour window (10 minutes ago) for tenant-a
    in_window_metric_a_id = str(uuid4())
    await real_dal.dns_server_metrics.async_insert(
        id=in_window_metric_a_id,
        server_id=server_a_id,
        tenant=tenant_a_id,
        timestamp=in_window_time,
        queries_total=1000,
        cache_hits=800,
        errors=5,
        avg_response_ms=10.5,
        created_at=now,
    )

    # Seed a metric OUTSIDE the 1-hour window (48 hours ago) for tenant-a
    out_of_window_metric_a_id = str(uuid4())
    await real_dal.dns_server_metrics.async_insert(
        id=out_of_window_metric_a_id,
        server_id=server_a_id,
        tenant=tenant_a_id,
        timestamp=out_of_window_time,
        queries_total=2000,
        cache_hits=1600,
        errors=10,
        avg_response_ms=12.0,
        created_at=now,
    )

    # Create a server for tenant-b
    server_b_id = str(uuid4())
    await real_dal.dns_servers.async_insert(
        id=server_b_id,
        tenant=tenant_b_id,
        name="test-resolver-b",
        status="online",
        version="1.0",
        region="us-east",
        hostname="test-b.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )

    # Seed a metric for tenant-b (also in-window, to test tenant filtering)
    metric_b_id = str(uuid4())
    await real_dal.dns_server_metrics.async_insert(
        id=metric_b_id,
        server_id=server_b_id,
        tenant=tenant_b_id,
        timestamp=in_window_time,
        queries_total=5000,
        cache_hits=4000,
        errors=20,
        avg_response_ms=15.0,
        created_at=now,
    )

    # Call the analytics route as tenant-a with 1-hour window
    # Route: GET /api/v1/netsvcs/analytics/queries?hours=1
    client = app_with_netsvcs_realdal.test_client()

    # Mock the feature flag to be enabled
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response_a = await client.get(
            "/api/v1/netsvcs/analytics/queries?hours=1",
            headers={"Authorization": f"Bearer {tenant_a_token_realdal}"},
        )

        assert response_a.status_code == 200
        data_a = await response_a.get_json()

        # Verify tenant-a sees ONLY their in-window metric (1000 queries)
        # NOT their out-of-window metric (2000) or tenant-b's metric (5000)
        assert data_a["total_queries"] == 1000, (
            f"Expected tenant-a to see 1000 queries (in-window only), "
            f"got {data_a['total_queries']}. "
            f"Old comma-syntax bug would return 3000 (1000+2000 from same tenant), "
            f"or missing tenant scoping would leak cross-tenant data."
        )

        # Call the analytics route as tenant-b with same window
        response_b = await client.get(
            "/api/v1/netsvcs/analytics/queries?hours=1",
            headers={"Authorization": f"Bearer {tenant_b_token_realdal}"},
        )

        assert response_b.status_code == 200
        data_b = await response_b.get_json()

        # Verify tenant-b sees ONLY their in-window metric (5000 queries)
        assert data_b["total_queries"] == 5000, (
            f"Expected tenant-b to see 5000 queries (in-window only), "
            f"got {data_b['total_queries']}. "
            f"Missing tenant scoping would allow cross-tenant data leakage."
        )
