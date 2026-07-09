"""Module contract definitions for the registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from quart import Blueprint


@dataclass(slots=True)
class NavEntry:
    """Navigation entry for a module."""

    label: str
    path: str
    icon: Optional[str] = None


@dataclass(slots=True)
class Entitlement:
    """Feature entitlement tier specification."""

    feature: str
    tier: str  # "community", "professional", "enterprise"


@dataclass(slots=True)
class ModuleContext:
    """Context provided to modules at initialization."""

    config: object
    db: object
    key_provider: object


@dataclass(slots=True)
class ModuleContract:
    """Contract that a module must implement."""

    name: str
    blueprints: list[Blueprint] = field(default_factory=list)
    nav: list[NavEntry] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    entitlements: list[Entitlement] = field(default_factory=list)
    migrations: list[str] = field(default_factory=list)
    health: Optional[Callable] = None
