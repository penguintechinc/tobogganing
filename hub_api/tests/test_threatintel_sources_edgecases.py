"""Edge-case tests for feeds/sources.py parsers and fetchers.

Complements tests/test_sase_feeds.py::TestParsers (happy-path parsing) with
the malformed-line skip branch and the async fetch_*/query_dnsbl functions,
which were entirely untested (they require a session/DNS resolver).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.threatintel.feeds.sources import (
    fetch_blackweb_domains,
    fetch_blackweb_ips,
    fetch_spamhaus_drop,
    parse_spamhaus_drop,
    query_dnsbl,
)


def test_parse_spamhaus_drop_skips_invalid_network() -> None:
    """parse_spamhaus_drop() skips lines that aren't valid IP networks."""
    content = """
; comment
not-a-network ; invalid
2.4.6.0/24 ; valid
"""
    networks = parse_spamhaus_drop(content)
    assert networks == ["2.4.6.0/24"]


def _mock_response(status: int, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(response: MagicMock) -> MagicMock:
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    return session


@pytest.mark.asyncio
async def test_fetch_blackweb_domains_success() -> None:
    """fetch_blackweb_domains() parses a 200 response body."""
    session = _mock_session(_mock_response(200, "||evil.example.com^\n"))

    domains = await fetch_blackweb_domains(session, "https://example.com/feed")

    assert "evil.example.com" in domains


@pytest.mark.asyncio
async def test_fetch_blackweb_domains_non_200_raises() -> None:
    """fetch_blackweb_domains() raises on a non-200 response (fail-open at caller)."""
    session = _mock_session(_mock_response(503))

    with pytest.raises(Exception):
        await fetch_blackweb_domains(session, "https://example.com/feed")


@pytest.mark.asyncio
async def test_fetch_blackweb_ips_success() -> None:
    """fetch_blackweb_ips() parses a 200 response body."""
    session = _mock_session(_mock_response(200, "10.0.0.0/8\n"))

    ips = await fetch_blackweb_ips(session, "https://example.com/ips")

    assert "10.0.0.0/8" in ips


@pytest.mark.asyncio
async def test_fetch_blackweb_ips_non_200_raises() -> None:
    """fetch_blackweb_ips() raises on a non-200 response."""
    session = _mock_session(_mock_response(500))

    with pytest.raises(Exception):
        await fetch_blackweb_ips(session, "https://example.com/ips")


@pytest.mark.asyncio
async def test_fetch_spamhaus_drop_success() -> None:
    """fetch_spamhaus_drop() parses a 200 response body."""
    session = _mock_session(_mock_response(200, "2.4.6.0/24 ; SBL1\n"))

    networks = await fetch_spamhaus_drop(session, "https://example.com/drop.txt")

    assert "2.4.6.0/24" in networks


@pytest.mark.asyncio
async def test_fetch_spamhaus_drop_non_200_raises() -> None:
    """fetch_spamhaus_drop() raises on a non-200 response."""
    session = _mock_session(_mock_response(404))

    with pytest.raises(Exception):
        await fetch_spamhaus_drop(session, "https://example.com/drop.txt")


@pytest.mark.asyncio
async def test_fetch_blackweb_domains_network_error_raises_and_logs() -> None:
    """fetch_blackweb_domains() re-raises on a network-level exception."""
    session = MagicMock()
    session.get = MagicMock(side_effect=RuntimeError("connection refused"))

    with pytest.raises(RuntimeError):
        await fetch_blackweb_domains(session, "https://example.com/feed")


@pytest.mark.asyncio
async def test_query_dnsbl_provider_hit() -> None:
    """query_dnsbl() records a provider whose reverse-DNS query resolves."""
    with patch("hub_api.modules.threatintel.feeds.sources.dns.resolver.resolve") as mock_resolve:
        mock_resolve.return_value = MagicMock()

        results = await query_dnsbl("192.0.2.1", ["zen.spamhaus.org"])

    assert results == ["zen.spamhaus.org"]


@pytest.mark.asyncio
async def test_query_dnsbl_provider_miss_on_nxdomain() -> None:
    """query_dnsbl() skips providers whose query raises NXDOMAIN."""
    import dns.resolver as dns_resolver

    with patch(
        "hub_api.modules.threatintel.feeds.sources.dns.resolver.resolve",
        side_effect=dns_resolver.NXDOMAIN(),
    ):
        results = await query_dnsbl("192.0.2.1", ["zen.spamhaus.org", "bl.spamcop.net"])

    assert results == []


@pytest.mark.asyncio
async def test_query_dnsbl_invalid_ip_returns_empty() -> None:
    """query_dnsbl() fails open (empty list) for an unparseable IP address."""
    results = await query_dnsbl("not-an-ip", ["zen.spamhaus.org"])

    assert results == []
