"""Real integration tests for SASE threat feeds using real_dal fixture."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from hub_api.modules.sase.security.feeds import (
    DetectionLogger,
    FeedSource,
    SecurityFeedsManager,
    ThreatType,
    build_threat_indicator,
)


@pytest.mark.asyncio
async def test_store_indicator_new_realdal(real_dal):
    """Test storing a new threat indicator via real database."""
    manager = SecurityFeedsManager(real_dal)
    tenant_id = str(uuid4())

    indicator = build_threat_indicator(
        indicator_type="domain",
        value="malicious-test-domain.com",
        threat_types=[ThreatType.MALWARE_DOMAIN, ThreatType.BLACKLISTED_DOMAIN],
        source=FeedSource.BLACKWEB,
        confidence=85,
        ttl=3600,
        metadata={"category": "malware", "test": True},
    )

    result = await manager._store_indicator(tenant_id, indicator)
    assert result is True

    # Verify indicator was inserted
    rows = await real_dal(
        (real_dal.threat_indicators.value == "malicious-test-domain.com")
        & (real_dal.threat_indicators.tenant_id == tenant_id)
    ).select()

    assert len(rows) > 0
    row = rows.first() if hasattr(rows, "first") else rows[0]
    assert row["value"] == "malicious-test-domain.com"
    assert row["tenant_id"] == tenant_id
    assert row["indicator_type"] == "domain"
    assert row["confidence"] == 85


@pytest.mark.asyncio
async def test_store_indicator_update_existing(real_dal):
    """Test updating an existing threat indicator."""
    manager = SecurityFeedsManager(real_dal)
    tenant_id = str(uuid4())
    value = "update-test-domain.com"

    # Insert initial indicator
    indicator1 = build_threat_indicator(
        indicator_type="domain",
        value=value,
        threat_types=[ThreatType.MALWARE_DOMAIN],
        source=FeedSource.SPAMHAUS,
        confidence=80,
        ttl=3600,
        metadata={"version": "1"},
    )
    result1 = await manager._store_indicator(tenant_id, indicator1)
    assert result1 is True

    # Update with new indicator
    indicator2 = build_threat_indicator(
        indicator_type="domain",
        value=value,
        threat_types=[ThreatType.MALWARE_DOMAIN, ThreatType.PHISHING_DOMAIN],
        source=FeedSource.SPAMHAUS,
        confidence=95,
        ttl=3600,
        metadata={"version": "2"},
    )
    result2 = await manager._store_indicator(tenant_id, indicator2)
    assert result2 is False  # Existing record

    # Verify updated indicator
    rows = await real_dal(
        (real_dal.threat_indicators.value == value)
        & (real_dal.threat_indicators.tenant_id == tenant_id)
    ).select()

    assert len(rows) > 0
    row = rows.first() if hasattr(rows, "first") else rows[0]
    assert row["confidence"] == 95


@pytest.mark.asyncio
async def test_detection_round_trip(real_dal):
    """Test recording threat detection via real database."""
    logger = DetectionLogger(real_dal)
    tenant_id = str(uuid4())

    threat_details = [
        {
            "value": "malicious.com",
            "threat_types": ["malware_domain"],
            "source": "blackweb",
            "confidence": 85,
        }
    ]

    detection_id = await logger.log_threat_detection(
        tenant_id=tenant_id,
        client_ip="192.168.1.100",
        requested_domain="malicious.com",
        action_taken="blocked",
        threat_details=threat_details,
    )

    assert detection_id != ""

    # Verify detection was recorded
    rows = await real_dal(
        (real_dal.threat_detections.id == detection_id)
        & (real_dal.threat_detections.tenant_id == tenant_id)
    ).select()

    assert len(rows) > 0
    row = rows.first() if hasattr(rows, "first") else rows[0]
    assert row["client_ip"] == "192.168.1.100"
    assert row["requested_domain"] == "malicious.com"
    assert row["action_taken"] == "blocked"
    assert row["tenant_id"] == tenant_id


@pytest.mark.asyncio
async def test_check_threat_indicator_found(real_dal):
    """Test checking for a known threat indicator."""
    manager = SecurityFeedsManager(real_dal)
    tenant_id = str(uuid4())
    domain = "known-threat.com"

    # Insert a threat indicator
    indicator = build_threat_indicator(
        indicator_type="domain",
        value=domain,
        threat_types=[ThreatType.MALWARE_DOMAIN],
        source=FeedSource.BLACKWEB,
        confidence=90,
        ttl=3600,
        metadata={"test": True},
    )
    await manager._store_indicator(tenant_id, indicator)

    # Check for threat
    is_threat, details = await manager.check_threat_indicator(tenant_id, domain)

    assert is_threat is True
    assert len(details) > 0
    assert details[0]["value"] == domain
    assert details[0]["confidence"] == 90
    assert details[0]["source"] == FeedSource.BLACKWEB.value


@pytest.mark.asyncio
async def test_check_threat_indicator_not_found(real_dal):
    """Test checking for unknown threat indicator."""
    manager = SecurityFeedsManager(real_dal)
    tenant_id = str(uuid4())

    is_threat, details = await manager.check_threat_indicator(
        tenant_id, "unknown-safe-domain.com"
    )

    assert is_threat is False
    assert len(details) == 0


@pytest.mark.asyncio
async def test_threat_statistics_count(real_dal):
    """Test threat statistics reporting via real database."""
    logger = DetectionLogger(real_dal)
    tenant_id = str(uuid4())

    # Record multiple detections
    for i in range(3):
        await logger.log_threat_detection(
            tenant_id=tenant_id,
            client_ip=f"192.168.1.{100 + i}",
            requested_domain=f"threat-{i}.com",
            action_taken="blocked",
            threat_details=[],
        )

    # Get statistics
    stats = await logger.get_threat_statistics(tenant_id, hours_back=24)

    assert stats["period_hours"] == 24
    assert stats["total_detections"] >= 3


@pytest.mark.asyncio
async def test_tenant_scoping_isolation(real_dal):
    """Test that threat data is properly tenant-scoped."""
    manager = SecurityFeedsManager(real_dal)
    tenant1 = str(uuid4())
    tenant2 = str(uuid4())
    domain = "tenant-isolated-threat.com"

    # Insert indicator for tenant1
    indicator = build_threat_indicator(
        indicator_type="domain",
        value=domain,
        threat_types=[ThreatType.MALWARE_DOMAIN],
        source=FeedSource.BLACKWEB,
        confidence=85,
        ttl=3600,
        metadata={"tenant": "1"},
    )
    await manager._store_indicator(tenant1, indicator)

    # Check from tenant2 should not find it
    is_threat, details = await manager.check_threat_indicator(tenant2, domain)
    assert is_threat is False
    assert len(details) == 0

    # Check from tenant1 should find it
    is_threat, details = await manager.check_threat_indicator(tenant1, domain)
    assert is_threat is True
    assert len(details) > 0


@pytest.mark.asyncio
async def test_feed_update_status_tracking(real_dal):
    """Test feed update status tracking via real database."""
    manager = SecurityFeedsManager(real_dal)
    tenant_id = str(uuid4())
    update_id = str(uuid4())

    # Record feed update start
    now = datetime.now(timezone.utc)
    await real_dal.feed_updates.async_insert(
        id=update_id,
        tenant_id=tenant_id,
        source=FeedSource.BLACKWEB.value,
        update_type="automatic",
        status="running",
        started_at=now,
        created_at=now,
    )

    # Update to completed
    duration = 120
    await real_dal(
        (real_dal.feed_updates.id == update_id)
        & (real_dal.feed_updates.tenant_id == tenant_id)
    ).update(
        status="completed",
        indicators_added=5,
        indicators_updated=2,
        indicators_removed=1,
        duration_seconds=duration,
        completed_at=datetime.now(timezone.utc),
    )

    # Verify update
    rows = await real_dal(
        (real_dal.feed_updates.id == update_id)
        & (real_dal.feed_updates.tenant_id == tenant_id)
    ).select()

    assert len(rows) > 0
    row = rows.first() if hasattr(rows, "first") else rows[0]
    assert row["status"] == "completed"
    assert row["indicators_added"] == 5
    assert row["indicators_updated"] == 2
