"""Performance test statistics and aggregation using penguin-dal."""
from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Any

logger = structlog.get_logger()


class StatsManager:
    """Manages statistics and aggregation over performance test results."""

    def __init__(self, db: object, tenant: str) -> None:
        """Initialize StatsManager.

        Args:
            db: penguin-dal DAL instance
            tenant: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant = tenant

    async def initialize(self) -> None:
        """Initialize the StatsManager."""
        try:
            logger.info("StatsManager initialized", tenant=self.tenant)
        except Exception as e:
            logger.error("Failed to initialize StatsManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the StatsManager."""
        logger.info("StatsManager shutdown complete")

    async def summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get overall statistics summary.

        Args:
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)

        Returns:
            Dictionary with overall statistics
        """
        try:
            # Parse date filters
            start_dt: datetime | None = None
            end_dt: datetime | None = None

            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Build query with tenant scoping
            query = self.db.perf_test_results.tenant == self.tenant

            # Add date filters to query
            if start_dt:
                query = query & (self.db.perf_test_results.created_at >= start_dt)
            if end_dt:
                query = query & (self.db.perf_test_results.created_at <= end_dt)

            # Execute query
            rowset = await self.db(query).select()
            results = list(rowset)
        except Exception as e:
            logger.error("summary_query_error", error=str(e), tenant=self.tenant)
            return {
                "total_tests": 0,
                "completed_count": 0,
                "pending_count": 0,
                "failed_count": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "avg_throughput": 0.0,
            }

        total = len(results)

        if total == 0:
            return {
                "total_tests": 0,
                "completed_count": 0,
                "pending_count": 0,
                "failed_count": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "avg_throughput": 0.0,
            }

        # Count by status
        completed_count = sum(1 for r in results if r.status == "completed")
        pending_count = sum(1 for r in results if r.status == "pending")
        failed_count = sum(1 for r in results if r.status == "failed")
        success_count = sum(1 for r in results if r.status == "completed" and r.latency_ms)

        success_rate = (success_count / total * 100) if total > 0 else 0.0

        # Calculate averages
        latencies = [r.latency_ms for r in results if r.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        throughputs = [r.throughput for r in results if r.throughput is not None]
        avg_throughput = sum(throughputs) / len(throughputs) if throughputs else 0.0

        return {
            "total_tests": total,
            "completed_count": completed_count,
            "pending_count": pending_count,
            "failed_count": failed_count,
            "success_rate": round(success_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "avg_throughput": round(avg_throughput, 2),
        }

    async def by_device(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get statistics aggregated by device.

        Args:
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            limit: Maximum number of devices

        Returns:
            List of per-device statistics
        """
        try:
            # Parse date filters
            start_dt: datetime | None = None
            end_dt: datetime | None = None

            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Build query with tenant scoping
            query = self.db.perf_test_results.tenant == self.tenant

            # Add date filters to query
            if start_dt:
                query = query & (self.db.perf_test_results.created_at >= start_dt)
            if end_dt:
                query = query & (self.db.perf_test_results.created_at <= end_dt)

            # Execute query
            rowset = await self.db(query).select()
            results = list(rowset)
        except Exception as e:
            logger.error("by_device_query_error", error=str(e), tenant=self.tenant)
            return []

        # Aggregate by device_id
        device_stats: dict[str, dict[str, Any]] = {}
        for r in results:
            device_id = r.device_id
            if device_id not in device_stats:
                device_stats[device_id] = {
                    "total": 0,
                    "completed": 0,
                    "latencies": [],
                    "throughputs": [],
                }

            device_stats[device_id]["total"] += 1
            if r.status == "completed":
                device_stats[device_id]["completed"] += 1
            if r.latency_ms is not None:
                device_stats[device_id]["latencies"].append(r.latency_ms)
            if r.throughput is not None:
                device_stats[device_id]["throughputs"].append(r.throughput)

        # Build results sorted by total tests
        output = []
        for device_id, stats in sorted(
            device_stats.items(), key=lambda x: x[1]["total"], reverse=True
        )[:limit]:
            total = stats["total"]
            completed = stats["completed"]
            success_rate = (completed / total * 100) if total > 0 else 0.0
            avg_latency = (
                sum(stats["latencies"]) / len(stats["latencies"])
                if stats["latencies"]
                else 0.0
            )
            avg_throughput = (
                sum(stats["throughputs"]) / len(stats["throughputs"])
                if stats["throughputs"]
                else 0.0
            )

            output.append(
                {
                    "device_id": device_id,
                    "total_tests": total,
                    "completed_count": completed,
                    "success_rate": round(success_rate, 2),
                    "avg_latency_ms": round(avg_latency, 2),
                    "avg_throughput": round(avg_throughput, 2),
                }
            )

        return output

    async def by_type(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get statistics aggregated by test type.

        Args:
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            limit: Maximum number of test types

        Returns:
            List of per-test-type statistics
        """
        try:
            # Parse date filters
            start_dt: datetime | None = None
            end_dt: datetime | None = None

            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Build query with tenant scoping
            query = self.db.perf_test_results.tenant == self.tenant

            # Add date filters to query
            if start_dt:
                query = query & (self.db.perf_test_results.created_at >= start_dt)
            if end_dt:
                query = query & (self.db.perf_test_results.created_at <= end_dt)

            # Execute query
            rowset = await self.db(query).select()
            results = list(rowset)
        except Exception as e:
            logger.error("by_type_query_error", error=str(e), tenant=self.tenant)
            return []

        # Aggregate by test_type
        type_stats: dict[str, dict[str, Any]] = {}
        for r in results:
            test_type = r.test_type or "unknown"

            if test_type not in type_stats:
                type_stats[test_type] = {
                    "total": 0,
                    "completed": 0,
                    "latencies": [],
                    "throughputs": [],
                }

            type_stats[test_type]["total"] += 1
            if r.status == "completed":
                type_stats[test_type]["completed"] += 1
            if r.latency_ms is not None:
                type_stats[test_type]["latencies"].append(r.latency_ms)
            if r.throughput is not None:
                type_stats[test_type]["throughputs"].append(r.throughput)

        # Build results sorted by total tests
        output = []
        for test_type, stats in sorted(
            type_stats.items(), key=lambda x: x[1]["total"], reverse=True
        )[:limit]:
            total = stats["total"]
            completed = stats["completed"]
            success_rate = (completed / total * 100) if total > 0 else 0.0
            avg_latency = (
                sum(stats["latencies"]) / len(stats["latencies"])
                if stats["latencies"]
                else 0.0
            )
            avg_throughput = (
                sum(stats["throughputs"]) / len(stats["throughputs"])
                if stats["throughputs"]
                else 0.0
            )

            output.append(
                {
                    "test_type": test_type,
                    "total_tests": total,
                    "completed_count": completed,
                    "success_rate": round(success_rate, 2),
                    "avg_latency_ms": round(avg_latency, 2),
                    "avg_throughput": round(avg_throughput, 2),
                }
            )

        return output

    async def trends(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        interval: str = "daily",
        metric: str = "success_rate",
    ) -> dict[str, Any]:
        """Get time-series data for trends.

        Args:
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            interval: Time interval (hourly, daily, weekly)
            metric: Metric to trend (success_rate, avg_latency, count)

        Returns:
            Dictionary with time-series data
        """
        try:
            # Parse date filters
            start_dt: datetime | None = None
            end_dt: datetime | None = None

            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Build query with tenant scoping
            query = self.db.perf_test_results.tenant == self.tenant

            # Add date filters to query
            if start_dt:
                query = query & (self.db.perf_test_results.created_at >= start_dt)
            if end_dt:
                query = query & (self.db.perf_test_results.created_at <= end_dt)

            # Execute query
            rowset = await self.db(query).select()
            results = list(rowset)
        except Exception as e:
            logger.error("trends_query_error", error=str(e), tenant=self.tenant)
            return {
                "timestamps": [],
                "values": [],
                "metric": metric,
                "interval": interval,
            }

        # Aggregate by time interval
        time_buckets: dict[str, dict[str, Any]] = {}
        for r in results:
            dt = r.created_at
            if interval == "hourly":
                key = dt.replace(minute=0, second=0, microsecond=0)
            elif interval == "weekly":
                key = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                # Round down to Monday
                days_since_monday = key.weekday()
                key = key - timedelta(days=days_since_monday)
            else:  # daily
                key = dt.replace(hour=0, minute=0, second=0, microsecond=0)

            key_str = key.isoformat()
            if key_str not in time_buckets:
                time_buckets[key_str] = {"total": 0, "completed": 0, "latencies": []}

            time_buckets[key_str]["total"] += 1
            if r.status == "completed":
                time_buckets[key_str]["completed"] += 1
            if r.latency_ms is not None:
                time_buckets[key_str]["latencies"].append(r.latency_ms)

        # Calculate metric for each bucket
        timestamps = []
        values = []
        for key_str in sorted(time_buckets.keys()):
            timestamps.append(key_str)
            bucket = time_buckets[key_str]
            total = bucket["total"]

            if metric == "success_rate":
                value = (bucket["completed"] / total * 100) if total > 0 else 0.0
            elif metric == "avg_latency":
                latencies = bucket["latencies"]
                value = sum(latencies) / len(latencies) if latencies else 0.0
            else:  # count
                value = total

            values.append(round(value, 2))

        return {
            "timestamps": timestamps,
            "values": values,
            "metric": metric,
            "interval": interval,
        }

    async def recent(
        self,
        device_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent test results.

        Args:
            device_id: Filter by device ID
            limit: Number of recent tests

        Returns:
            List of recent test results
        """
        try:
            # Build query with tenant scoping
            query = self.db.perf_test_results.tenant == self.tenant

            # Add device filter if provided
            if device_id:
                query = query & (self.db.perf_test_results.device_id == device_id)

            # Execute query with limit and order by created_at descending
            rowset = await self.db(query).select(
                orderby=self.db.perf_test_results.created_at.column.desc(),
                limitby=(0, limit),
            )
            results = list(rowset)
        except Exception as e:
            logger.error("recent_query_error", error=str(e), tenant=self.tenant)
            return []

        return [
            {
                "id": r.id,
                "device_id": r.device_id,
                "test_type": r.test_type,
                "status": r.status,
                "target": r.target,
                "latency_ms": r.latency_ms,
                "throughput": r.throughput,
                "completed_at": r.completed_at.isoformat()
                if r.completed_at
                else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ]
