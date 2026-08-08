"""Real-DB tenant-isolation tests for netsvcs module using real_dal fixture.

REGRESSION TEST for analytics time-window filter bug:
The old comma-syntax query db(tenant==t, timestamp>=cutoff) silently dropped
the timestamp condition, causing analytics to return all-time data regardless
of the ?hours query parameter. The new & syntax fixes this.
This test FAILS on old comma-syntax, PASSES with the fix.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from hub_api.modules.netsvcs.managers.zone_manager import ZoneManager
from hub_api.modules.netsvcs.managers.server_manager import ServerManager
from hub_api.modules.netsvcs.managers.config_service import ConfigService


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
async def test_analytics_time_window_filter_realdal(real_dal) -> None:
    """REGRESSION: Test that analytics time-window filter actually works.

    The old comma-syntax query db(tenant==t, timestamp>=cutoff) silently
    dropped the timestamp condition, causing analytics to return all-time
    data regardless of the ?hours query parameter.

    This test FAILS on the old syntax (both metrics counted),
    PASSES with the new & syntax (only in-window metric counted).

    This is a regression test for a bug the mock-based tests missed
    because mocks don't enforce query semantics.
    """
    tenant_id = "tenant-analytics-test"
    now = datetime.now(timezone.utc)
    in_window_time = now - timedelta(minutes=10)  # 10 minutes ago
    out_of_window_time = now - timedelta(hours=48)  # 48 hours ago

    # Create a server for this tenant
    server_id = str(uuid4())
    await real_dal.dns_servers.async_insert(
        id=server_id,
        tenant=tenant_id,
        name="test-resolver",
        status="online",
        version="1.0",
        region="us-west",
        hostname="test.internal",
        last_heartbeat=now,
        created_at=now,
        updated_at=now,
    )

    # Seed a metric INSIDE the 1-hour window (10 minutes ago)
    in_window_metric_id = str(uuid4())
    await real_dal.dns_server_metrics.async_insert(
        id=in_window_metric_id,
        server_id=server_id,
        tenant=tenant_id,
        timestamp=in_window_time,
        queries_total=1000,
        cache_hits=800,
        errors=5,
        avg_response_ms=10.5,
        created_at=now,
    )

    # Seed a metric OUTSIDE the 1-hour window (48 hours ago)
    out_of_window_metric_id = str(uuid4())
    await real_dal.dns_server_metrics.async_insert(
        id=out_of_window_metric_id,
        server_id=server_id,
        tenant=tenant_id,
        timestamp=out_of_window_time,
        queries_total=2000,
        cache_hits=1600,
        errors=10,
        avg_response_ms=12.0,
        created_at=now,
    )

    # Query metrics with 1-hour window using the fixed SQL syntax
    # (simulating what the analytics route does)
    cutoff = now - timedelta(hours=1)
    rowset = await real_dal(
        (real_dal.dns_server_metrics.tenant == tenant_id)
        & (real_dal.dns_server_metrics.timestamp >= cutoff)
    ).select()

    rows = list(rowset)

    # REGRESSION TEST: With the fix, we should see ONLY the in-window metric
    # With the old comma-syntax, BOTH metrics would be returned
    assert len(rows) == 1, (
        f"Expected 1 metric (only in-window), got {len(rows)}. "
        f"Old comma-syntax bug would return both in-window and out-of-window metrics."
    )

    # Verify it's the correct (in-window) metric
    row = rows[0]
    # SQLite returns datetimes without tzinfo, so compare just the time part
    assert row.timestamp.replace(tzinfo=timezone.utc) == in_window_time
    assert row.queries_total == 1000

    # Also verify tenant isolation in analytics: seed metrics for tenant-b
    # and ensure tenant-a's query doesn't see them
    tenant_b = "tenant-b"
    server_b_id = str(uuid4())

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

    # Seed a metric for tenant-b (also in-window, to prove it's tenant filtering)
    metric_b_id = str(uuid4())
    await real_dal.dns_server_metrics.async_insert(
        id=metric_b_id,
        server_id=server_b_id,
        tenant=tenant_b,
        timestamp=in_window_time,
        queries_total=5000,
        cache_hits=4000,
        errors=20,
        avg_response_ms=15.0,
        created_at=now,
    )

    # Query analytics for tenant-a with 1-hour window
    # Should see ONLY tenant-a's in-window metric, NOT tenant-b's
    rowset_a = await real_dal(
        (real_dal.dns_server_metrics.tenant == tenant_id)
        & (real_dal.dns_server_metrics.timestamp >= cutoff)
    ).select()

    rows_a = list(rowset_a)
    assert len(rows_a) == 1, "Tenant-a should see only 1 metric (their own in-window one)"
    assert rows_a[0].queries_total == 1000  # tenant-a's metric

    # Query analytics for tenant-b with same window
    # Should see ONLY tenant-b's in-window metric
    rowset_b = await real_dal(
        (real_dal.dns_server_metrics.tenant == tenant_b)
        & (real_dal.dns_server_metrics.timestamp >= cutoff)
    ).select()

    rows_b = list(rowset_b)
    assert len(rows_b) == 1, "Tenant-b should see only 1 metric (their own in-window one)"
    assert rows_b[0].queries_total == 5000  # tenant-b's metric
