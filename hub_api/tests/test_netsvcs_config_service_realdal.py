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


async def _add_zone(dal, tenant: str, name: str, visibility: str) -> str:
    """Insert a zone with one A record; returns the zone id."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    zid = str(uuid4())
    await dal.dns_zones.async_insert(
        id=zid, tenant=tenant, name=name, visibility=visibility, created_at=now, updated_at=now
    )
    await dal.dns_records.async_insert(
        id=str(uuid4()),
        tenant=tenant,
        zone_id=zid,
        name=f"www.{name}",
        type="A",
        value="10.0.0.1",
        ttl=60,
        created_at=now,
        updated_at=now,
    )
    return zid


@pytest.mark.asyncio
async def test_get_server_config_keeps_all_valid_visibilities(real_dal) -> None:
    """All four spec visibility levels are pushed (normalized) with their records."""
    tenant = str(uuid4())
    for vis in ("public", "internal", "Restricted", "private"):
        await _add_zone(real_dal, tenant, f"{vis.lower()}.example.com", vis)

    config = await ConfigService(real_dal, tenant).get_server_config()

    assert sorted(z.visibility for z in config.zones) == [
        "internal",
        "private",
        "public",
        "restricted",
    ]
    assert all(len(z.records) == 1 for z in config.zones)


@pytest.mark.asyncio
async def test_get_server_config_drops_unknown_visibility(real_dal) -> None:
    """A zone with an unknown visibility is dropped (fail closed), not served as public."""
    tenant = str(uuid4())
    await _add_zone(real_dal, tenant, "ok.example.com", "public")
    await _add_zone(real_dal, tenant, "bad.example.com", "everyone")
    await _add_zone(real_dal, tenant, "empty.example.com", "")

    config = await ConfigService(real_dal, tenant).get_server_config()

    assert [z.name for z in config.zones] == ["ok.example.com"]


@pytest.mark.asyncio
async def test_get_server_config_excludes_other_tenant_zones(real_dal) -> None:
    """Zones of another tenant never appear in this tenant's config."""
    tenant, other = str(uuid4()), str(uuid4())
    await _add_zone(real_dal, other, "other.example.com", "public")

    config = await ConfigService(real_dal, tenant).get_server_config()

    assert config.zones == []


@pytest.mark.asyncio
async def test_resolver_settings_default_when_no_row(real_dal) -> None:
    """With no stored row, defaults flow into cache_settings/settings."""
    config = await ConfigService(real_dal, str(uuid4())).get_server_config()

    assert config.cache_settings == {"enabled": True, "ttl": 300, "max_entries": 10000}
    assert config.settings == {"log_queries": True, "enable_dnssec": False, "ioc_filtering": True}


@pytest.mark.asyncio
async def test_resolver_settings_stored_values_are_served(real_dal) -> None:
    """Stored settings replace the defaults and each update bumps the version."""
    tenant = str(uuid4())
    svc = ConfigService(real_dal, tenant)

    await svc.update_resolver_settings(cache_ttl=60, enable_dnssec=True)
    await svc.update_resolver_settings(cache_enabled=False, ioc_filtering=False)
    config = await svc.get_server_config()

    assert config.cache_settings == {"enabled": False, "ttl": 60, "max_entries": 10000}
    assert config.settings == {"log_queries": True, "enable_dnssec": True, "ioc_filtering": False}
    assert config.version == 2
    other = await ConfigService(real_dal, str(uuid4())).get_resolver_settings()
    assert other["cache_ttl"] == 300


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"nope": 1},
        {"cache_ttl": -1},
        {"cache_ttl": 86401},
        {"cache_ttl": "300"},
        {"cache_max_entries": True},
        {"enable_dnssec": "yes"},
    ],
)
async def test_update_resolver_settings_rejects_invalid(real_dal, changes) -> None:
    """Invalid keys/values raise ValueError and write nothing."""
    svc = ConfigService(real_dal, str(uuid4()))

    with pytest.raises(ValueError):
        await svc.update_resolver_settings(**changes)

    assert await svc.get_config_version() == 0
