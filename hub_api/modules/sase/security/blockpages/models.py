"""Block page models for SASE enforcement customization."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PageStatus(str, Enum):
    """Status of a block page."""

    draft = "draft"
    live = "live"


class RouteDest(str, Enum):
    """Destination type for a block route."""

    page = "page"
    external = "external"


@dataclass(slots=True)
class RuleMetadata:
    """Governance metadata for block routes."""

    created_by: str
    updated_by: str | None = None
    ticket: str | None = None
    notes: str | None = None
    expiry: datetime | None = None
    review_date: datetime | None = None
    scope: str | None = None
    risk: str | None = None


@dataclass(slots=True)
class BlockPage:
    """A customizable markdown block page for enforcement actions.

    Stores markdown content with draft/live versioning and history tracking.
    """

    id: str
    tenant: str
    name: str
    markdown: str
    status: PageStatus
    version: int
    created_by: str
    updated_by: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class BlockRoute:
    """Routes a block source to a block page or external URL.

    Maps source_type (e.g., web-category:gambling, oob-analysis:malware)
    to either a page_id (served from hub-api) or external_url (redirect).
    Includes governance metadata for audit and compliance.
    """

    id: str
    tenant: str
    source_type: str
    destination_kind: RouteDest
    created_at: datetime = field(default_factory=datetime.utcnow)
    page_id: str | None = None
    external_url: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    ticket: str | None = None
    notes: str | None = None
    expiry: datetime | None = None
    review_date: datetime | None = None
    scope: str | None = None
    risk: str | None = None
