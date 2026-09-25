"""Data models for SASE blocklist verdicts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

IOC_TYPES = ("ip", "domain", "url", "hash")
SEVERITIES = ("low", "medium", "high", "critical")


@dataclass(slots=True)
class Verdict:
    """A verdict on an indicator of compromise.

    Represents a STIX-normalized IOC with provenance and TTL,
    stored in Valkey for O(1) lookup by Inspection Points.
    """

    ioc_type: str
    value: str
    severity: str
    source: str
    stix_id: str
    first_seen: int
    expiry: Optional[int]
