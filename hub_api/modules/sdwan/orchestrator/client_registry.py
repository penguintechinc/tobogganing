"""Client registry using penguin-dal with hashed API keys."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass(slots=True)
class Client:
    """Client data structure."""

    id: str
    name: str
    type: str  # 'docker' or 'native'
    cluster_id: str
    api_key_hash: str
    public_key: str
    ip_address: str
    status: str
    created_at: datetime
    last_seen: datetime
    tenant: str
    metadata: dict | None = None


class ClientRegistry:
    """Manages client registration and authentication using penguin-dal."""

    def __init__(self, db: Any, tenant_id: str) -> None:
        """Initialize ClientRegistry.

        Args:
            db: penguin-dal AsyncDB instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id
        self.cleanup_interval = 300  # 5 minutes

    async def initialize(self) -> None:
        """Initialize the ClientRegistry."""
        try:
            logger.info("ClientRegistry initialized", tenant=self.tenant_id)
        except Exception as e:
            logger.error("Failed to initialize ClientRegistry", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the ClientRegistry."""
        logger.info("ClientRegistry shutdown complete")

    async def register_client(self, client_data: dict) -> tuple[Client, str]:
        """Register a new client.

        Args:
            client_data: Client data dictionary (id, name, type, cluster_id, public_key, ip_address, metadata)

        Returns:
            Tuple of (Client object, unencrypted api_key)
        """
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        now = datetime.now(timezone.utc)

        await self.db.clients.async_insert(
            id=client_data["id"],
            name=client_data["name"],
            type=client_data["type"],
            cluster_id=client_data["cluster_id"],
            api_key_hash=api_key_hash,
            public_key=client_data["public_key"],
            ip_address=client_data.get("ip_address", ""),
            created_at=now,
            last_seen=now,
            tenant=self.tenant_id,
            metadata=client_data.get("metadata", {}),
        )

        client_obj = Client(
            id=client_data["id"],
            name=client_data["name"],
            type=client_data["type"],
            cluster_id=client_data["cluster_id"],
            api_key_hash=api_key_hash,
            public_key=client_data["public_key"],
            ip_address=client_data.get("ip_address", ""),
            status="pending",
            created_at=now,
            last_seen=now,
            tenant=self.tenant_id,
            metadata=client_data.get("metadata", {}),
        )

        logger.info(
            "Registered client",
            client_id=client_obj.id,
            type=client_obj.type,
            tenant=self.tenant_id,
        )

        return (client_obj, api_key)

    async def authenticate_client(self, api_key: str) -> Client | None:
        """Authenticate a client by API key.

        Args:
            api_key: Unencrypted API key

        Returns:
            Client if authenticated and active, None otherwise
        """
        try:
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

            rowset = await self.db(
                (self.db.clients.api_key_hash == api_key_hash)
                & (self.db.clients.tenant == self.tenant_id)
            ).select()
            client_obj = rowset.first()

            if not client_obj:
                return None

            # CRITICAL: Reject non-active clients (revoked, disabled, pending)
            if client_obj.status != "active":
                logger.warning(
                    "Authentication rejected: inactive client",
                    client_id=client_obj.id,
                    status=client_obj.status,
                    tenant=self.tenant_id,
                )
                return None

            # Use constant-time comparison for stored hash
            if not hmac.compare_digest(client_obj.api_key_hash, api_key_hash):
                logger.warning(
                    "Authentication rejected: hash mismatch",
                    client_id=client_obj.id,
                    tenant=self.tenant_id,
                )
                return None

            # Update last_seen (DO NOT update status; client must already be active)
            await self.db(self.db.clients.id == client_obj.id).update(
                last_seen=datetime.now(timezone.utc)
            )

            return Client(
                id=client_obj.id,
                name=client_obj.name,
                type=client_obj.type,
                cluster_id=client_obj.cluster_id,
                api_key_hash=client_obj.api_key_hash,
                public_key=client_obj.public_key,
                ip_address=client_obj.ip_address,
                status=client_obj.status,
                created_at=client_obj.created_at,
                last_seen=client_obj.last_seen,
                tenant=client_obj.tenant,
                metadata=client_obj.metadata,
            )
        except Exception as e:
            logger.error(
                "Authentication error (fail closed)",
                error=str(e),
                tenant=self.tenant_id,
            )
            return None

    async def update_client_status(
        self, client_id: str, status: str, metadata: dict | None = None
    ) -> bool:
        """Update client status.

        Args:
            client_id: Client identifier
            status: New status
            metadata: Optional metadata to merge

        Returns:
            True if successful, False if client not found or on error
        """
        try:
            rowset = await self.db(
                (self.db.clients.id == client_id) & (self.db.clients.tenant == self.tenant_id)
            ).select()
            client_obj = rowset.first()
            if not client_obj:
                return False

            update_data = {
                "status": status,
                "last_seen": datetime.now(timezone.utc),
            }
            if metadata:
                existing_metadata = client_obj.metadata or {}
                existing_metadata.update(metadata)
                update_data["metadata"] = existing_metadata

            await self.db(self.db.clients.id == client_id).update(**update_data)
            return True
        except Exception as e:
            logger.error(
                "Failed to update client status (fail closed)",
                client_id=client_id,
                error=str(e),
                tenant=self.tenant_id,
            )
            return False

    async def get_client(self, client_id: str) -> Client | None:
        """Get a client by ID.

        Args:
            client_id: Client identifier

        Returns:
            Client or None if not found
        """
        rowset = await self.db(
            (self.db.clients.id == client_id) & (self.db.clients.tenant == self.tenant_id)
        ).select()
        client_obj = rowset.first()
        if not client_obj:
            return None

        return Client(
            id=client_obj.id,
            name=client_obj.name,
            type=client_obj.type,
            cluster_id=client_obj.cluster_id,
            api_key_hash=client_obj.api_key_hash,
            public_key=client_obj.public_key,
            ip_address=client_obj.ip_address,
            status=client_obj.status,
            created_at=client_obj.created_at,
            last_seen=client_obj.last_seen,
            tenant=client_obj.tenant,
            metadata=client_obj.metadata,
        )

    async def get_all_clients(self) -> list[Client]:
        """Get all clients for the tenant.

        Returns:
            List of Client objects
        """
        rowset = await self.db(self.db.clients.tenant == self.tenant_id).select()

        return [
            Client(
                id=c.id,
                name=c.name,
                type=c.type,
                cluster_id=c.cluster_id,
                api_key_hash=c.api_key_hash,
                public_key=c.public_key,
                ip_address=c.ip_address,
                status=c.status,
                created_at=c.created_at,
                last_seen=c.last_seen,
                tenant=c.tenant,
                metadata=c.metadata,
            )
            for c in rowset
        ]

    async def get_clients_by_cluster(self, cluster_id: str) -> list[Client]:
        """Get clients by cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            List of Client objects
        """
        rowset = await self.db(
            (self.db.clients.cluster_id == cluster_id) & (self.db.clients.tenant == self.tenant_id)
        ).select()

        return [
            Client(
                id=c.id,
                name=c.name,
                type=c.type,
                cluster_id=c.cluster_id,
                api_key_hash=c.api_key_hash,
                public_key=c.public_key,
                ip_address=c.ip_address,
                status=c.status,
                created_at=c.created_at,
                last_seen=c.last_seen,
                tenant=c.tenant,
                metadata=c.metadata,
            )
            for c in rowset
        ]

    async def get_clients_by_type(self, client_type: str) -> list[Client]:
        """Get clients by type.

        Args:
            client_type: Client type ('docker' or 'native')

        Returns:
            List of Client objects
        """
        rowset = await self.db(
            (self.db.clients.type == client_type) & (self.db.clients.tenant == self.tenant_id)
        ).select()

        return [
            Client(
                id=c.id,
                name=c.name,
                type=c.type,
                cluster_id=c.cluster_id,
                api_key_hash=c.api_key_hash,
                public_key=c.public_key,
                ip_address=c.ip_address,
                status=c.status,
                created_at=c.created_at,
                last_seen=c.last_seen,
                tenant=c.tenant,
                metadata=c.metadata,
            )
            for c in rowset
        ]

    async def remove_client(self, client_id: str) -> bool:
        """Remove a client.

        Args:
            client_id: Client identifier

        Returns:
            True if successful, False if not found or on error
        """
        try:
            rowset = await self.db(
                (self.db.clients.id == client_id) & (self.db.clients.tenant == self.tenant_id)
            ).select()
            client_obj = rowset.first()
            if not client_obj:
                return False

            await self.db(self.db.clients.id == client_id).delete()
            logger.info("Removed client", client_id=client_id, tenant=self.tenant_id)
            return True
        except Exception as e:
            logger.error(
                "Failed to remove client (fail closed)",
                client_id=client_id,
                error=str(e),
                tenant=self.tenant_id,
            )
            return False

    async def cleanup_expired(self) -> None:
        """Cleanup expired clients (background task)."""
        while True:
            try:
                await self._cleanup_stale_clients()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error("Cleanup error", error=str(e))
                await asyncio.sleep(30)

    async def _cleanup_stale_clients(self) -> None:
        """Clean up stale clients."""
        # NOTE: last_seen is stored as a naive sa.DateTime() column, so the
        # threshold must be naive too -- comparing against datetime.now(timezone.utc)
        # raises TypeError: can't compare offset-naive and offset-aware datetimes.
        stale_threshold = datetime.utcnow() - timedelta(hours=24)

        rowset = await self.db(self.db.clients.tenant == self.tenant_id).select()

        for client_obj in rowset:
            if client_obj.last_seen < stale_threshold and client_obj.status != "active":
                await self.db(self.db.clients.id == client_obj.id).delete()
                logger.info(
                    "Cleaned up stale client",
                    client_id=client_obj.id,
                    tenant=self.tenant_id,
                )

    async def get_client_count(self) -> int:
        """Get count of clients for the tenant.

        Returns:
            Number of clients
        """
        count = await self.db(self.db.clients.tenant == self.tenant_id).count()
        return count

    async def is_healthy(self) -> bool:
        """Check if registry is healthy.

        Returns:
            True if healthy
        """
        try:
            await self.get_client_count()
            return True
        except Exception:
            return False

    async def rotate_api_key(self, client_id: str) -> str | None:
        """Rotate API key for a client.

        Args:
            client_id: Client identifier

        Returns:
            New unencrypted API key or None if client not found
        """
        new_api_key = secrets.token_urlsafe(32)
        new_api_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()

        rowset = await self.db(
            (self.db.clients.id == client_id) & (self.db.clients.tenant == self.tenant_id)
        ).select()
        client_obj = rowset.first()
        if not client_obj:
            return None

        await self.db(self.db.clients.id == client_id).update(api_key_hash=new_api_key_hash)

        logger.info(
            "Rotated API key for client",
            client_id=client_id,
            tenant=self.tenant_id,
        )
        return new_api_key
