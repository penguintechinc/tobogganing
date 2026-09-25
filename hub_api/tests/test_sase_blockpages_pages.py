"""Test SASE BlockPageManager with real DAL."""
from __future__ import annotations

import pytest
from typing import Any

from hub_api.modules.sase.security.blockpages.pages import BlockPageManager
from hub_api.modules.sase.security.blockpages.models import PageStatus


@pytest.mark.asyncio
async def test_create_page(real_dal: Any):
    """Test creating a block page."""
    manager = BlockPageManager(real_dal)
    tenant = "tenant-test-a"

    page = await manager.create(
        tenant=tenant,
        name="Test Page",
        markdown="# Blocked",
        created_by="user-123",
    )

    assert page.id is not None
    assert page.tenant == tenant
    assert page.name == "Test Page"
    assert page.markdown == "# Blocked"
    assert page.status == PageStatus.draft
    assert page.version == 1
    assert page.created_by == "user-123"
    assert page.updated_by is None


@pytest.mark.asyncio
async def test_get_by_id(real_dal: Any):
    """Test retrieving a page by ID."""
    manager = BlockPageManager(real_dal)
    tenant = "tenant-test-a"

    created = await manager.create(
        tenant=tenant,
        name="Test Page",
        markdown="# Blocked",
        created_by="user-123",
    )

    retrieved = await manager.get_by_id(tenant=tenant, page_id=created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == "Test Page"


@pytest.mark.asyncio
async def test_update_page(real_dal: Any):
    """Test updating a page's markdown."""
    manager = BlockPageManager(real_dal)
    tenant = "tenant-test-a"

    created = await manager.create(
        tenant=tenant,
        name="Test Page",
        markdown="# Original",
        created_by="user-123",
    )

    updated = await manager.update(
        tenant=tenant,
        page_id=created.id,
        markdown="# Updated Content",
        updated_by="user-456",
    )

    assert updated is not None
    assert updated.markdown == "# Updated Content"
    assert updated.updated_by == "user-456"
    assert updated.version == 1  # Version doesn't bump until publish


@pytest.mark.asyncio
async def test_publish_page(real_dal: Any):
    """Test publishing a page (draft -> live, bumps version)."""
    manager = BlockPageManager(real_dal)
    tenant = "tenant-test-a"

    created = await manager.create(
        tenant=tenant,
        name="Test Page",
        markdown="# Live Content",
        created_by="user-123",
    )

    assert created.status == PageStatus.draft

    published = await manager.publish(tenant=tenant, page_id=created.id)

    assert published is not None
    assert published.status == PageStatus.live
    assert published.version == 2


@pytest.mark.asyncio
async def test_revert_page(real_dal: Any):
    """Test reverting a page to draft."""
    manager = BlockPageManager(real_dal)
    tenant = "tenant-test-a"

    created = await manager.create(
        tenant=tenant,
        name="Test Page",
        markdown="# Content",
        created_by="user-123",
    )

    published = await manager.publish(tenant=tenant, page_id=created.id)
    assert published.status == PageStatus.live

    reverted = await manager.revert(tenant=tenant, page_id=created.id, version=2)

    assert reverted is not None
    assert reverted.status == PageStatus.draft


@pytest.mark.asyncio
async def test_get_live_page(real_dal: Any):
    """Test retrieving live version of a page."""
    manager = BlockPageManager(real_dal)
    tenant = "tenant-test-a"

    created = await manager.create(
        tenant=tenant,
        name="Live Test",
        markdown="# Content",
        created_by="user-123",
    )

    # Not live yet
    live = await manager.get_live(tenant=tenant, name="Live Test")
    assert live is None

    # Publish it
    await manager.publish(tenant=tenant, page_id=created.id)

    # Now should get it
    live = await manager.get_live(tenant=tenant, name="Live Test")
    assert live is not None
    assert live.status == PageStatus.live


@pytest.mark.asyncio
async def test_list_pages(real_dal: Any):
    """Test listing all pages for a tenant."""
    manager = BlockPageManager(real_dal)
    tenant = "tenant-test-a"

    page1 = await manager.create(
        tenant=tenant,
        name="Page 1",
        markdown="# Content 1",
        created_by="user-123",
    )

    page2 = await manager.create(
        tenant=tenant,
        name="Page 2",
        markdown="# Content 2",
        created_by="user-123",
    )

    pages = await manager.list_pages(tenant=tenant)

    assert len(pages) >= 2
    page_ids = [p.id for p in pages]
    assert page1.id in page_ids
    assert page2.id in page_ids


@pytest.mark.asyncio
async def test_cross_tenant_isolation_read(real_dal: Any):
    """Regression: page created by tenant A not readable by tenant B.

    regression: cross-tenant
    """
    manager = BlockPageManager(real_dal)
    tenant_a = "tenant-cross-test-a"
    tenant_b = "tenant-cross-test-b"

    # Create page in tenant A
    page_a = await manager.create(
        tenant=tenant_a,
        name="Secret Page",
        markdown="# Tenant A Secret",
        created_by="user-a",
    )

    # Try to read from tenant B (should fail)
    page_b = await manager.get_by_id(tenant=tenant_b, page_id=page_a.id)

    assert page_b is None  # Cross-tenant read blocked


@pytest.mark.asyncio
async def test_cross_tenant_isolation_update(real_dal: Any):
    """Regression: page from tenant A not updatable by tenant B.

    regression: cross-tenant
    """
    manager = BlockPageManager(real_dal)
    tenant_a = "tenant-cross-test-a"
    tenant_b = "tenant-cross-test-b"

    # Create page in tenant A
    page_a = await manager.create(
        tenant=tenant_a,
        name="Secret Page",
        markdown="# Tenant A Secret",
        created_by="user-a",
    )

    # Try to update from tenant B (should fail)
    updated = await manager.update(
        tenant=tenant_b,
        page_id=page_a.id,
        markdown="# Hacked by Tenant B",
        updated_by="user-b",
    )

    assert updated is None  # Cross-tenant update blocked
