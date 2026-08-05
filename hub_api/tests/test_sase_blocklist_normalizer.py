"""Tests for SASE blocklist STIX normalizer."""
from __future__ import annotations

import stix2
import pytest

from hub_api.modules.sase.security.blocklist.stix_normalizer import to_stix_indicator


def test_ip_indicator_pattern() -> None:
    """Test IP indicator generates correct STIX pattern."""
    ind = to_stix_indicator(
        "ip", "1.2.3.4", severity="high", source="spamhaus", first_seen=1000
    )
    assert ind.pattern == "[ipv4-addr:value = '1.2.3.4']"
    assert "malicious-activity" in ind.labels
    # Verify round-trip via stix2.parse
    parsed = stix2.parse(ind.serialize())
    assert parsed.id == ind.id


def test_domain_indicator_pattern() -> None:
    """Test domain indicator generates correct STIX pattern."""
    ind = to_stix_indicator(
        "domain", "bad.com", severity="low", source="ut1", first_seen=1
    )
    assert ind.pattern == "[domain-name:value = 'bad.com']"


def test_hash_indicator_pattern() -> None:
    """Test hash indicator generates correct STIX pattern."""
    hash_val = "a" * 64
    ind = to_stix_indicator(
        "hash", hash_val, severity="critical", source="strelka", first_seen=1
    )
    assert ind.pattern == f"[file:hashes.'SHA-256' = '{hash_val}']"


def test_url_indicator_pattern() -> None:
    """Test URL indicator generates correct STIX pattern."""
    ind = to_stix_indicator(
        "url", "http://x/y", severity="medium", source="urlhaus", first_seen=1
    )
    assert ind.pattern == "[url:value = 'http://x/y']"


def test_severity_to_confidence_mapping() -> None:
    """Test severity values map to correct confidence levels."""
    test_cases = [
        ("low", 15),
        ("medium", 50),
        ("high", 75),
        ("critical", 95),
    ]
    for severity, expected_confidence in test_cases:
        ind = to_stix_indicator(
            "ip", "1.2.3.4", severity=severity, source="test", first_seen=1000
        )
        assert ind.confidence == expected_confidence


def test_stix_round_trip() -> None:
    """Test STIX indicators serialize and parse correctly."""
    ind = to_stix_indicator(
        "domain", "malware.com", severity="high", source="spamhaus", first_seen=1000
    )
    serialized = ind.serialize()
    parsed = stix2.parse(serialized)
    assert parsed.id == ind.id
    assert parsed.pattern == ind.pattern
    assert parsed.labels == ind.labels
