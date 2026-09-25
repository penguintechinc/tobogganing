"""SSRF regression tests for WebhookTransport.send().

WebhookTransport.send() previously only checked the URL scheme (https),
never the resolved address — an authenticated user could register a
webhook pointed at loopback, link-local (incl. cloud metadata), or private
RFC1918 addresses and have hub_api make the request server-side. It now
runs every send() through the same resolved-address SSRF guard
(assert_safe_feed_url) used by the threatintel feeds ingest path, and the
underlying httpx client never auto-follows redirects.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from hub_api.notifications.transports import TransportError, WebhookTransport


@pytest.mark.asyncio
async def test_send_rejects_loopback_resolved_address() -> None:
    """send() rejects a webhook URL whose host resolves to loopback."""
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["127.0.0.1"],
    ):
        transport = WebhookTransport()
        with pytest.raises(TransportError, match="not allowed"):
            await transport.send("https://webhook.example.com/x", "secret", "Subj", "Body")


@pytest.mark.asyncio
async def test_send_rejects_link_local_cloud_metadata_address() -> None:
    """send() rejects a webhook URL resolving to the cloud metadata address."""
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["169.254.169.254"],
    ):
        transport = WebhookTransport()
        with pytest.raises(TransportError, match="not allowed"):
            await transport.send("https://webhook.example.com/x", "secret", "Subj", "Body")


@pytest.mark.asyncio
async def test_send_rejects_private_rfc1918_address() -> None:
    """send() rejects a webhook URL resolving to an RFC1918 private address."""
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["10.0.0.5"],
    ):
        transport = WebhookTransport()
        with pytest.raises(TransportError, match="not allowed"):
            await transport.send("https://webhook.example.com/x", "secret", "Subj", "Body")


@pytest.mark.asyncio
async def test_send_never_reaches_http_client_when_ssrf_rejected() -> None:
    """The SSRF guard runs before any request is made — the http client is never touched."""
    mock_client = AsyncMock()
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["127.0.0.1"],
    ):
        transport = WebhookTransport()
        transport._client = mock_client
        with pytest.raises(TransportError):
            await transport.send("https://webhook.example.com/x", "secret", "Subj", "Body")

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_allows_safe_public_address() -> None:
    """send() proceeds normally when the resolved address is a safe public IP."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=Mock(status_code=200))

    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        return_value=["8.8.8.8"],
    ):
        transport = WebhookTransport()
        transport._client = mock_client
        await transport.send("https://webhook.example.com/x", "secret", "Subj", "Body")

    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_send_revalidates_dns_on_every_call() -> None:
    """The SSRF guard is re-run on every send() (TOCTOU / DNS-rebinding protection)."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=Mock(status_code=200))

    resolve_calls = {"n": 0}

    def _flip_flop(host: str) -> list[str]:
        resolve_calls["n"] += 1
        # First call: safe public address. Second call: rebinds to loopback.
        return ["8.8.8.8"] if resolve_calls["n"] == 1 else ["127.0.0.1"]

    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        side_effect=_flip_flop,
    ):
        transport = WebhookTransport()
        transport._client = mock_client

        # First send succeeds (safe address).
        await transport.send("https://webhook.example.com/x", "secret", "Subj", "Body")

        # Second send is rejected — DNS rebound to loopback.
        with pytest.raises(TransportError, match="not allowed"):
            await transport.send("https://webhook.example.com/x", "secret", "Subj", "Body")

    assert resolve_calls["n"] == 2
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_client_never_follows_redirects() -> None:
    """The lazily-created httpx client has follow_redirects disabled."""
    transport = WebhookTransport()
    client = await transport._get_client()
    try:
        assert client.follow_redirects is False
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_non_https_url_rejected_before_dns_resolution() -> None:
    """A non-https URL is rejected by the scheme check, before any DNS lookup."""
    with patch(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
    ) as mock_resolve:
        transport = WebhookTransport()
        with pytest.raises(TransportError, match="https"):
            await transport.send("http://webhook.example.com/x", "secret", "Subj", "Body")

    mock_resolve.assert_not_called()
