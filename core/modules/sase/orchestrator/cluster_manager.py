"""Cluster management using penguin-dal."""
from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

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

    def __init__(self, db: object, tenant_id: str) -> None:
        """Initialize ClusterManager.

        Args:
            db: penguin-dal DAL instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id
        self.health_check_interval = 30
        self._lock = asyncio.Lock()

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

    async def register_cluster(self, cluster_data: dict) -> Cluster:
        """Register a new cluster.

        Args:
            cluster_data: Cluster data dictionary

        Returns:
            Registered Cluster object
        """
        async with self._lock:
            cluster_obj = await asyncio.to_thread(
                self.db.clusters.create,
                id=cluster_data["id"],
                name=cluster_data["name"],
                region=cluster_data["region"],
                datacenter=cluster_data["datacenter"],
                headend_url=cluster_data["headend_url"],
                status="active",
                last_heartbeat=datetime.now(timezone.utc),
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

    async def update_heartbeat(
        self, cluster_id: str, client_count: int | None = None
    ) -> bool:
        """Update cluster heartbeat.

        Args:
            cluster_id: Cluster identifier
            client_count: Optional new client count

        Returns:
            True if successful, False if cluster not found
        """
        async with self._lock:
            cluster_obj = await asyncio.to_thread(
                self.db.clusters.select,
                id=cluster_id,
                tenant=self.tenant_id,
            )
            if not cluster_obj:
                return False

            await asyncio.to_thread(
                cluster_obj.update,
                last_heartbeat=datetime.now(timezone.utc),
                status="active",
                client_count=client_count or cluster_obj.client_count,
            )

            return True

    async def get_cluster(self, cluster_id: str) -> Cluster | None:
        """Get a cluster by ID.

        Args:
            cluster_id: Cluster identifier

        Returns:
            Cluster or None if not found
        """
        cluster_obj = await asyncio.to_thread(
            self.db.clusters.select,
            id=cluster_id,
            tenant=self.tenant_id,
        )
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
        clusters = await asyncio.to_thread(
            self.db.clusters.select_list,
            tenant=self.tenant_id,
        )

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
            for c in clusters
        ]

    async def get_clusters_by_region(self, region: str) -> list[Cluster]:
        """Get clusters by region.

        Args:
            region: Region name

        Returns:
            List of Cluster objects
        """
        clusters = await asyncio.to_thread(
            self.db.clusters.select_list,
            region=region,
            tenant=self.tenant_id,
        )

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
            for c in clusters
        ]

    async def get_clusters_by_datacenter(self, datacenter: str) -> list[Cluster]:
        """Get clusters by datacenter.

        Args:
            datacenter: Datacenter name

        Returns:
            List of Cluster objects
        """
        clusters = await asyncio.to_thread(
            self.db.clusters.select_list,
            datacenter=datacenter,
            tenant=self.tenant_id,
        )

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
            for c in clusters
        ]

    async def remove_cluster(self, cluster_id: str) -> bool:
        """Remove a cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            True if successful, False if not found
        """
        async with self._lock:
            cluster_obj = await asyncio.to_thread(
                self.db.clusters.select,
                id=cluster_id,
                tenant=self.tenant_id,
            )
            if not cluster_obj:
                return False

            await asyncio.to_thread(cluster_obj.delete)
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
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=5)

        async with self._lock:
            clusters = await asyncio.to_thread(
                self.db.clusters.select_list,
                tenant=self.tenant_id,
            )

            for cluster_obj in clusters:
                if cluster_obj.last_heartbeat < stale_threshold:
                    if cluster_obj.status == "active":
                        await asyncio.to_thread(cluster_obj.update, status="stale")
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
        clusters = await asyncio.to_thread(
            self.db.clusters.select_list,
            tenant=self.tenant_id,
        )
        return len(clusters)

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

    async def get_optimal_cluster(
        self, client_location: dict
    ) -> Cluster | None:
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
