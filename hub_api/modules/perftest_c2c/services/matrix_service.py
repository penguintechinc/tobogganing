"""Cluster-to-cluster results matrix aggregation and trending."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

logger = structlog.get_logger()


class MatrixService:
    """Aggregates and visualizes cluster-to-cluster test results matrices."""

    def __init__(self, db: Any, tenant: str) -> None:
        """Initialize MatrixService.

        Args:
            db: penguin-dal AsyncDB instance
            tenant: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant = tenant

    async def latest_matrix(self, test_type: str) -> dict[str, object]:
        """Build the latest NxN region matrix for a test type.

        Selects the most recent c2c_pair_results per (source_region, dest_region)
        for the given test_type, and builds a grid structure.

        Args:
            test_type: Test type to aggregate

        Returns:
            Dict with keys: test_type, regions (sorted list), cells (list of
            {source, dest, status, latency_ms, measured_at})
        """
        # Get all pair results for this test_type and tenant
        rowset = await self.db(
            (self.db.c2c_pair_results.tenant == self.tenant)
            & (self.db.c2c_pair_results.test_type == test_type)
        ).select()

        results = list(rowset) if rowset else []

        # Build region set and map (source_region, dest_region) -> latest result
        regions_set: set[str] = set()
        latest_per_pair: dict[tuple[str, str], Any] = {}

        for result in results:
            regions_set.add(result.source_region)
            regions_set.add(result.dest_region)

            key = (result.source_region, result.dest_region)
            existing = latest_per_pair.get(key)

            # Keep the most recent result for this pair
            if existing is None or (result.measured_at and existing.measured_at and
                                    result.measured_at > existing.measured_at):
                latest_per_pair[key] = result

        regions = sorted(list(regions_set))

        # Build cells
        cells = []
        for (source_region, dest_region), result in latest_per_pair.items():
            cells.append({
                "source": source_region,
                "dest": dest_region,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "throughput": result.throughput,
                "loss_pct": result.loss_pct,
                "measured_at": result.measured_at.isoformat() if result.measured_at else None,
            })

        return {
            "test_type": test_type,
            "regions": regions,
            "cells": cells,
        }

    async def run_matrix(self, run_id: str) -> dict[str, object]:
        """Build the region grid for one run's pair results.

        Args:
            run_id: Run ID

        Returns:
            Dict with keys: run_id, test_types (list), regions (sorted list),
            cells (list of {source, dest, test_type, status, latency_ms, measured_at})
        """
        # Get all pair results for this run and tenant
        rowset = await self.db(
            (self.db.c2c_pair_results.tenant == self.tenant)
            & (self.db.c2c_pair_results.run_id == run_id)
        ).select()

        results = list(rowset) if rowset else []

        # Build region set, test_type set, and cells
        regions_set: set[str] = set()
        test_types_set: set[str] = set()
        cells = []

        for result in results:
            regions_set.add(result.source_region)
            regions_set.add(result.dest_region)
            test_types_set.add(result.test_type)

            cells.append({
                "source": result.source_region,
                "dest": result.dest_region,
                "test_type": result.test_type,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "throughput": result.throughput,
                "loss_pct": result.loss_pct,
                "measured_at": result.measured_at.isoformat() if result.measured_at else None,
            })

        regions = sorted(list(regions_set))
        test_types = sorted(list(test_types_set))

        return {
            "run_id": run_id,
            "test_types": test_types,
            "regions": regions,
            "cells": cells,
        }

    async def trends(
        self,
        source_region: str,
        dest_region: str,
        test_type: str,
        window: int = 20,
    ) -> list[dict[str, object]]:
        """Get recent pair results for a region pair and test type.

        Returns the last `window` pair results, oldest to newest.

        Args:
            source_region: Source region
            dest_region: Destination region
            test_type: Test type
            window: Number of recent results to return

        Returns:
            List of dicts (oldest to newest) with keys: measured_at, latency_ms, status
        """
        # Get all pair results for this region pair and test_type
        rowset = await self.db(
            (self.db.c2c_pair_results.tenant == self.tenant)
            & (self.db.c2c_pair_results.source_region == source_region)
            & (self.db.c2c_pair_results.dest_region == dest_region)
            & (self.db.c2c_pair_results.test_type == test_type)
        ).select()

        results = list(rowset) if rowset else []

        # Sort by measured_at oldest to newest
        sorted_results = sorted(
            results,
            key=lambda r: r.measured_at or datetime.min.replace(tzinfo=timezone.utc),
        )

        # Limit to window
        limited = sorted_results[-window:] if window > 0 else sorted_results

        return [
            {
                "measured_at": r.measured_at.isoformat() if r.measured_at else None,
                "latency_ms": r.latency_ms,
                "throughput": r.throughput,
                "loss_pct": r.loss_pct,
                "status": r.status,
            }
            for r in limited
        ]
