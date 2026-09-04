"""Direct unit tests for ConfigService against a real migrated DAL.

Covers get_config_version()/bump_version() version-counter behavior, which
existing zones/dns_servers API tests only ever exercise through a mocked
ConfigService — the real non-atomic read-then-write logic itself was
untested.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from hub_api.modules.netsvcs.managers.config_service import ConfigService


@pytest.mark.asyncio
async def test_get_config_version_defaults_to_zero(real_dal) -> None:
    """get_config_version() returns 0 when no version row exists yet."""
    tenant_id = str(uuid4())
    svc = ConfigService(real_dal, tenant_id)

    version = await svc.get_config_version()

    assert version == 0


@pytest.mark.asyncio
async def test_bump_version_creates_row_starting_at_one(real_dal) -> None:
    """bump_version() creates a new version row at 1 when none exists."""
    tenant_id = str(uuid4())
    svc = ConfigService(real_dal, tenant_id)

    new_version = await svc.bump_version()

    assert new_version == 1
    assert await svc.get_config_version() == 1


@pytest.mark.asyncio
async def test_bump_version_increments_existing_row(real_dal) -> None:
    """bump_version() increments an existing version row monotonically."""
    tenant_id = str(uuid4())
    svc = ConfigService(real_dal, tenant_id)

    await svc.bump_version()
    await svc.bump_version()
    third = await svc.bump_version()

    assert third == 3
    assert await svc.get_config_version() == 3


@pytest.mark.asyncio
async def test_bump_version_is_tenant_scoped(real_dal) -> None:
    """bump_version() for one tenant never affects another tenant's version."""
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    svc_a = ConfigService(real_dal, tenant_a)
    svc_b = ConfigService(real_dal, tenant_b)

    await svc_a.bump_version()
    await svc_a.bump_version()

    assert await svc_a.get_config_version() == 2
    assert await svc_b.get_config_version() == 0


@pytest.mark.asyncio
async def test_get_server_config_empty_tenant_returns_defaults(real_dal) -> None:
    """get_server_config() returns empty zones list and default settings for a fresh tenant."""
    tenant_id = str(uuid4())
    svc = ConfigService(real_dal, tenant_id)

    config = await svc.get_server_config()

    assert config.zones == []
    assert config.version == 0
    assert config.cache_settings["ttl"] == 300
    assert config.settings["ioc_filtering"] is True


@pytest.mark.asyncio
async def test_get_server_config_assembles_zones_and_records(real_dal) -> None:
    """get_server_config() assembles zones with their records and current version."""
    import datetime as dt

    tenant_id = str(uuid4())
    now = dt.datetime.now(dt.timezone.utc)

    zone_id = str(uuid4())
    await real_dal.dns_zones.async_insert(
        id=zone_id,
        tenant=tenant_id,
        name="example.com",
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

    svc = ConfigService(real_dal, tenant_id)
    await svc.bump_version()

    config = await svc.get_server_config()

    assert len(config.zones) == 1
    assert config.zones[0].name == "example.com"
    assert len(config.zones[0].records) == 1
    assert config.zones[0].records[0].name == "www"
    assert config.version == 1
