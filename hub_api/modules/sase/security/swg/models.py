"""Data models for SASE SWG category filtering and policy resolution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hub_api.modules.sase.security.enforcement import EnforcementAction

__all__ = ["DomainCategory", "CategoryPolicy", "LookupResult"]


@dataclass(slots=True)
class DomainCategory:
    """A domain associated with one or more security categories.

    Represents the mapping of a domain to its security categories,
    sourced from either feeds or custom admin definitions.
    """

    id: str
    domain: str
    categories: tuple[str, ...]
    source: str
    tenant: str | None
    updated_at: datetime


@dataclass(slots=True)
class CategoryPolicy:
    """Policy mapping a security category to an enforcement action.

    Defines what action to take when a domain in a specific category
    is accessed by a user/group/tenant.
    """

    id: str
    tenant: str
    scope: str
    scope_id: str | None
    category: str
    action: EnforcementAction
    created_at: datetime


@dataclass(slots=True)
class LookupResult:
    """Result of domain lookup in the SWG category filter.

    Contains the domain, its categories (if found), the resolved
    enforcement action, the scope that matched, and whether the domain
    was uncategorized.
    """

    domain: str
    categories: tuple[str, ...] | None
    action: EnforcementAction
    matched_scope: str
    uncategorized: bool
