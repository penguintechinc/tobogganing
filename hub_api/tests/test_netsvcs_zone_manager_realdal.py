"""Direct unit tests for ZoneManager against a real migrated DAL.

Existing zones API tests (tests/test_netsvcs_zones.py) mock ZoneManager
entirely, so most of the real manager logic — duplicate-name enforcement,
record type/TTL validation, update/delete not-found branches — was never
exercised. This file drives the real manager directly.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from hub_api.modules.netsvcs.managers.zone_manager import ZoneManager


@pytest.mark.asyncio
async def test_create_zone_success(real_dal) -> None:
    """create_zone() persists a new zone and returns its record."""
    tenant_id = str(uuid4())
    manager = ZoneManager(real_dal, tenant_id)

    zone = await manager.create_zone(name="example.com", visibility="public", description="test")

    assert zone is not None
    assert zone.name == "example.com"
    assert zone.tenant == tenant_id


@pytest.mark.asyncio
async def test_create_zone_duplicate_name_returns_none(real_dal) -> None:
    """create_zone() returns None on a duplicate name within the same tenant."""
    tenant_id = str(uuid4())
    manager = ZoneManager(real_dal, tenant_id)

    await manager.create_zone(name="dup.com")
    result = await manager.create_zone(name="dup.com")

    assert result is None


@pytest.mark.asyncio
async def test_create_zone_same_name_different_tenant_allowed(real_dal) -> None:
    """create_zone() allows the same zone name across different tenants."""
    manager_a = ZoneManager(real_dal, str(uuid4()))
    manager_b = ZoneManager(real_dal, str(uuid4()))

    zone_a = await manager_a.create_zone(name="shared.com")
    zone_b = await manager_b.create_zone(name="shared.com")

    assert zone_a is not None
    assert zone_b is not None


@pytest.mark.asyncio
async def test_get_zone_not_found_returns_none(real_dal) -> None:
    """get_zone() returns None for an unknown zone_id."""
    manager = ZoneManager(real_dal, str(uuid4()))

    assert await manager.get_zone("nonexistent") is None


@pytest.mark.asyncio
async def test_get_zone_success(real_dal) -> None:
    """get_zone() returns the zone record when found."""
    manager = ZoneManager(real_dal, str(uuid4()))
    created = await manager.create_zone(name="found.com")

    fetched = await manager.get_zone(created.id)

    assert fetched is not None
    assert fetched.name == "found.com"


@pytest.mark.asyncio
async def test_update_zone_not_found_returns_none(real_dal) -> None:
    """update_zone() returns None when the zone doesn't exist."""
    manager = ZoneManager(real_dal, str(uuid4()))

    assert await manager.update_zone("nonexistent", name="new.com") is None


@pytest.mark.asyncio
async def test_update_zone_duplicate_name_returns_none(real_dal) -> None:
    """update_zone() returns None when renaming to a name already used in-tenant."""
    tenant_id = str(uuid4())
    manager = ZoneManager(real_dal, tenant_id)
    await manager.create_zone(name="taken.com")
    zone2 = await manager.create_zone(name="mine.com")

    result = await manager.update_zone(zone2.id, name="taken.com")

    assert result is None


@pytest.mark.asyncio
async def test_update_zone_same_name_noop_allowed(real_dal) -> None:
    """update_zone() allows 're-setting' the same name (no uniqueness check triggered)."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="same.com", visibility="public")

    updated = await manager.update_zone(zone.id, name="same.com", visibility="internal")

    assert updated is not None
    assert updated.visibility == "internal"


@pytest.mark.asyncio
async def test_update_zone_success_partial_fields(real_dal) -> None:
    """update_zone() updates only the provided fields, preserving the rest."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="partial.com", description="original")

    updated = await manager.update_zone(zone.id, visibility="restricted")

    assert updated is not None
    assert updated.name == "partial.com"
    assert updated.visibility == "restricted"
    assert updated.description == "original"


@pytest.mark.asyncio
async def test_delete_zone_not_found_returns_false(real_dal) -> None:
    """delete_zone() returns False when the zone doesn't exist."""
    manager = ZoneManager(real_dal, str(uuid4()))

    assert await manager.delete_zone("nonexistent") is False


@pytest.mark.asyncio
async def test_delete_zone_cascades_records(real_dal) -> None:
    """delete_zone() removes the zone and cascades its records."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="cascade.com")
    await manager.create_record(zone_id=zone.id, name="www", type="A", value="1.1.1.1")

    deleted = await manager.delete_zone(zone.id)
    assert deleted is True

    assert await manager.get_zone(zone.id) is None
    assert await manager.list_records(zone.id) == []


@pytest.mark.asyncio
async def test_create_record_zone_not_found_returns_none(real_dal) -> None:
    """create_record() returns None when the parent zone doesn't exist."""
    manager = ZoneManager(real_dal, str(uuid4()))

    result = await manager.create_record(
        zone_id="nonexistent", name="www", type="A", value="1.1.1.1"
    )

    assert result is None


@pytest.mark.asyncio
async def test_create_record_invalid_type_returns_none(real_dal) -> None:
    """create_record() returns None for an unsupported record type."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="badtype.com")

    result = await manager.create_record(zone_id=zone.id, name="www", type="INVALID", value="x")

    assert result is None


@pytest.mark.asyncio
async def test_create_record_negative_ttl_returns_none(real_dal) -> None:
    """create_record() returns None for a negative TTL."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="badttl.com")

    result = await manager.create_record(
        zone_id=zone.id, name="www", type="A", value="1.1.1.1", ttl=-1
    )

    assert result is None


@pytest.mark.asyncio
async def test_create_record_success(real_dal) -> None:
    """create_record() persists a valid record under the zone."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="valid.com")

    record = await manager.create_record(
        zone_id=zone.id, name="www", type="A", value="1.2.3.4", ttl=600
    )

    assert record is not None
    assert record.name == "www"
    assert record.ttl == 600

    records = await manager.list_records(zone.id)
    assert len(records) == 1


@pytest.mark.asyncio
async def test_get_record_not_found_returns_none(real_dal) -> None:
    """get_record() returns None for an unknown record_id."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="norecord.com")

    assert await manager.get_record(zone.id, "nonexistent") is None


@pytest.mark.asyncio
async def test_update_record_not_found_returns_none(real_dal) -> None:
    """update_record() returns None when the record doesn't exist."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="updatemissing.com")

    result = await manager.update_record(zone.id, "nonexistent", value="1.1.1.1")

    assert result is None


@pytest.mark.asyncio
async def test_update_record_invalid_type_returns_none(real_dal) -> None:
    """update_record() returns None when changing to an unsupported type."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="updatetype.com")
    record = await manager.create_record(zone_id=zone.id, name="www", type="A", value="1.1.1.1")

    result = await manager.update_record(zone.id, record.id, type="BOGUS")

    assert result is None


@pytest.mark.asyncio
async def test_update_record_negative_ttl_returns_none(real_dal) -> None:
    """update_record() returns None for a negative TTL update."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="updatettl.com")
    record = await manager.create_record(zone_id=zone.id, name="www", type="A", value="1.1.1.1")

    result = await manager.update_record(zone.id, record.id, ttl=-5)

    assert result is None


@pytest.mark.asyncio
async def test_update_record_success_all_fields(real_dal) -> None:
    """update_record() updates every mutable field and persists them."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="updateall.com")
    record = await manager.create_record(
        zone_id=zone.id, name="mail", type="MX", value="mail.updateall.com", priority=10
    )

    updated = await manager.update_record(
        zone.id,
        record.id,
        name="mail2",
        type="MX",
        value="mail2.updateall.com",
        ttl=900,
        priority=20,
        weight=5,
        port=25,
    )

    assert updated is not None
    assert updated.name == "mail2"
    assert updated.value == "mail2.updateall.com"
    assert updated.ttl == 900
    assert updated.priority == 20
    assert updated.weight == 5
    assert updated.port == 25


@pytest.mark.asyncio
async def test_delete_record_not_found_returns_false(real_dal) -> None:
    """delete_record() returns False when the record doesn't exist."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="deletemissing.com")

    assert await manager.delete_record(zone.id, "nonexistent") is False


@pytest.mark.asyncio
async def test_delete_record_success(real_dal) -> None:
    """delete_record() removes an existing record."""
    manager = ZoneManager(real_dal, str(uuid4()))
    zone = await manager.create_zone(name="deleteok.com")
    record = await manager.create_record(zone_id=zone.id, name="www", type="A", value="1.1.1.1")

    deleted = await manager.delete_record(zone.id, record.id)
    assert deleted is True
    assert await manager.get_record(zone.id, record.id) is None


@pytest.mark.asyncio
async def test_list_zones_tenant_scoped(real_dal) -> None:
    """list_zones() only returns zones for the manager's tenant."""
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    manager_a = ZoneManager(real_dal, tenant_a)
    manager_b = ZoneManager(real_dal, tenant_b)

    await manager_a.create_zone(name="a-only.com")
    await manager_b.create_zone(name="b-only.com")

    zones_a = await manager_a.list_zones()
    names_a = {z.name for z in zones_a}
    assert "a-only.com" in names_a
    assert "b-only.com" not in names_a
