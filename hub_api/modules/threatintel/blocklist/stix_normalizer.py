"""Normalize IOCs to STIX 2.1 Indicators."""
from __future__ import annotations

from datetime import datetime, timezone

import stix2

from .models import SEVERITIES

# Severity to confidence mapping
SEVERITY_TO_CONFIDENCE = {
    "low": 15,
    "medium": 50,
    "high": 75,
    "critical": 95,
}


def to_stix_indicator(
    ioc_type: str, value: str, *, severity: str, source: str, first_seen: int
) -> stix2.Indicator:
    """Normalize an IOC to a STIX 2.1 Indicator.

    Builds the correct STIX pattern per IOC type and includes
    severity-derived confidence, feed source reference, and
    creation timestamp.
    """
    # Map IOC type to STIX pattern
    if ioc_type == "ip":
        pattern = f"[ipv4-addr:value = '{value}']"
    elif ioc_type == "domain":
        pattern = f"[domain-name:value = '{value}']"
    elif ioc_type == "url":
        pattern = f"[url:value = '{value}']"
    elif ioc_type == "hash":
        pattern = f"[file:hashes.'SHA-256' = '{value}']"
    else:
        raise ValueError(f"unsupported ioc_type: {ioc_type}")

    # Convert first_seen timestamp to datetime
    valid_from = datetime.fromtimestamp(first_seen, tz=timezone.utc)

    # Map severity to confidence
    confidence = SEVERITY_TO_CONFIDENCE.get(severity, 50)

    # Build the indicator
    indicator = stix2.Indicator(
        pattern=pattern,
        pattern_type="stix",
        labels=["malicious-activity"],
        confidence=confidence,
        valid_from=valid_from,
        external_references=[
            {
                "source_name": source,
                "url": f"https://{source}.invalid",
            }
        ],
    )

    return indicator
