"""Test SASE block pages data models."""
from __future__ import annotations

import pytest
from datetime import datetime

from hub_api.modules.sase.security.blockpages.models import (
    BlockPage,
    BlockRoute,
    PageStatus,
    RouteDest,
    RuleMetadata,
)


def test_page_status_enum():
    """Test PageStatus enum values."""
    assert PageStatus.draft.value == "draft"
    assert PageStatus.live.value == "live"


def test_route_dest_enum():
    """Test RouteDest enum values."""
    assert RouteDest.page.value == "page"
    assert RouteDest.external.value == "external"


def test_rule_metadata_construction():
    """Test RuleMetadata dataclass construction."""
    now = datetime.utcnow()
    metadata = RuleMetadata(
        created_by="user-123",
        updated_by="user-456",
        ticket="TICKET-001",
        notes="Test metadata",
        expiry=now,
        review_date=now,
        scope="global",
        risk="high",
    )

    assert metadata.created_by == "user-123"
    assert metadata.updated_by == "user-456"
    assert metadata.ticket == "TICKET-001"
    assert metadata.notes == "Test metadata"
    assert metadata.expiry == now
    assert metadata.review_date == now
    assert metadata.scope == "global"
    assert metadata.risk == "high"


def test_block_page_construction():
    """Test BlockPage dataclass construction."""
    now = datetime.utcnow()
    page = BlockPage(
        id="page-123",
        tenant="tenant-abc",
        name="Default Block Page",
        markdown="# Blocked\nYour request was blocked.",
        status=PageStatus.draft,
        version=1,
        created_by="user-123",
        updated_by="user-456",
        created_at=now,
        updated_at=now,
    )

    assert page.id == "page-123"
    assert page.tenant == "tenant-abc"
    assert page.name == "Default Block Page"
    assert page.markdown == "# Blocked\nYour request was blocked."
    assert page.status == PageStatus.draft
    assert page.version == 1
    assert page.created_by == "user-123"
    assert page.updated_by == "user-456"


def test_block_page_defaults():
    """Test BlockPage dataclass default values."""
    page = BlockPage(
        id="page-123",
        tenant="tenant-abc",
        name="Default Page",
        markdown="# Blocked",
        status=PageStatus.live,
        version=2,
        created_by="user-123",
    )

    assert page.updated_by is None
    assert page.created_at is not None
    assert page.updated_at is not None


def test_block_route_construction():
    """Test BlockRoute dataclass construction."""
    now = datetime.utcnow()
    route = BlockRoute(
        id="route-123",
        tenant="tenant-abc",
        source_type="web-category:gambling",
        destination_kind=RouteDest.page,
        page_id="page-123",
        external_url=None,
        created_at=now,
        created_by="user-123",
        updated_by="user-456",
        ticket="TICKET-001",
        notes="Gambling category block",
        expiry=now,
        review_date=now,
        scope="tenant",
        risk="medium",
    )

    assert route.id == "route-123"
    assert route.tenant == "tenant-abc"
    assert route.source_type == "web-category:gambling"
    assert route.destination_kind == RouteDest.page
    assert route.page_id == "page-123"
    assert route.external_url is None
    assert route.created_by == "user-123"
    assert route.ticket == "TICKET-001"


def test_block_route_external():
    """Test BlockRoute with external URL destination."""
    route = BlockRoute(
        id="route-456",
        tenant="tenant-abc",
        source_type="custom-rule:malware",
        destination_kind=RouteDest.external,
        external_url="https://customer.example.com/block-page",
        created_by="user-123",
    )

    assert route.destination_kind == RouteDest.external
    assert route.external_url == "https://customer.example.com/block-page"
    assert route.page_id is None


def test_block_route_defaults():
    """Test BlockRoute dataclass default values."""
    route = BlockRoute(
        id="route-123",
        tenant="tenant-abc",
        source_type="web-category:adult",
        destination_kind=RouteDest.page,
    )

    assert route.page_id is None
    assert route.external_url is None
    assert route.created_by is None
    assert route.updated_by is None
    assert route.ticket is None
    assert route.notes is None
    assert route.expiry is None
    assert route.review_date is None
    assert route.scope is None
    assert route.risk is None
    assert route.created_at is not None


def test_block_page_slots():
    """Test that BlockPage uses slots for memory efficiency."""
    page = BlockPage(
        id="page-123",
        tenant="tenant-abc",
        name="Test Page",
        markdown="# Blocked",
        status=PageStatus.draft,
        version=1,
        created_by="user-123",
    )

    # Slots-enabled classes should not have __dict__
    assert not hasattr(page, "__dict__")


def test_block_route_slots():
    """Test that BlockRoute uses slots for memory efficiency."""
    route = BlockRoute(
        id="route-123",
        tenant="tenant-abc",
        source_type="web-category:gambling",
        destination_kind=RouteDest.page,
    )

    # Slots-enabled classes should not have __dict__
    assert not hasattr(route, "__dict__")
