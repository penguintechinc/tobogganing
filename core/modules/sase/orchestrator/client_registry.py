"""Client registry using penguin-dal with hashed API keys."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

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

    def __init__(self, db: object, tenant_id: str) -> None:
        """Initialize ClientRegistry.

        Args:
            db: penguin-dal DAL instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id
        self.cleanup_interval = 300  # 5 minutes
        self._lock = asyncio.Lock()

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

    async def register_client(
        self, client_data: dict
    ) -> tuple[Client, str]:
        """Register a new client.

        Args:
            client_data: Client data dictionary (id, name, type, cluster_id, public_key, ip_address, metadata)

        Returns:
            Tuple of (Client object, unencrypted api_key)
        """
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        async with self._lock:
            client_obj = await asyncio.to_thread(
                self.db.clients.create,
                id=client_data["id"],
                name=client_data["name"],
                type=client_data["type"],
                cluster_id=client_data["cluster_id"],
                api_key_hash=api_key_hash,
                public_key=client_data["public_key"],
                ip_address=client_data.get("ip_address", ""),
                status="pending",
                created_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                tenant=self.tenant_id,
                metadata=client_data.get("metadata", {}),
            )

            logger.info(
                "Registered client",
                client_id=client_obj.id,
                type=client_obj.type,
                tenant=self.tenant_id,
            )

            return (
                Client(
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
                ),
                api_key,
            )

    async def authenticate_client(
        self, api_key: str
    ) -> Client | None:
        """Authenticate a client by API key.

        Args:
            api_key: Unencrypted API key

        Returns:
            Client if authenticated, None otherwise
        """
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        client_obj = await asyncio.to_thread(
            self.db.clients.select,
            api_key_hash=api_key_hash,
            tenant=self.tenant_id,
        )

        if not client_obj:
            return None

        # Update last_seen and status
        await asyncio.to_thread(
            client_obj.update,
            last_seen=datetime.now(timezone.utc),
            status="active",
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

    async def update_client_status(
        self, client_id: str, status: str, metadata: dict | None = None
    ) -> bool:
        """Update client status.

        Args:
            client_id: Client identifier
            status: New status
            metadata: Optional metadata to merge

        Returns:
            True if successful, False if client not found
        """
        async with self._lock:
            client_obj = await asyncio.to_thread(
                self.db.clients.select,
                id=client_id,
                tenant=self.tenant_id,
            )
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

            await asyncio.to_thread(client_obj.update, **update_data)
            return True

    async def get_client(self, client_id: str) -> Client | None:
        """Get a client by ID.

        Args:
            client_id: Client identifier

        Returns:
            Client or None if not found
        """
        client_obj = await asyncio.to_thread(
            self.db.clients.select,
            id=client_id,
            tenant=self.tenant_id,
        )
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
        clients = await asyncio.to_thread(
            self.db.clients.select_list,
            tenant=self.tenant_id,
        )

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
            for c in clients
        ]

    async def get_clients_by_cluster(self, cluster_id: str) -> list[Client]:
        """Get clients by cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            List of Client objects
        """
        clients = await asyncio.to_thread(
            self.db.clients.select_list,
            cluster_id=cluster_id,
            tenant=self.tenant_id,
        )

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
            for c in clients
        ]

    async def get_clients_by_type(self, client_type: str) -> list[Client]:
        """Get clients by type.

        Args:
            client_type: Client type ('docker' or 'native')

        Returns:
            List of Client objects
        """
        clients = await asyncio.to_thread(
            self.db.clients.select_list,
            type=client_type,
            tenant=self.tenant_id,
        )

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
            for c in clients
        ]

    async def remove_client(self, client_id: str) -> bool:
        """Remove a client.

        Args:
            client_id: Client identifier

        Returns:
            True if successful, False if not found
        """
        async with self._lock:
            client_obj = await asyncio.to_thread(
                self.db.clients.select,
                id=client_id,
                tenant=self.tenant_id,
            )
            if not client_obj:
                return False

            await asyncio.to_thread(client_obj.delete)
            logger.info("Removed client", client_id=client_id, tenant=self.tenant_id)
            return True

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
        stale_threshold = datetime.now(timezone.utc) - timedelta(hours=24)

        async with self._lock:
            clients = await asyncio.to_thread(
                self.db.clients.select_list,
                tenant=self.tenant_id,
            )

            for client_obj in clients:
                if (
                    client_obj.last_seen < stale_threshold
                    and client_obj.status != "active"
                ):
                    await asyncio.to_thread(client_obj.delete)
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
        clients = await asyncio.to_thread(
            self.db.clients.select_list,
            tenant=self.tenant_id,
        )
        return len(clients)

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

        async with self._lock:
            client_obj = await asyncio.to_thread(
                self.db.clients.select,
                id=client_id,
                tenant=self.tenant_id,
            )
            if not client_obj:
                return None

            await asyncio.to_thread(
                client_obj.update,
                api_key_hash=new_api_key_hash,
            )

            logger.info(
                "Rotated API key for client",
                client_id=client_id,
                tenant=self.tenant_id,
            )
            return new_api_key
