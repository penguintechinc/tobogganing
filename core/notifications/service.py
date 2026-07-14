"""Notification service for sending and logging delivery."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog
from penguin_dal import AsyncDB

from core.notifications.channels import ChannelManager
from core.notifications.transports import EmailTransport, TransportError, WebhookTransport

log = structlog.get_logger(__name__)


class NotificationService:
    """Manage notification delivery with logging."""

    def __init__(
        self,
        db: AsyncDB,
        email_transport: EmailTransport | None = None,
        webhook_transport: WebhookTransport | None = None,
    ) -> None:
        """Initialize notification service.

        Args:
            db: AsyncDB instance
            email_transport: Email transport (default creates new)
            webhook_transport: Webhook transport (default creates new)
        """
        self.db = db
        self.channel_manager = ChannelManager(db)
        self.email_transport = email_transport or EmailTransport()
        self.webhook_transport = webhook_transport or WebhookTransport()

    async def notify(
        self,
        tenant: str,
        subject: str,
        body: str,
        channel_ids: list[str] | None = None,
    ) -> dict[str, int]:
        """Send notification via specified or all enabled channels.

        Args:
            tenant: Tenant ID
            subject: Notification subject
            body: Notification body
            channel_ids: Channel IDs to use (None = all enabled for tenant)

        Returns:
            {"sent": count_successful, "failed": count_failed}
        """
        # Resolve channels
        if channel_ids is None:
            # Use all enabled channels for tenant
            all_channels = await self.channel_manager.list_channels(tenant)
            channels = [ch for ch in all_channels if ch["enabled"]]
        else:
            # Use specified channels (tenant-verified per row)
            channels = []
            for ch_id in channel_ids:
                ch = await self.channel_manager.get_channel(tenant, ch_id)
                if ch:  # Skip cross-tenant channel IDs (fail closed)
                    channels.append(ch)

        sent_count = 0
        failed_count = 0

        for channel in channels:
            try:
                # Deliver based on kind
                if channel["kind"] == "email":
                    config = channel["config"]
                    to_list = config.get("to", [])
                    await self.email_transport.send(to_list, subject, body)

                elif channel["kind"] == "webhook":
                    config = channel["config"]
                    url = config.get("url")
                    secret = config.get("secret")

                    # Retrieve full secret (not redacted) from DB
                    full_channels = await self.db(
                        self.db.notification_channels.id == channel["id"]
                    ).select()
                    if full_channels:
                        full_config = json.loads(full_channels[0]["config"])
                        secret = full_config.get("secret")

                    if url and secret:
                        await self.webhook_transport.send(url, secret, subject, body)

                # Record successful delivery
                await self._record_delivery(
                    tenant,
                    channel["id"],
                    subject,
                    status="sent",
                    error=None,
                )
                sent_count += 1
                log.info(
                    "notification_sent",
                    tenant=tenant,
                    channel_id=channel["id"],
                    kind=channel["kind"],
                )

            except TransportError as e:
                # Record failed delivery
                await self._record_delivery(
                    tenant,
                    channel["id"],
                    subject,
                    status="failed",
                    error=str(e),
                )
                failed_count += 1
                log.error(
                    "notification_delivery_failed",
                    tenant=tenant,
                    channel_id=channel["id"],
                    error=str(e),
                )
            except Exception as e:
                # Unexpected error - record and continue
                await self._record_delivery(
                    tenant,
                    channel["id"],
                    subject,
                    status="failed",
                    error=f"Unexpected error: {str(e)}",
                )
                failed_count += 1
                log.error(
                    "notification_error",
                    tenant=tenant,
                    channel_id=channel["id"],
                    error=str(e),
                    exc_info=True,
                )

        return {"sent": sent_count, "failed": failed_count}

    async def _record_delivery(
        self,
        tenant: str,
        channel_id: str,
        subject: str,
        status: str,
        error: str | None,
    ) -> None:
        """Record a delivery attempt in the database.

        Args:
            tenant: Tenant ID
            channel_id: Channel ID
            subject: Notification subject
            status: Delivery status (sent or failed)
            error: Error message if failed
        """
        try:
            delivery_id = str(uuid4())
            await self.db.notification_deliveries.async_insert(
                id=delivery_id,
                tenant=tenant,
                channel_id=channel_id,
                subject=subject,
                status=status,
                error=error,
                created_at=datetime.utcnow(),
            )
        except Exception as e:
            log.error("failed_to_record_delivery", error=str(e), exc_info=True)
