"""Notification channel manager for tenant-scoped CRUD."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog
from penguin_dal import AsyncDB

log = structlog.get_logger(__name__)


class ChannelManager:
    """Manage notification channels (email/webhook) per tenant."""

    def __init__(self, db: AsyncDB) -> None:
        """Initialize channel manager.

        Args:
            db: AsyncDB instance
        """
        self.db = db

    async def create_channel(
        self,
        tenant: str,
        name: str,
        kind: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a notification channel.

        Args:
            tenant: Tenant ID
            name: Channel name
            kind: Channel kind (email or webhook)
            config: Channel configuration (JSON)
                - email: {"to": [email_addresses]}
                - webhook: {"url": "https://...", "secret": "..."}

        Returns:
            Channel row dict

        Raises:
            ValueError: On invalid kind or missing required config
        """
        # Validate kind
        if kind not in ("email", "webhook"):
            raise ValueError(f"Invalid channel kind: {kind}")

        # Validate config based on kind
        if kind == "email":
            if "to" not in config or not config["to"]:
                raise ValueError("Email channel requires 'to' list")
            if not isinstance(config["to"], list):
                raise ValueError("Email 'to' must be a list")

        elif kind == "webhook":
            if "url" not in config:
                raise ValueError("Webhook channel requires 'url'")
            if "secret" not in config:
                raise ValueError("Webhook channel requires 'secret'")
            if not config["url"].startswith("https://"):
                raise ValueError("Webhook URL must use https")

        # Create channel row
        channel_id = str(uuid4())
        config_json = json.dumps(config)

        await self.db.notification_channels.async_insert(
            id=channel_id,
            tenant=tenant,
            name=name,
            kind=kind,
            config=config_json,
            enabled=True,
            created_at=datetime.utcnow(),
        )

        log.info("channel_created", channel_id=channel_id, tenant=tenant, kind=kind)

        return {
            "id": channel_id,
            "tenant": tenant,
            "name": name,
            "kind": kind,
            "config": self._redact_config(kind, config),
            "enabled": True,
            "created_at": None,
        }

    async def list_channels(self, tenant: str) -> list[dict[str, Any]]:
        """List all channels for a tenant.

        Args:
            tenant: Tenant ID

        Returns:
            List of channel row dicts (secrets redacted)
        """
        rows = await self.db(self.db.notification_channels.tenant == tenant).select()

        result = []
        for row in rows:
            config = json.loads(row["config"])
            result.append(
                {
                    "id": row["id"],
                    "tenant": row["tenant"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "config": self._redact_config(row["kind"], config),
                    "enabled": row["enabled"],
                    "created_at": row["created_at"],
                }
            )

        return result

    async def get_channel(self, tenant: str, channel_id: str) -> dict[str, Any] | None:
        """Retrieve a specific channel.

        Args:
            tenant: Tenant ID
            channel_id: Channel ID

        Returns:
            Channel row dict or None if not found (secrets redacted)
        """
        rows = await self.db(
            (self.db.notification_channels.tenant == tenant)
            & (self.db.notification_channels.id == channel_id)
        ).select()

        if not rows:
            return None

        row = rows[0]
        config = json.loads(row["config"])

        return {
            "id": row["id"],
            "tenant": row["tenant"],
            "name": row["name"],
            "kind": row["kind"],
            "config": self._redact_config(row["kind"], config),
            "enabled": row["enabled"],
            "created_at": row["created_at"],
        }

    async def delete_channel(self, tenant: str, channel_id: str) -> bool:
        """Delete a channel.

        Args:
            tenant: Tenant ID
            channel_id: Channel ID

        Returns:
            True if deleted, False if not found or cross-tenant
        """
        result = await self.db(
            (self.db.notification_channels.tenant == tenant)
            & (self.db.notification_channels.id == channel_id)
        ).delete()

        if result:
            log.info("channel_deleted", channel_id=channel_id, tenant=tenant)

        return result > 0

    async def set_enabled(self, tenant: str, channel_id: str, enabled: bool) -> bool:
        """Enable or disable a channel.

        Args:
            tenant: Tenant ID
            channel_id: Channel ID
            enabled: Enabled state

        Returns:
            True if updated, False if not found or cross-tenant
        """
        result = await self.db(
            (self.db.notification_channels.tenant == tenant)
            & (self.db.notification_channels.id == channel_id)
        ).update(enabled=enabled)

        if result:
            log.info("channel_enabled_updated", channel_id=channel_id, enabled=enabled)

        return result > 0

    @staticmethod
    def _redact_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
        """Redact secrets from config for external responses.

        Args:
            kind: Channel kind
            config: Channel config dict

        Returns:
            Config dict with secrets redacted
        """
        if kind == "webhook" and "secret" in config:
            secret = config["secret"]
            redacted = "****" + secret[-4:] if len(secret) > 4 else "****"
            return {**config, "secret": redacted}

        return config
