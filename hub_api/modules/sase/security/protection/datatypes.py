"""Data structures for security protection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class RateLimitRuleData:
    """Rate limiting rule configuration."""

    name: str
    max_requests: int
    window_seconds: int
    block_duration: int = 300
    endpoints: list[str] | None = None
    exempt_ips: list[str] | None = None
    priority: int = 10


@dataclass(slots=True)
class SecurityEventData:
    """Security event for logging and analysis."""

    event_type: str
    ip_address: str
    endpoint: str
    user_agent: str
    timestamp: datetime
    severity: str
    details: dict[str, Any]
    tenant_id: str | None = None
