"""Additional coverage for hub_api.notifications.service: webhook delivery + error paths.

test_notifications.py exercises NotificationService with email channels only;
this file covers the webhook delivery branch (including full-secret retrieval),
the generic-exception catch-all, and _record_delivery's own failure handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from penguin_dal import AsyncDB

from hub_api.notifications.channels import ChannelManager
from hub_api.notifications.service import NotificationService
from hub_api.notifications.transports import EmailTransport, WebhookTransport


@pytest.mark.asyncio
class TestNotificationServiceWebhook:
    """Tests for webhook delivery through NotificationService.notify()."""

    async def test_notify_webhook_success_retrieves_full_secret(self, real_dal: AsyncDB) -> None:
        """Webhook delivery fetches the un-redacted secret from the DB before sending."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel(
            "tenant-a",
            "WH",
            "webhook",
            {"url": "https://example.com/hook", "secret": "top-secret-value"},
        )

        fake_webhook = AsyncMock(spec=WebhookTransport)
        service = NotificationService(real_dal, webhook_transport=fake_webhook)

        result = await service.notify("tenant-a", "Subject", "Body", [ch["id"]])

        assert result["sent"] == 1
        assert result["failed"] == 0
        fake_webhook.send.assert_called_once_with(
            "https://example.com/hook", "top-secret-value", "Subject", "Body"
        )

    async def test_notify_webhook_missing_secret_skips_send(self, real_dal: AsyncDB) -> None:
        """Webhook delivery still records 'sent' even if url/secret end up missing."""
        manager = ChannelManager(real_dal)
        ch = await manager.create_channel(
            "tenant-a", "WH", "webhook", {"url": "https://example.com/hook", "secret": "s"}
        )

        # Directly corrupt the stored config so full_config.get("secret") is None.
        await real_dal(real_dal.notification_channels.id == ch["id"]).update(
            config='{"url": "https://example.com/hook"}'
        )

        fake_webhook = AsyncMock(spec=WebhookTransport)
        service = NotificationService(real_dal, webhook_transport=fake_webhook)

        result = await service.notify("tenant-a", "Subject", "Body", [ch["id"]])

        assert result["sent"] == 1
        fake_webhook.send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_unexpected_exception_recorded_as_failed(real_dal: AsyncDB) -> None:
    """notify() catches unexpected (non-TransportError) exceptions per-channel."""
    manager = ChannelManager(real_dal)
    ch = await manager.create_channel("tenant-a", "Email", "email", {"to": ["a@example.com"]})

    fake_email = AsyncMock(spec=EmailTransport)
    fake_email.send.side_effect = ValueError("totally unexpected")
    service = NotificationService(real_dal, email_transport=fake_email)

    result = await service.notify("tenant-a", "Subject", "Body", [ch["id"]])

    assert result["sent"] == 0
    assert result["failed"] == 1

    deliveries = await real_dal(real_dal.notification_deliveries.tenant == "tenant-a").select()
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "failed"
    assert "Unexpected error" in (deliveries[0].get("error") or "")


@pytest.mark.asyncio
async def test_record_delivery_swallows_db_error(real_dal: AsyncDB) -> None:
    """_record_delivery() logs but doesn't raise when the insert itself fails."""
    manager = ChannelManager(real_dal)
    ch = await manager.create_channel("tenant-a", "Email", "email", {"to": ["a@example.com"]})

    fake_email = AsyncMock(spec=EmailTransport)
    service = NotificationService(real_dal, email_transport=fake_email)

    with patch.object(
        real_dal.notification_deliveries,
        "async_insert",
        new=AsyncMock(side_effect=RuntimeError("insert failed")),
    ):
        # Should not raise despite the delivery-logging insert failing.
        result = await service.notify("tenant-a", "Subject", "Body", [ch["id"]])

    assert result["sent"] == 1
