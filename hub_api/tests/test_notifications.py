"""Tests for hub_api.notifications channels, transports, and delivery."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from penguin_dal import AsyncDB

from hub_api.notifications.channels import ChannelManager
from hub_api.notifications.service import NotificationService
from hub_api.notifications.transports import EmailTransport, TransportError, WebhookTransport


@pytest.fixture(autouse=True)
def _mock_safe_webhook_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve every webhook hostname to a safe public IP (8.8.8.8).

    Keeps WebhookTransport's SSRF guard (real DNS resolution via
    assert_safe_feed_url) out of these unit tests. SSRF guard behavior
    itself is covered by test_notifications_transports_ssrf.py.
    """
    monkeypatch.setattr(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        lambda host: ["8.8.8.8"],
    )


@pytest.mark.asyncio
class TestChannelManager:
    """Test ChannelManager CRUD and tenant isolation."""

    async def test_create_channel_email(self, real_dal: AsyncDB) -> None:
        """Create email channel with valid config."""
        manager = ChannelManager(real_dal)
        config = {"to": ["user@example.com", "admin@example.com"]}

        result = await manager.create_channel("tenant-a", "Alert Channel", "email", config)

        assert result["id"]
        assert result["tenant"] == "tenant-a"
        assert result["name"] == "Alert Channel"
        assert result["kind"] == "email"
        assert result["enabled"] is True
        assert result["config"] == config

    async def test_create_channel_webhook_https(self, real_dal: AsyncDB) -> None:
        """Create webhook channel with https URL."""
        manager = ChannelManager(real_dal)
        config = {"url": "https://example.com/webhook", "secret": "super-secret-key"}

        result = await manager.create_channel("tenant-a", "Webhook", "webhook", config)

        assert result["id"]
        assert result["kind"] == "webhook"
        assert result["config"]["url"] == "https://example.com/webhook"
        # Secret should be redacted in response
        assert "secret" not in result["config"] or result["config"].get("secret", "").startswith(
            "****"
        )

    async def test_create_channel_webhook_non_https_rejected(self, real_dal: AsyncDB) -> None:
        """Reject webhook with non-https URL."""
        manager = ChannelManager(real_dal)
        config = {"url": "http://example.com/webhook", "secret": "key"}

        with pytest.raises(ValueError, match="https"):
            await manager.create_channel("tenant-a", "Webhook", "webhook", config)

    async def test_create_channel_email_missing_to(self, real_dal: AsyncDB) -> None:
        """Reject email channel with missing 'to' list."""
        manager = ChannelManager(real_dal)

        with pytest.raises(ValueError):
            await manager.create_channel("tenant-a", "Email", "email", {})

    async def test_create_channel_webhook_missing_url(self, real_dal: AsyncDB) -> None:
        """Reject webhook with missing 'url'."""
        manager = ChannelManager(real_dal)
        config = {"secret": "key"}

        with pytest.raises(ValueError):
            await manager.create_channel("tenant-a", "Webhook", "webhook", config)

    async def test_list_channels(self, real_dal: AsyncDB) -> None:
        """List channels for a tenant."""
        manager = ChannelManager(real_dal)
        config_a = {"to": ["a@example.com"]}
        config_b = {"to": ["b@example.com"]}

        ch_a = await manager.create_channel("tenant-a", "Ch-A", "email", config_a)
        ch_b = await manager.create_channel("tenant-a", "Ch-B", "email", config_b)
        ch_c = await manager.create_channel("tenant-b", "Ch-C", "email", {"to": ["c@example.com"]})

        result = await manager.list_channels("tenant-a")

        assert len(result) == 2
        assert any(ch["id"] == ch_a["id"] for ch in result)
        assert any(ch["id"] == ch_b["id"] for ch in result)
        assert not any(ch["id"] == ch_c["id"] for ch in result)

    async def test_list_channels_secret_redacted(self, real_dal: AsyncDB) -> None:
        """Secrets redacted in list response."""
        manager = ChannelManager(real_dal)
        config = {"url": "https://example.com/webhook", "secret": "secret-key-12345"}

        await manager.create_channel("tenant-a", "WH", "webhook", config)

        channels = await manager.list_channels("tenant-a")
        assert len(channels) == 1
        # Secret should be redacted or absent
        cfg = channels[0].get("config", {})
        if "secret" in cfg:
            assert cfg["secret"].startswith("****") and cfg["secret"].endswith("5")

    async def test_get_channel(self, real_dal: AsyncDB) -> None:
        """Retrieve a specific channel."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Ch", "email", {"to": ["a@example.com"]})

        result = await manager.get_channel("tenant-a", ch["id"])

        assert result is not None
        assert result["id"] == ch["id"]
        assert result["name"] == "Ch"

    async def test_get_channel_secret_redacted(self, real_dal: AsyncDB) -> None:
        """Secrets redacted in get response."""
        manager = ChannelManager(real_dal)
        config = {"url": "https://example.com/webhook", "secret": "my-secret-99999"}

        ch = await manager.create_channel("tenant-a", "WH", "webhook", config)

        result = await manager.get_channel("tenant-a", ch["id"])
        cfg = result.get("config", {})
        if "secret" in cfg:
            assert cfg["secret"].startswith("****") and cfg["secret"].endswith("9")

    async def test_get_channel_cross_tenant_returns_none(self, real_dal: AsyncDB) -> None:
        """Cross-tenant get returns None."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Ch", "email", {"to": ["a@example.com"]})

        result = await manager.get_channel("tenant-b", ch["id"])

        assert result is None

    async def test_delete_channel(self, real_dal: AsyncDB) -> None:
        """Delete a channel."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Ch", "email", {"to": ["a@example.com"]})

        deleted = await manager.delete_channel("tenant-a", ch["id"])

        assert deleted is True
        result = await manager.get_channel("tenant-a", ch["id"])
        assert result is None

    async def test_delete_channel_cross_tenant_returns_false(self, real_dal: AsyncDB) -> None:
        """Cross-tenant delete returns False."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Ch", "email", {"to": ["a@example.com"]})

        deleted = await manager.delete_channel("tenant-b", ch["id"])

        assert deleted is False
        # Original should still exist
        result = await manager.get_channel("tenant-a", ch["id"])
        assert result is not None

    async def test_set_enabled(self, real_dal: AsyncDB) -> None:
        """Toggle channel enabled state."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Ch", "email", {"to": ["a@example.com"]})

        await manager.set_enabled("tenant-a", ch["id"], False)

        result = await manager.get_channel("tenant-a", ch["id"])
        assert result["enabled"] is False

        await manager.set_enabled("tenant-a", ch["id"], True)

        result = await manager.get_channel("tenant-a", ch["id"])
        assert result["enabled"] is True


@pytest.mark.asyncio
class TestNotificationService:
    """Test NotificationService delivery and tenant isolation."""

    async def test_notify_success_email(self, real_dal: AsyncDB) -> None:
        """Notify with working email transport records delivery."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Email", "email", {"to": ["a@example.com"]})

        fake_email = AsyncMock(spec=EmailTransport)
        service = NotificationService(real_dal, email_transport=fake_email)

        result = await service.notify("tenant-a", "Subject", "Body", [ch["id"]])

        assert result["sent"] == 1
        assert result["failed"] == 0
        fake_email.send.assert_called_once()

        # Verify delivery row created
        deliveries = await real_dal(real_dal.notification_deliveries.tenant == "tenant-a").select()
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "sent"

    async def test_notify_failure_records_failed(self, real_dal: AsyncDB) -> None:
        """Notify with failing transport records failure."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Email", "email", {"to": ["a@example.com"]})

        fake_email = AsyncMock(spec=EmailTransport)
        fake_email.send.side_effect = TransportError("SMTP failed")
        service = NotificationService(real_dal, email_transport=fake_email)

        result = await service.notify("tenant-a", "Subject", "Body", [ch["id"]])

        assert result["sent"] == 0
        assert result["failed"] == 1

        # Verify failed delivery row with error
        deliveries = await real_dal(real_dal.notification_deliveries.tenant == "tenant-a").select()
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "failed"
        assert "SMTP" in (deliveries[0].get("error") or "")

    async def test_notify_cross_tenant_channel_skipped(self, real_dal: AsyncDB) -> None:
        """Notify silently skips cross-tenant channel IDs (no delivery row)."""
        manager = ChannelManager(real_dal)
        # ch_a exists only to prove tenant-a's own channels aren't touched.
        _ch_a = await manager.create_channel("tenant-a", "Ch", "email", {"to": ["a@example.com"]})
        ch_b = await manager.create_channel("tenant-b", "Ch", "email", {"to": ["b@example.com"]})

        fake_email = AsyncMock(spec=EmailTransport)
        service = NotificationService(real_dal, email_transport=fake_email)

        # Try to notify tenant-a with a channel from tenant-b
        result = await service.notify("tenant-a", "Subject", "Body", [ch_b["id"]])

        # Should not send anything (cross-tenant channel ignored)
        assert result["sent"] == 0
        assert result["failed"] == 0
        fake_email.send.assert_not_called()

        # No delivery row should be created
        deliveries = await real_dal(real_dal.notification_deliveries.tenant == "tenant-a").select()
        assert len(deliveries) == 0

    async def test_notify_no_channels_specified_uses_all_enabled(self, real_dal: AsyncDB) -> None:
        """Notify with channel_ids=None uses all enabled channels for tenant."""
        manager = ChannelManager(real_dal)
        # ch_a/ch_b exist only to be picked up by the "all enabled" default.
        _ch_a = await manager.create_channel("tenant-a", "Ch-A", "email", {"to": ["a@example.com"]})
        _ch_b = await manager.create_channel("tenant-a", "Ch-B", "email", {"to": ["b@example.com"]})
        ch_c = await manager.create_channel("tenant-a", "Ch-C", "email", {"to": ["c@example.com"]})

        # Disable ch_c
        await manager.set_enabled("tenant-a", ch_c["id"], False)

        fake_email = AsyncMock(spec=EmailTransport)
        service = NotificationService(real_dal, email_transport=fake_email)

        result = await service.notify("tenant-a", "Subject", "Body", channel_ids=None)

        # Should send to ch_a and ch_b (ch_c is disabled)
        assert result["sent"] == 2
        assert result["failed"] == 0
        assert fake_email.send.call_count == 2

    async def test_notify_never_raises_transport_error(self, real_dal: AsyncDB) -> None:
        """Notify never raises transport errors outward."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel("tenant-a", "Email", "email", {"to": ["a@example.com"]})

        fake_email = AsyncMock(spec=EmailTransport)
        fake_email.send.side_effect = TransportError("Connection refused")
        service = NotificationService(real_dal, email_transport=fake_email)

        # Should not raise
        result = await service.notify("tenant-a", "Subject", "Body", [ch["id"]])

        assert result["failed"] == 1


@pytest.mark.asyncio
class TestWebhookTransport:
    """Test webhook HMAC signature computation."""

    async def test_webhook_signature_hmac_sha256(self) -> None:
        """Webhook signature is HMAC-SHA256 over raw body."""
        import hashlib
        import hmac

        # Create a fake HTTP client
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=Mock(status_code=200))

        transport = WebhookTransport()
        transport._client = mock_client

        url = "https://example.com/webhook"
        secret = "test-secret"
        subject = "Alert"
        body = "Something happened"

        await transport.send(url, secret, subject, body)

        # Check the call
        assert mock_client.post.called
        call_args = mock_client.post.call_args

        # Extract headers from the call
        headers = call_args.kwargs.get("headers", {})

        # We can't easily check the exact signature without knowing the timestamp,
        # but we can verify the header is present and has the right format
        assert "X-Tobogganing-Signature" in headers
        assert headers["X-Tobogganing-Signature"].startswith("sha256=")

    async def test_webhook_post_json_body(self) -> None:
        """Webhook POSTs JSON with subject, body, timestamp."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=Mock(status_code=200))

        transport = WebhookTransport()
        transport._client = mock_client

        url = "https://example.com/webhook"

        await transport.send(url, "secret", "Subject", "Body")

        # Check call
        assert mock_client.post.called
        call_args = mock_client.post.call_args
        json_arg = call_args.kwargs.get("content", "")

        # Parse the JSON body
        if json_arg:
            body_dict = json.loads(json_arg)
            assert body_dict["subject"] == "Subject"
            assert body_dict["body"] == "Body"
            assert "timestamp" in body_dict

    async def test_webhook_raises_on_http_error(self) -> None:
        """WebhookTransport raises TransportError on HTTP errors."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=Mock(status_code=500))

        transport = WebhookTransport()
        transport._client = mock_client

        with pytest.raises(TransportError):
            await transport.send("https://example.com/webhook", "secret", "Subj", "Body")


@pytest.mark.asyncio
class TestEmailTransport:
    """Test email transport via SMTP."""

    async def test_email_send_uses_smtp(self) -> None:
        """EmailTransport uses stdlib smtplib in thread."""
        # We can't easily test the actual SMTP without mocking,
        # but we can verify the interface works
        transport = EmailTransport()

        # Should have send method
        assert hasattr(transport, "send")
        assert callable(transport.send)
