"""Usage metering for license reporting."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Usage:
    """Usage snapshot for license keepalive reporting."""

    seats: int  # Distinct active identities (human or machine/AI)
    nodes: int  # Count of registered clusters/headends/testservers
    features: frozenset[str]  # Enabled Enterprise features


class UsageReporter:
    """Reports usage metrics to the license server."""

    def __init__(
        self,
        db: object,
        license_client: object,
        node_counter: Optional[Callable[[], int]] = None,
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
                # Count total users (both active and inactive for now)
                # In Phase 1, we count all users; Phase 3 can add activity filter
                # Use a condition that matches all rows (id != "")
                result = await self.db(self.db.users.id != "").select()
                seats = len(result) if result else 0
            except Exception as e:
                logger.error(f"Failed to count users: {e}")
                seats = 0

            # Get node count from injected callable
            nodes = 0
            try:
                nodes = self.node_counter()
            except Exception as e:
                logger.error(f"Failed to get node count: {e}")
                nodes = 0

            # Collect enabled Enterprise features from registry
            features_set: set[str] = set()
            try:
                from quart import current_app

                registry = current_app.registry
                for entitlement in registry._entitlements:
                    # Only include Enterprise features that are enabled
                    if entitlement.tier.lower() == "enterprise":
                        # Check if the feature is enabled via flags
                        from core.flags import feature_enabled

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
                    self.license_client.keepalive(usage_data)
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
