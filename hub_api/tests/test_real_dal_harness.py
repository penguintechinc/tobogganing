"""Smoke test proving the real_dal fixture round-trips against a migrated sqlite DB.

Guards the integration harness itself: if penguin-dal's async API, the migration
chain, or reflection breaks, this fails loudly instead of being masked by mocks.
"""
from __future__ import annotations

import datetime
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_real_dal_async_crud_round_trip(real_dal: Any) -> None:
    """async_insert → filtered select → update → delete all work on a real DB."""
    now = datetime.datetime.now(datetime.UTC)
    await real_dal.c2c_endpoints.async_insert(
        id="e1",
        tenant="t1",
        region="nj",
        name="n1",
        engine_url="http://x",
        target="h1",
        api_key_hash="abc",
        enabled=True,
        created_at=now,
        updated_at=now,
    )

    rows = await real_dal(
        (real_dal.c2c_endpoints.tenant == "t1")
        & (real_dal.c2c_endpoints.region == "nj")
    ).select()
    row = rows.first()
    assert row is not None
    assert row.id == "e1"
    assert row.name == "n1"

    updated = await real_dal(real_dal.c2c_endpoints.id == "e1").update(name="n1b")
    assert updated == 1
    again = await real_dal(real_dal.c2c_endpoints.id == "e1").select()
    assert again.first().name == "n1b"

    deleted = await real_dal(real_dal.c2c_endpoints.id == "e1").delete()
    assert deleted == 1
    assert len(await real_dal(real_dal.c2c_endpoints.id == "e1").select()) == 0


@pytest.mark.asyncio
async def test_real_dal_tenant_isolation(real_dal: Any) -> None:
    """A filtered select scoped to one tenant never returns another tenant's row."""
    now = datetime.datetime.now(datetime.UTC)
    for tenant in ("t1", "t2"):
        await real_dal.c2c_endpoints.async_insert(
            id=f"e-{tenant}",
            tenant=tenant,
            region="nj",
            name="n",
            engine_url="http://x",
            target="h",
            api_key_hash="k",
            enabled=True,
            created_at=now,
            updated_at=now,
        )

    t1_rows = await real_dal(real_dal.c2c_endpoints.tenant == "t1").select()
    assert len(t1_rows) == 1
    assert t1_rows.first().id == "e-t1"
