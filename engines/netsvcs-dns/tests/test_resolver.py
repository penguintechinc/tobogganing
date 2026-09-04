"""Tests for the async DNS resolver."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

# Add the app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.resolver import DNSResolver


class TestDNSResolver:
    """Test DNSResolver async resolution."""

    @pytest.fixture
    def resolver(self) -> DNSResolver:
        """Create resolver instance."""
        return DNSResolver(timeout=5.0, lifetime=5.0)

    @pytest.mark.asyncio
    async def test_resolve_success_a_record(self, resolver: DNSResolver) -> None:
        """Test successful A record resolution."""
        with patch("app.resolver.dns.asyncresolver.Resolver.resolve") as mock_resolve:
            # Mock dns.resolver.Answer
            mock_answer = AsyncMock()
            mock_answer.rrset.ttl = 300
            mock_answer.__iter__ = lambda self: iter([b"192.0.2.1"])
            mock_answer.__aiter__ = lambda self: self.__iter__()

            mock_resolve.return_value = mock_answer
            resolver.resolver.resolve = mock_resolve

            result = await resolver.resolve("example.com", "A")

            assert result["Status"] == 0  # NOERROR
            assert result["Question"] == [{"name": "example.com", "type": "A"}]
            assert len(result["Answer"]) == 1
            assert result["Answer"][0]["TTL"] == 300
            mock_resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_nxdomain(self, resolver: DNSResolver) -> None:
        """Test NXDOMAIN response."""
        import dns.resolver

        with patch("app.resolver.dns.asyncresolver.Resolver.resolve") as mock_resolve:
            mock_resolve.side_effect = dns.resolver.NXDOMAIN()
            resolver.resolver.resolve = mock_resolve

            result = await resolver.resolve("nonexistent.example.com", "A")

            assert result["Status"] == 3  # NXDOMAIN
            assert result["Question"] == [{"name": "nonexistent.example.com", "type": "A"}]
            assert result["Answer"] == []

    @pytest.mark.asyncio
    async def test_resolve_timeout(self, resolver: DNSResolver) -> None:
        """Test DNS query timeout."""
        import dns.resolver

        with patch("app.resolver.dns.asyncresolver.Resolver.resolve") as mock_resolve:
            mock_resolve.side_effect = dns.resolver.Timeout()
            resolver.resolver.resolve = mock_resolve

            result = await resolver.resolve("slow.example.com", "A")

            assert result["Status"] == 2  # SERVFAIL
            assert result["Question"] == [{"name": "slow.example.com", "type": "A"}]
            assert result["Answer"] == []

    @pytest.mark.asyncio
    async def test_resolve_no_answer(self, resolver: DNSResolver) -> None:
        """Test NoAnswer response (NOERROR but no Answer section)."""
        import dns.resolver

        with patch("app.resolver.dns.asyncresolver.Resolver.resolve") as mock_resolve:
            mock_resolve.side_effect = dns.resolver.NoAnswer()
            resolver.resolver.resolve = mock_resolve

            result = await resolver.resolve("example.com", "AAAA")

            assert result["Status"] == 0  # NOERROR
            assert result["Question"] == [{"name": "example.com", "type": "AAAA"}]
            assert result["Answer"] == []

    @pytest.mark.asyncio
    async def test_resolve_invalid_record_type(self, resolver: DNSResolver) -> None:
        """Test invalid record type."""
        result = await resolver.resolve("example.com", "INVALID_TYPE")

        assert result["Status"] == 2  # SERVFAIL
        assert result["Question"] == [{"name": "example.com", "type": "INVALID_TYPE"}]
        assert result["Answer"] == []

    @pytest.mark.asyncio
    async def test_resolve_generic_exception(self, resolver: DNSResolver) -> None:
        """Test generic exception handling."""
        with patch("app.resolver.dns.asyncresolver.Resolver.resolve") as mock_resolve:
            mock_resolve.side_effect = Exception("Some error")
            resolver.resolver.resolve = mock_resolve

            result = await resolver.resolve("example.com", "A")

            assert result["Status"] == 2  # SERVFAIL
            assert result["Answer"] == []

    def test_resolve_custom_zone_match(self, resolver: DNSResolver) -> None:
        """Test custom zone resolution with matching record."""
        zone_records = [
            {"name": "internal.example.com", "type": "A", "ttl": 300, "value": "10.0.0.1"},
            {"name": "internal.example.com", "type": "A", "ttl": 300, "value": "10.0.0.2"},
        ]

        result = resolver.resolve_custom_zone("internal.example.com", "A", zone_records)

        assert result["Status"] == 0  # NOERROR
        assert result["Question"] == [{"name": "internal.example.com", "type": "A"}]
        assert len(result["Answer"]) == 2
        assert result["Answer"][0]["data"] == "10.0.0.1"
        assert result["Answer"][1]["data"] == "10.0.0.2"

    def test_resolve_custom_zone_no_match(self, resolver: DNSResolver) -> None:
        """Test custom zone resolution with no matching record."""
        zone_records = [
            {"name": "internal.example.com", "type": "A", "ttl": 300, "value": "10.0.0.1"},
        ]

        result = resolver.resolve_custom_zone("other.example.com", "A", zone_records)

        assert result["Status"] == 3  # NXDOMAIN
        assert result["Answer"] == []

    def test_resolve_custom_zone_different_type(self, resolver: DNSResolver) -> None:
        """Test custom zone resolution with different record type."""
        zone_records = [
            {"name": "internal.example.com", "type": "A", "ttl": 300, "value": "10.0.0.1"},
        ]

        result = resolver.resolve_custom_zone("internal.example.com", "AAAA", zone_records)

        assert result["Status"] == 3  # NXDOMAIN
        assert result["Answer"] == []

    def test_resolve_custom_zone_default_ttl(self, resolver: DNSResolver) -> None:
        """Test custom zone uses default TTL when not specified."""
        zone_records = [
            {"name": "internal.example.com", "type": "A", "value": "10.0.0.1"},
        ]

        result = resolver.resolve_custom_zone("internal.example.com", "A", zone_records)

        assert result["Status"] == 0
        assert result["Answer"][0]["TTL"] == 300

    def test_resolve_custom_zone_empty_records(self, resolver: DNSResolver) -> None:
        """Test custom zone resolution with empty records list."""
        result = resolver.resolve_custom_zone("internal.example.com", "A", [])

        assert result["Status"] == 3  # NXDOMAIN
        assert result["Answer"] == []
