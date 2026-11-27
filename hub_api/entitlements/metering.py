"""Usage metering for license reporting."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Usage:
    """Usage snapshot for license keepalive reporting."""

    seats: int  # Distinct active identities (human or machine/AI)
    nodes: int  # Enrolled compute objects seen within NODE_STALENESS_DAYS
    features: frozenset[str]  # Enabled Enterprise features


async def count_active_seats(db: Any) -> int:
    """Count distinct active identities (seats) from users table.

    Args:
        db: penguin-dal database connection

    Returns:
        Number of distinct active identities in the users table.
    """
    try:
        # Query all users (both active and inactive; Phase 3 can add activity filter)
        def query_users() -> int:
            try:
                result = db.users.select()
                return len(result) if result else 0
            except Exception as e:
                logger.error(f"Error in query_users: {e}")
                return 0

        # Run sync DB query in thread pool to avoid blocking async context
        count = await asyncio.to_thread(query_users)
        return count
    except Exception as e:
        logger.error(f"Failed to count active seats: {e}")
        return 0


NODE_STALENESS_DAYS = 30
"""No-contact window after which an enrolled node frees its license slot."""


async def _count(db: Any, query: Any) -> int:
    """Run ``db(query).count()`` on a sync or async penguin-dal handle."""
    result = db(query).count()
    if inspect.isawaitable(result):
        result = await result
    return int(result or 0)


async def count_registered_nodes(db: Any, now: datetime | None = None) -> int:
    """Count licensable nodes: enrolled compute objects seen in the last 30 days.

    Per org licensing (critical-rules.md Licensing Model), a node is the compute
    object/OS instance, counted only once *enrolled* (credentialed and checked
    in). Here that is SASE clusters/headends (enrolled via API key, heartbeat
    required) plus WaddlePerf devices that have checked in at least once
    (``last_heartbeat`` set). A node with no contact for ``NODE_STALENESS_DAYS``
    frees its slot; reappearance simply re-counts. Overage is reported only and
    never blocks enrollment -- this function is metering, not enforcement.

    Args:
        db: penguin-dal database connection (sync or async)
        now: Reference time (UTC); defaults to the current time.

    Returns:
        Number of enrolled, non-stale nodes; 0 on query failure (logged).
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=NODE_STALENESS_DAYS)
    try:
        clusters = await _count(
            db,
            (db.clusters.last_heartbeat != None) & (db.clusters.last_heartbeat >= cutoff),  # noqa: E711
        )
        devices = await _count(
            db,
            (db.devices.last_heartbeat != None) & (db.devices.last_heartbeat >= cutoff),  # noqa: E711
        )
        return clusters + devices
    except Exception as e:
        logger.error(f"Failed to count registered nodes: {e}")
        return 0


class UsageReporter:
    """Reports usage metrics to the license server."""

    def __init__(
        self,
        db: object,
        license_client: object,
        node_counter: Optional[Callable[[], Any]] = None,
    ) -> None:
        """
        Initialize the usage reporter.

        Args:
            db: Database connection (penguin-dal)
            license_client: License server client
            node_counter: Callable that returns node count (defaults to lambda: 0)
        """
        self.db = db
        self.license_client = license_client
        self.node_counter = node_counter or (lambda: 0)
        self._last_snapshot: Optional[Usage] = None

    async def snapshot(self) -> Usage:
        """
        Capture a usage snapshot.

        Returns:
            Usage dataclass with seats, nodes, and enabled features.
        """
        try:
            # Count distinct active identities (seats) from users table
            seats = 0
            try:
                seats = await count_active_seats(self.db)
            except Exception as e:
                logger.error(f"Failed to count users: {e}")
                seats = 0

            # Get node count from injected callable
            nodes = 0
            try:
                counted = self.node_counter()
                nodes = int(await counted) if inspect.isawaitable(counted) else int(counted)
            except Exception as e:
                logger.error(f"Failed to get node count: {e}")
                nodes = 0

            # Collect enabled Enterprise features from registry
            features_set: set[str] = set()
            try:
                from quart import current_app

                registry = current_app.registry  # type: ignore[attr-defined]
                for entitlement in registry._entitlements:  # type: ignore[attr-defined]
                    # Only include Enterprise features that are enabled
                    if entitlement.tier.lower() == "enterprise":
                        # Check if the feature is enabled via flags
                        from hub_api.flags import feature_enabled

                        # Parse feature name (format: "module.feature")
                        if "." in entitlement.feature:
                            module, feature = entitlement.feature.rsplit(".", 1)
                            if feature_enabled(module, feature, licensed=True):
                                features_set.add(entitlement.feature)
            except Exception as e:
                logger.error(f"Failed to collect enabled features: {e}")

            # Create usage snapshot
            usage = Usage(
                seats=seats,
                nodes=nodes,
                features=frozenset(features_set),
            )

            # Cache the snapshot
            self._last_snapshot = usage

            return usage

        except Exception as e:
            logger.error(f"Usage snapshot failed: {e}")
            # Return cached snapshot if available, otherwise empty
            if self._last_snapshot:
                return self._last_snapshot
            return Usage(seats=0, nodes=0, features=frozenset())

    async def report(self) -> bool:
        """
        Report usage to the license server.

        This is a best-effort, non-blocking operation that catches all exceptions.
        Never raises or blocks request paths.

        Returns:
            True if report was successful, False otherwise.
        """
        try:
            # Get current usage snapshot
            usage = await self.snapshot()

            # Prepare usage payload for license client
            usage_data = {
                "seats": usage.seats,
                "nodes": usage.nodes,
                "features": list(usage.features),
            }

            # Send keepalive with usage data
            # Run in thread since license_client is sync
            def send_keepalive() -> bool:
                if self.license_client is None:
                    return False

                try:
                    self.license_client.keepalive(usage_data)  # type: ignore[attr-defined]
                    logger.info(
                        f"Usage reported: seats={usage.seats}, nodes={usage.nodes}, "
                        f"features={len(usage.features)}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"License keepalive failed: {e}")
                    return False

            result = await asyncio.to_thread(send_keepalive)
            return result

        except Exception as e:
            # Log but never raise
            logger.error(f"Usage report failed: {e}")
            return False
