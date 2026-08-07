"""Test SASE BlockRouteManager with real DAL."""
from __future__ import annotations

import pytest
from typing import Any
from datetime import datetime

from hub_api.modules.sase.security.blockpages.routes import BlockRouteManager
from hub_api.modules.sase.security.blockpages.models import RouteDest


@pytest.mark.asyncio
async def test_set_route_page(real_dal: Any):
    """Test setting a route to a block page."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"

    route = await manager.set_route(
        tenant=tenant,
        source_type="web-category:gambling",
        destination_kind=RouteDest.page,
        page_id="page-123",
        metadata={
            "created_by": "user-123",
            "ticket": "TICKET-001",
            "notes": "Block gambling sites",
        },
    )

    assert route.id is not None
    assert route.tenant == tenant
    assert route.source_type == "web-category:gambling"
    assert route.destination_kind == RouteDest.page
    assert route.page_id == "page-123"
    assert route.external_url is None
    assert route.ticket == "TICKET-001"
    assert route.notes == "Block gambling sites"


@pytest.mark.asyncio
async def test_set_route_external(real_dal: Any):
    """Test setting a route to an external URL."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"

    route = await manager.set_route(
        tenant=tenant,
        source_type="custom-rule:malware",
        destination_kind=RouteDest.external,
        external_url="https://customer.example.com/block",
        metadata={"created_by": "user-123"},
    )

    assert route.destination_kind == RouteDest.external
    assert route.external_url == "https://customer.example.com/block"
    assert route.page_id is None


@pytest.mark.asyncio
async def test_resolve_exact_match(real_dal: Any):
    """Test resolving a route with exact source type match."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"

    # Create a route
    await manager.set_route(
        tenant=tenant,
        source_type="web-category:gambling",
        destination_kind=RouteDest.page,
        page_id="page-123",
        metadata={"created_by": "user-123"},
    )

    # Resolve it
    resolved = await manager.resolve(tenant=tenant, source_type="web-category:gambling")

    assert resolved is not None
    assert resolved.source_type == "web-category:gambling"
    assert resolved.page_id == "page-123"


@pytest.mark.asyncio
async def test_resolve_default_fallback(real_dal: Any):
    """Test resolving falls back to global default if source type not found."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"

    # Create a default route
    await manager.set_route(
        tenant=tenant,
        source_type="default",
        destination_kind=RouteDest.page,
        page_id="default-page",
        metadata={"created_by": "user-123"},
    )

    # Resolve an unknown source type (should get default)
    resolved = await manager.resolve(tenant=tenant, source_type="unknown-category")

    assert resolved is not None
    assert resolved.source_type == "default"
    assert resolved.page_id == "default-page"


@pytest.mark.asyncio
async def test_resolve_not_found(real_dal: Any):
    """Test resolving returns None if no route or default exists."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"

    resolved = await manager.resolve(tenant=tenant, source_type="nonexistent")

    assert resolved is None


@pytest.mark.asyncio
async def test_get_routes(real_dal: Any):
    """Test listing all routes for a tenant."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"

    route1 = await manager.set_route(
        tenant=tenant,
        source_type="web-category:gambling",
        destination_kind=RouteDest.page,
        page_id="page-1",
        metadata={"created_by": "user-123"},
    )

    route2 = await manager.set_route(
        tenant=tenant,
        source_type="web-category:adult",
        destination_kind=RouteDest.page,
        page_id="page-2",
        metadata={"created_by": "user-123"},
    )

    routes = await manager.get_routes(tenant=tenant)

    assert len(routes) >= 2
    source_types = [r.source_type for r in routes]
    assert "web-category:gambling" in source_types
    assert "web-category:adult" in source_types


@pytest.mark.asyncio
async def test_governance_metadata(real_dal: Any):
    """Test that governance metadata is properly stored and retrieved."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"
    now = datetime.utcnow()

    route = await manager.set_route(
        tenant=tenant,
        source_type="oob-analysis:malware",
        destination_kind=RouteDest.page,
        page_id="page-123",
        metadata={
            "created_by": "user-123",
            "updated_by": "user-456",
            "ticket": "TICKET-001",
            "notes": "Malware blocking rule",
            "expiry": now,
            "review_date": now,
            "scope": "tenant",
            "risk": "critical",
        },
    )

    assert route.created_by == "user-123"
    assert route.updated_by == "user-456"
    assert route.ticket == "TICKET-001"
    assert route.notes == "Malware blocking rule"
    assert route.scope == "tenant"
    assert route.risk == "critical"


@pytest.mark.asyncio
async def test_cross_tenant_isolation(real_dal: Any):
    """Regression: routes from tenant A not visible to tenant B.

    regression: cross-tenant
    """
    manager = BlockRouteManager(real_dal)
    tenant_a = "tenant-cross-route-a"
    tenant_b = "tenant-cross-route-b"

    # Create route in tenant A
    await manager.set_route(
        tenant=tenant_a,
        source_type="secret-category",
        destination_kind=RouteDest.page,
        page_id="secret-page",
        metadata={"created_by": "user-a"},
    )

    # Try to resolve from tenant B (should not see it)
    resolved = await manager.resolve(tenant=tenant_b, source_type="secret-category")

    assert resolved is None  # Cross-tenant read blocked


@pytest.mark.asyncio
async def test_update_route(real_dal: Any):
    """Test updating an existing route."""
    manager = BlockRouteManager(real_dal)
    tenant = "tenant-route-test-a"

    # Create initial route
    await manager.set_route(
        tenant=tenant,
        source_type="web-category:gambling",
        destination_kind=RouteDest.page,
        page_id="page-1",
        metadata={"created_by": "user-123"},
    )

    # Update it
    updated = await manager.set_route(
        tenant=tenant,
        source_type="web-category:gambling",
        destination_kind=RouteDest.external,
        external_url="https://new.example.com/block",
        metadata={
            "created_by": "user-123",
            "updated_by": "user-456",
            "notes": "Updated to external redirect",
        },
    )

    assert updated.destination_kind == RouteDest.external
    assert updated.external_url == "https://new.example.com/block"
    assert updated.page_id is None
    assert updated.updated_by == "user-456"
