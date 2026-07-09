"""Tests for SASE threat feeds module."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.modules.sase.security.feeds import (
    DetectionLogger,
    FeedSource,
    SecurityFeedsManager,
    ThreatIndicatorData,
    ThreatType,
    build_threat_indicator,
    parse_blackweb_domains,
    parse_blackweb_ips,
    parse_spamhaus_drop,
)


@pytest.fixture
def mock_db():
    """Create a mocked penguin-dal instance."""
    db = MagicMock()

    # Mock tables
    db.threat_indicators = MagicMock()
    db.feed_updates = MagicMock()
    db.threat_detections = MagicMock()

    # Mock insert/update/select - return coroutines
    async def mock_insert(*args, **kwargs):
        return "id-123"

    async def mock_select(*args, **kwargs):
        return []

    async def mock_count(*args, **kwargs):
        return 0

    async def mock_update(*args, **kwargs):
        pass

    db.threat_indicators.async_insert = AsyncMock(side_effect=mock_insert)
    db.feed_updates.async_insert = AsyncMock(side_effect=mock_insert)
    db.threat_detections.async_insert = AsyncMock(side_effect=mock_insert)

    # Mock the call() pattern to return a query-like object
    def query_mock(*args, **kwargs):
        query_obj = MagicMock()
        query_obj.async_select = AsyncMock(return_value=[])
        query_obj.async_count = AsyncMock(return_value=0)
        query_obj.async_update = AsyncMock(side_effect=mock_update)
        return query_obj

    db.side_effect = query_mock
    db.return_value.async_select = AsyncMock(return_value=[])
    db.return_value.async_count = AsyncMock(return_value=0)
    db.return_value.async_update = AsyncMock(side_effect=mock_update)

    return db


class TestParsers:
    """Test feed parsers."""

    def test_parse_blackweb_domains(self) -> None:
        """Test Blackweb domain parsing."""
        content = """
# Comment
||example.com^
||bad-site.net^
malicious.org
"""
        domains = parse_blackweb_domains(content)
        assert "example.com" in domains
        assert "bad-site.net" in domains
        assert len(domains) >= 2

    def test_parse_blackweb_ips(self) -> None:
        """Test Blackweb IP parsing."""
        content = """
# Comment
192.168.1.0/24
10.0.0.0/8
1.1.1.1
invalid
"""
        ips = parse_blackweb_ips(content)
        assert "192.168.1.0/24" in ips
        assert "10.0.0.0/8" in ips
        assert "1.1.1.1" in ips
        assert "invalid" not in ips

    def test_parse_spamhaus_drop(self) -> None:
        """Test Spamhaus DROP format parsing."""
        content = """
; Some comment
2.4.6.0/24 ; SBL123456
192.0.2.0/24 ; Spamhaus
10.20.30.0/24 ; Another entry
"""
        networks = parse_spamhaus_drop(content)
        assert "2.4.6.0/24" in networks
        assert "192.0.2.0/24" in networks
        assert "10.20.30.0/24" in networks


class TestThreatIndicator:
    """Test threat indicator data structures."""

    def test_build_threat_indicator(self) -> None:
        """Test building a threat indicator."""
        indicator = build_threat_indicator(
            indicator_type="domain",
            value="malicious.example.com",
            threat_types=[ThreatType.MALWARE_DOMAIN],
            source=FeedSource.BLACKWEB,
            confidence=85,
            ttl=3600,
            metadata={"category": "malware"},
        )

        assert indicator.indicator_type == "domain"
        assert indicator.value == "malicious.example.com"
        assert ThreatType.MALWARE_DOMAIN in indicator.threat_types
        assert indicator.source == FeedSource.BLACKWEB
        assert indicator.confidence == 85
        assert indicator.ttl == 3600


class TestSecurityFeedsManager:
    """Test SecurityFeedsManager."""

    @pytest.mark.asyncio
    async def test_init(self, mock_db: AsyncMock) -> None:
        """Test manager initialization."""
        manager = SecurityFeedsManager(mock_db)

        assert manager.db == mock_db
        assert manager.detection_logger is not None
        assert FeedSource.BLACKWEB in manager.feed_configs
        assert FeedSource.SPAMHAUS in manager.feed_configs

    @pytest.mark.asyncio
    async def test_store_indicator_new(self, mock_db: MagicMock) -> None:
        """Test storing a new indicator."""
        mock_db.return_value.async_select = AsyncMock(return_value=[])

        manager = SecurityFeedsManager(mock_db)
        indicator = build_threat_indicator(
            indicator_type="domain",
            value="test.com",
            threat_types=[ThreatType.MALWARE_DOMAIN],
            source=FeedSource.BLACKWEB,
            confidence=85,
            ttl=3600,
        )

        result = await manager._store_indicator("tenant-1", indicator)
        assert result is True
        mock_db.threat_indicators.async_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_threat_indicator_structure(self, mock_db: MagicMock) -> None:
        """Test checking for threat indicator returns correct structure."""
        manager = SecurityFeedsManager(mock_db)

        # Setup mock to return empty (no threats found)
        mock_db.return_value.async_select = AsyncMock(return_value=[])

        is_threat, details = await manager.check_threat_indicator(
            "tenant-1", "unknown.com"
        )

        # Should return tuple of (bool, list)
        assert isinstance(is_threat, bool)
        assert isinstance(details, list)
        assert is_threat is False  # Should be no threat
        assert len(details) == 0

    @pytest.mark.asyncio
    async def test_check_threat_indicator_not_found(self, mock_db: MagicMock) -> None:
        """Test checking for threat indicator (not found)."""
        mock_db.return_value.async_select = AsyncMock(return_value=[])

        manager = SecurityFeedsManager(mock_db)
        is_threat, details = await manager.check_threat_indicator(
            "tenant-1", "safe.com"
        )

        assert is_threat is False
        assert len(details) == 0

    @pytest.mark.asyncio
    async def test_check_threat_indicator_with_ip(self, mock_db: MagicMock) -> None:
        """Test checking threat indicator with IP address."""
        mock_db.return_value.async_select = AsyncMock(return_value=[])

        manager = SecurityFeedsManager(mock_db)
        is_threat, details = await manager.check_threat_indicator(
            "tenant-1", "192.0.2.1"
        )

        assert isinstance(is_threat, bool)
        assert isinstance(details, list)


class TestDetectionLogger:
    """Test DetectionLogger."""

    @pytest.mark.asyncio
    async def test_init(self, mock_db: AsyncMock) -> None:
        """Test detection logger initialization."""
        logger = DetectionLogger(mock_db)
        assert logger.db == mock_db

    @pytest.mark.asyncio
    async def test_log_threat_detection(self, mock_db: AsyncMock) -> None:
        """Test logging a threat detection."""
        logger = DetectionLogger(mock_db)
        threat_details = [
            {
                "value": "malicious.com",
                "threat_types": ["malware_domain"],
                "source": "blackweb",
                "confidence": 85,
            }
        ]

        detection_id = await logger.log_threat_detection(
            tenant_id="tenant-1",
            client_ip="192.168.1.100",
            requested_domain="malicious.com",
            action_taken="blocked",
            threat_details=threat_details,
        )

        assert detection_id != ""
        mock_db.threat_detections.async_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_threat_statistics(self, mock_db: MagicMock) -> None:
        """Test getting threat statistics."""
        mock_db.return_value.async_count = AsyncMock(return_value=5)

        logger = DetectionLogger(mock_db)
        stats = await logger.get_threat_statistics("tenant-1", hours_back=24)

        assert stats["period_hours"] == 24
        assert "total_detections" in stats
        assert "action_counts" in stats
        assert "active_indicators" in stats


class TestFeedUpdate:
    """Test feed update operations."""

    @pytest.mark.asyncio
    async def test_update_feed_stats(self, mock_db: AsyncMock) -> None:
        """Test feed update returns statistics."""
        manager = SecurityFeedsManager(mock_db)

        # Mock feed sources to return no results
        with patch(
            "core.modules.sase.security.feeds.manager.fetch_blackweb_domains",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with patch(
                "core.modules.sase.security.feeds.manager.fetch_blackweb_ips",
                new_callable=AsyncMock,
                return_value=[],
            ):
                stats = await manager._update_blackweb_feed("tenant-1")

        assert isinstance(stats, dict)
        assert "added" in stats
        assert "updated" in stats
        assert "removed" in stats
        assert "errors" in stats

    @pytest.mark.asyncio
    async def test_tenant_scoping(self, mock_db: MagicMock) -> None:
        """Test that operations are tenant-scoped."""
        mock_db.return_value.async_select = AsyncMock(return_value=[])

        manager = SecurityFeedsManager(mock_db)
        await manager.check_threat_indicator("tenant-scoped", "test.com")

        # Verify db was called
        assert mock_db.called
