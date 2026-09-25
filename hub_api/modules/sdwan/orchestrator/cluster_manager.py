"""Cluster management using penguin-dal."""

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
class Cluster:
    """Cluster data structure."""

    id: str
    name: str
    region: str
    datacenter: str
    headend_url: str
    status: str
    last_heartbeat: datetime
    client_count: int
    tenant: str
    metadata: dict | None = None


class ClusterManager:
    """Manages cluster registration and health monitoring using penguin-dal."""

    def __init__(self, db: Any, tenant_id: str) -> None:
        """Initialize ClusterManager.

        Args:
            db: penguin-dal AsyncDB instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id
        self.health_check_interval = 30

    async def initialize(self) -> None:
        """Initialize the ClusterManager."""
        try:
            logger.info("ClusterManager initialized", tenant=self.tenant_id)
        except Exception as e:
            logger.error("Failed to initialize ClusterManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the ClusterManager."""
        logger.info("ClusterManager shutdown complete")

    async def register_cluster(self, cluster_data: dict) -> tuple[Cluster, str]:
        """Register a new cluster and generate per-cluster API key.

        Args:
            cluster_data: Cluster data dictionary

        Returns:
            Tuple of (Cluster object, unencrypted API key)
        """
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        now = datetime.now(timezone.utc)

        await self.db.clusters.async_insert(
            id=cluster_data["id"],
            name=cluster_data["name"],
            region=cluster_data["region"],
            datacenter=cluster_data["datacenter"],
            headend_url=cluster_data["headend_url"],
            status="active",
            last_heartbeat=now,
            tenant=self.tenant_id,
            api_key_hash=api_key_hash,
            metadata=cluster_data.get("metadata", {}),
            created_at=now,
            updated_at=now,
        )

        cluster_obj = Cluster(
            id=cluster_data["id"],
            name=cluster_data["name"],
            region=cluster_data["region"],
            datacenter=cluster_data["datacenter"],
            headend_url=cluster_data["headend_url"],
            status="active",
            last_heartbeat=now,
            client_count=0,
            tenant=self.tenant_id,
            metadata=cluster_data.get("metadata", {}),
        )

        logger.info(
            "Registered cluster",
            cluster_id=cluster_obj.id,
            region=cluster_obj.region,
            datacenter=cluster_obj.datacenter,
            tenant=self.tenant_id,
        )

        return (cluster_obj, api_key)

    async def authenticate_cluster(self, api_key: str) -> Cluster | None:
        """Authenticate a cluster by API key.

        The API key hash is looked up globally (without tenant scoping) because
        the key itself IS the identity. Pre-authentication, the caller has no
        tenant context. The machine JWT issued from this authentication carries
        the cluster's real tenant ID, so downstream operations are tenant-scoped.

        Args:
            api_key: Unencrypted API key

        Returns:
            Cluster if authenticated, None otherwise
        """
        try:
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

            # Look up by hash globally (key IS the identity)
            rowset = await self.db(self.db.clusters.api_key_hash == api_key_hash).select()
            cluster_obj = rowset.first()

            if not cluster_obj:
                logger.warning(
                    "Cluster authentication rejected: key not found",
                    hash_prefix=api_key_hash[:8],
                )
                return None

            # Use constant-time comparison for stored hash
            if not hmac.compare_digest(cluster_obj.api_key_hash, api_key_hash):
                logger.warning(
                    "Cluster authentication rejected: hash mismatch",
                    cluster_id=cluster_obj.id,
                    tenant=cluster_obj.tenant,
                )
                return None

            # Update last_heartbeat on successful auth
            await self.db(self.db.clusters.id == cluster_obj.id).update(
                last_heartbeat=datetime.now(timezone.utc)
            )

            return Cluster(
                id=cluster_obj.id,
                name=cluster_obj.name,
                region=cluster_obj.region,
                datacenter=cluster_obj.datacenter,
                headend_url=cluster_obj.headend_url,
                status=cluster_obj.status,
                last_heartbeat=cluster_obj.last_heartbeat,
                client_count=cluster_obj.client_count,
                tenant=cluster_obj.tenant,
                metadata=cluster_obj.metadata,
            )
        except Exception as e:
            logger.error(
                "Cluster authentication error (fail closed)",
                error=str(e),
            )
            return None

    async def rotate_api_key(self, cluster_id: str) -> str | None:
        """Rotate API key for a cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            New unencrypted API key or None if cluster not found
        """
        new_api_key = secrets.token_urlsafe(32)
        new_api_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()

        rowset = await self.db(
            (self.db.clusters.id == cluster_id) & (self.db.clusters.tenant == self.tenant_id)
        ).select()
        cluster_obj = rowset.first()
        if not cluster_obj:
            return None

        await self.db(self.db.clusters.id == cluster_id).update(api_key_hash=new_api_key_hash)

        logger.info(
            "Rotated API key for cluster",
            cluster_id=cluster_id,
            tenant=self.tenant_id,
            key_prefix=new_api_key_hash[:8],
        )
        return new_api_key

    async def update_heartbeat(self, cluster_id: str, client_count: int | None = None) -> bool:
        """Update cluster heartbeat.

        Args:
            cluster_id: Cluster identifier
            client_count: Optional new client count

        Returns:
            True if successful, False if cluster not found
        """
        rowset = await self.db(
            (self.db.clusters.id == cluster_id) & (self.db.clusters.tenant == self.tenant_id)
        ).select()
        cluster_obj = rowset.first()
        if not cluster_obj:
            return False

        new_client_count = client_count if client_count is not None else cluster_obj.client_count
        await self.db(self.db.clusters.id == cluster_id).update(
            last_heartbeat=datetime.now(timezone.utc),
            status="active",
            client_count=new_client_count,
        )

        return True

    async def get_cluster(self, cluster_id: str) -> Cluster | None:
        """Get a cluster by ID.

        Args:
            cluster_id: Cluster identifier

        Returns:
            Cluster or None if not found
        """
        rowset = await self.db(
            (self.db.clusters.id == cluster_id) & (self.db.clusters.tenant == self.tenant_id)
        ).select()
        cluster_obj = rowset.first()
        if not cluster_obj:
            return None

        return Cluster(
            id=cluster_obj.id,
            name=cluster_obj.name,
            region=cluster_obj.region,
            datacenter=cluster_obj.datacenter,
            headend_url=cluster_obj.headend_url,
            status=cluster_obj.status,
            last_heartbeat=cluster_obj.last_heartbeat,
            client_count=cluster_obj.client_count,
            tenant=cluster_obj.tenant,
            metadata=cluster_obj.metadata,
        )

    async def get_all_clusters(self) -> list[Cluster]:
        """Get all clusters for the tenant.

        Returns:
            List of Cluster objects
        """
        rowset = await self.db(self.db.clusters.tenant == self.tenant_id).select()

        return [
            Cluster(
                id=c.id,
                name=c.name,
                region=c.region,
                datacenter=c.datacenter,
                headend_url=c.headend_url,
                status=c.status,
                last_heartbeat=c.last_heartbeat,
                client_count=c.client_count,
                tenant=c.tenant,
                metadata=c.metadata,
            )
            for c in rowset
        ]

    async def get_clusters_by_region(self, region: str) -> list[Cluster]:
        """Get clusters by region.

        Args:
            region: Region name

        Returns:
            List of Cluster objects
        """
        rowset = await self.db(
            (self.db.clusters.region == region) & (self.db.clusters.tenant == self.tenant_id)
        ).select()

        return [
            Cluster(
                id=c.id,
                name=c.name,
                region=c.region,
                datacenter=c.datacenter,
                headend_url=c.headend_url,
                status=c.status,
                last_heartbeat=c.last_heartbeat,
                client_count=c.client_count,
                tenant=c.tenant,
                metadata=c.metadata,
            )
            for c in rowset
        ]

    async def get_clusters_by_datacenter(self, datacenter: str) -> list[Cluster]:
        """Get clusters by datacenter.

        Args:
            datacenter: Datacenter name

        Returns:
            List of Cluster objects
        """
        rowset = await self.db(
            (self.db.clusters.datacenter == datacenter)
            & (self.db.clusters.tenant == self.tenant_id)
        ).select()

        return [
            Cluster(
                id=c.id,
                name=c.name,
                region=c.region,
                datacenter=c.datacenter,
                headend_url=c.headend_url,
                status=c.status,
                last_heartbeat=c.last_heartbeat,
                client_count=c.client_count,
                tenant=c.tenant,
                metadata=c.metadata,
            )
            for c in rowset
        ]

    async def remove_cluster(self, cluster_id: str) -> bool:
        """Remove a cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            True if successful, False if not found
        """
        rowset = await self.db(
            (self.db.clusters.id == cluster_id) & (self.db.clusters.tenant == self.tenant_id)
        ).select()
        cluster_obj = rowset.first()
        if not cluster_obj:
            return False

        await self.db(self.db.clusters.id == cluster_id).delete()
        logger.info("Removed cluster", cluster_id=cluster_id, tenant=self.tenant_id)
        return True

    async def monitor_health(self) -> None:
        """Monitor cluster health (background task)."""
        while True:
            try:
                await self._check_cluster_health()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error("Health monitoring error", error=str(e))
                await asyncio.sleep(5)

    async def _check_cluster_health(self) -> None:
        """Check cluster health and mark stale clusters."""
        # NOTE: last_heartbeat is stored as a naive sa.DateTime() column, so the
        # threshold must be naive too -- comparing against datetime.now(timezone.utc)
        # raises TypeError: can't compare offset-naive and offset-aware datetimes.
        stale_threshold = datetime.utcnow() - timedelta(minutes=5)

        rowset = await self.db(self.db.clusters.tenant == self.tenant_id).select()

        for cluster_obj in rowset:
            if cluster_obj.last_heartbeat < stale_threshold:
                if cluster_obj.status == "active":
                    await self.db(self.db.clusters.id == cluster_obj.id).update(status="stale")
                    logger.warning(
                        "Cluster marked as stale",
                        cluster_id=cluster_obj.id,
                        tenant=self.tenant_id,
                    )

    async def get_cluster_count(self) -> int:
        """Get count of clusters for the tenant.

        Returns:
            Number of clusters
        """
        count = await self.db(self.db.clusters.tenant == self.tenant_id).count()
        return count

    async def is_healthy(self) -> bool:
        """Check if manager is healthy.

        Returns:
            True if healthy
        """
        try:
            await self.get_cluster_count()
            return True
        except Exception:
            return False

    async def get_optimal_cluster(self, client_location: dict) -> Cluster | None:
        """Get optimal cluster for client location.

        Args:
            client_location: Client location dict with optional 'region' and 'datacenter'

        Returns:
            Optimal Cluster or None
        """
        region = client_location.get("region")
        datacenter = client_location.get("datacenter")

        candidates = []

        if datacenter:
            candidates = await self.get_clusters_by_datacenter(datacenter)

        if not candidates and region:
            candidates = await self.get_clusters_by_region(region)

        if not candidates:
            candidates = await self.get_all_clusters()

        active_candidates = [c for c in candidates if c.status == "active"]

        if not active_candidates:
            return None

        return min(active_candidates, key=lambda c: c.client_count)
