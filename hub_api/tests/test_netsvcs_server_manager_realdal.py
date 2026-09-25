"""Direct unit tests for ServerManager against a real migrated DAL.

Existing dns_servers API tests mock ServerManager entirely, so the real
manager methods (initialize, register_server, get_server, delete_server,
record_heartbeat) were never exercised directly.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from hub_api.modules.netsvcs.managers.server_manager import ServerManager


@pytest.mark.asyncio
async def test_initialize_does_not_raise(real_dal) -> None:
    """initialize() logs and completes without error."""
    manager = ServerManager(real_dal, str(uuid4()))
    await manager.initialize()


@pytest.mark.asyncio
async def test_register_server_creates_record(real_dal) -> None:
    """register_server() persists a new server row and returns its record."""
    tenant_id = str(uuid4())
    manager = ServerManager(real_dal, tenant_id)

    record = await manager.register_server(
        name="dns-1",
        hostname="dns1.example.com",
        version="1.2.3",
        region="us-east-1",
    )

    assert record.name == "dns-1"
    assert record.status == "online"
    assert record.tenant == tenant_id

    fetched = await manager.get_server(record.id)
    assert fetched is not None
    assert fetched.hostname == "dns1.example.com"


@pytest.mark.asyncio
async def test_get_server_not_found_returns_none(real_dal) -> None:
    """get_server() returns None for an unknown server_id."""
    manager = ServerManager(real_dal, str(uuid4()))

    result = await manager.get_server("does-not-exist")

    assert result is None


@pytest.mark.asyncio
async def test_get_server_cross_tenant_denied(real_dal) -> None:
    """get_server() never returns a server belonging to a different tenant."""
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    manager_a = ServerManager(real_dal, tenant_a)
    manager_b = ServerManager(real_dal, tenant_b)

    record = await manager_a.register_server(
        name="dns-a", hostname="a.example.com", version="1.0.0", region="us-east-1"
    )

    result = await manager_b.get_server(record.id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_server_not_found_returns_false(real_dal) -> None:
    """delete_server() returns False when the server does not exist."""
    manager = ServerManager(real_dal, str(uuid4()))

    deleted = await manager.delete_server("nonexistent")

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_server_cascades_metrics(real_dal) -> None:
    """delete_server() removes the server and cascades its metrics rows."""
    tenant_id = str(uuid4())
    manager = ServerManager(real_dal, tenant_id)

    record = await manager.register_server(
        name="dns-del", hostname="del.example.com", version="1.0.0", region="eu-west-1"
    )
    await manager.record_heartbeat(
        record.id,
        {"queries_total": 10, "cache_hits": 5, "errors": 0, "avg_response_ms": 1.5},
    )

    deleted = await manager.delete_server(record.id)
    assert deleted is True

    assert await manager.get_server(record.id) is None
    metrics = await manager.get_metrics(record.id, hours=999999)
    assert metrics == []


@pytest.mark.asyncio
async def test_record_heartbeat_not_found_returns_false(real_dal) -> None:
    """record_heartbeat() returns False when the server does not exist."""
    manager = ServerManager(real_dal, str(uuid4()))

    recorded = await manager.record_heartbeat(
        "nonexistent",
        {"queries_total": 1, "cache_hits": 1, "errors": 0, "avg_response_ms": 1.0},
    )

    assert recorded is False


@pytest.mark.asyncio
async def test_record_heartbeat_updates_status_and_inserts_metrics(real_dal) -> None:
    """record_heartbeat() marks the server online and records a metrics row."""
    tenant_id = str(uuid4())
    manager = ServerManager(real_dal, tenant_id)

    record = await manager.register_server(
        name="dns-hb", hostname="hb.example.com", version="1.0.0", region="ap-south-1"
    )

    recorded = await manager.record_heartbeat(
        record.id,
        {
            "queries_total": 1000,
            "cache_hits": 800,
            "errors": 5,
            "avg_response_ms": 12.5,
        },
    )
    assert recorded is True

    metrics = await manager.get_metrics(record.id, hours=24)
    assert len(metrics) == 1
    assert metrics[0].queries_total == 1000
    assert metrics[0].cache_hits == 800


@pytest.mark.asyncio
async def test_record_heartbeat_defaults_missing_metric_fields(real_dal) -> None:
    """record_heartbeat() defaults absent metrics_dict keys to 0/0.0."""
    tenant_id = str(uuid4())
    manager = ServerManager(real_dal, tenant_id)

    record = await manager.register_server(
        name="dns-defaults", hostname="d.example.com", version="1.0.0", region="us-west-2"
    )

    recorded = await manager.record_heartbeat(record.id, {})
    assert recorded is True

    metrics = await manager.get_metrics(record.id, hours=24)
    assert metrics[0].queries_total == 0
    assert metrics[0].avg_response_ms == 0.0
