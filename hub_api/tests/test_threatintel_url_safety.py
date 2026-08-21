"""Direct unit tests for the threatintel feed-source SSRF guard.

Complements the higher-level regression tests in test_threatintel_feeds_api.py
and test_threatintel_feeds_ingestor.py by exercising assert_safe_feed_url's
branches directly, including edge cases (no hostname, unresolvable host,
empty resolution, unparseable address) that are impractical to trigger
through the full API/ingest call path.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from hub_api.modules.threatintel.feeds.url_safety import (
    UnsafeFeedURLError,
    _resolve_addresses_sync,
    assert_safe_feed_url,
)


def test_resolve_addresses_sync_literal_ip() -> None:
    """_resolve_addresses_sync on a literal IP returns it (possibly repeated
    once per socket type) without any real DNS I/O.
    """
    result = _resolve_addresses_sync("127.0.0.1")
    assert result
    assert set(result) == {"127.0.0.1"}


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_non_http_scheme() -> None:
    """A non-http(s) scheme (e.g. file://) is rejected before any resolution."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="scheme"):
        await assert_safe_feed_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_ftp_scheme() -> None:
    """A non-http(s) scheme (ftp) is rejected."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="scheme"):
        await assert_safe_feed_url("ftp://feeds.example.com/feed.csv")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_missing_hostname() -> None:
    """A URL with no hostname (e.g. a bare relative path) is rejected."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="no hostname"):
        await assert_safe_feed_url("http:///no-host")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_unresolvable_host() -> None:
    """A host that fails DNS resolution (gaierror) is rejected."""
    # SSRF guard
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        side_effect=socket.gaierror("name or service not known"),
    ):
        with pytest.raises(UnsafeFeedURLError, match="could not resolve"):
            await assert_safe_feed_url("https://does-not-resolve.example.com/feed")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_empty_resolution() -> None:
    """A host that resolves to zero addresses is rejected."""
    # SSRF guard
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=[],
    ):
        with pytest.raises(UnsafeFeedURLError, match="could not resolve"):
            await assert_safe_feed_url("https://no-addresses.example.com/feed")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_unparseable_address() -> None:
    """A resolved value that isn't a parseable IP address is rejected."""
    # SSRF guard
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["not-an-ip-address"],
    ):
        with pytest.raises(UnsafeFeedURLError, match="unparseable"):
            await assert_safe_feed_url("https://weird.example.com/feed")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_cloud_metadata_literal() -> None:
    """The literal cloud metadata IP is rejected (link-local)."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="disallowed"):
        await assert_safe_feed_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_loopback_literal() -> None:
    """The literal loopback address is rejected."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="disallowed"):
        await assert_safe_feed_url("http://127.0.0.1/x")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_private_rfc1918_literal() -> None:
    """A literal RFC1918 private address (10/8) is rejected."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="disallowed"):
        await assert_safe_feed_url("http://10.0.0.1/x")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_private_rfc1918_192_literal() -> None:
    """A literal RFC1918 private address (192.168/16) is rejected."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="disallowed"):
        await assert_safe_feed_url("http://192.168.1.1/x")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_ipv6_loopback() -> None:
    """The IPv6 loopback address (::1) is rejected."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="disallowed"):
        await assert_safe_feed_url("http://[::1]/x")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_ipv6_link_local() -> None:
    """An IPv6 link-local address (fe80::/10) is rejected."""
    # SSRF guard
    with pytest.raises(UnsafeFeedURLError, match="disallowed"):
        await assert_safe_feed_url("http://[fe80::1]/x")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_hostname_resolving_to_private_ip() -> None:
    """A public-looking hostname that resolves to a private IP is rejected (mocked DNS)."""
    # SSRF guard
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["172.16.5.5"],
    ):
        with pytest.raises(UnsafeFeedURLError, match="disallowed"):
            await assert_safe_feed_url("https://looks-public.example.com/feed.csv")


@pytest.mark.asyncio
async def test_assert_safe_feed_url_allows_public_address() -> None:
    """A hostname resolving to a genuinely public address is allowed."""
    # SSRF guard
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["8.8.8.8"],
    ):
        await assert_safe_feed_url("https://feeds.example.com/threat.csv")  # does not raise


@pytest.mark.asyncio
async def test_assert_safe_feed_url_rejects_if_any_resolved_address_unsafe() -> None:
    """If a host resolves to multiple addresses, ANY private one fails the whole check."""
    # SSRF guard
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["8.8.8.8", "10.0.0.1"],
    ):
        with pytest.raises(UnsafeFeedURLError, match="disallowed"):
            await assert_safe_feed_url("https://multi-homed.example.com/feed")
