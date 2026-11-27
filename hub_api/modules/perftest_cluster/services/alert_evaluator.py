"""Alert rule evaluation and event generation for performance metrics."""

from __future__ import annotations

import operator
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import structlog
from penguin_dal import AsyncDB

from hub_api.notifications.service import NotificationService

log = structlog.get_logger(__name__)

_COMPARATORS: dict[str, Callable[[float, float], bool]] = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


class AlertEvaluator:
    """Evaluate performance results against alert rules and fire notifications."""

    SWEEP_PAGE_SIZE = 500

    def __init__(self, db: AsyncDB, notifications: NotificationService) -> None:
        """Initialize alert evaluator.

        Args:
            db: AsyncDB instance for rule and event queries
            notifications: NotificationService for sending alerts
        """
        self.db = db
        self.notifications = notifications

    async def evaluate_result(self, tenant: str, result: dict[str, Any]) -> int:
        """Evaluate a test result against enabled alert rules.

        Result dict contains test metrics:
        - device_id: Device ID (str)
        - test_type: Test type (str)
        - latency_ms: Latency in milliseconds (float or None)
        - throughput: Throughput metric (float or None)
        - status: Test status (str)

        Metrics are matched against rules by name (e.g., "latency_ms", "throughput").
        Rules may filter on device_id and/or test_type; all must match for evaluation.

        Comparators: gt, gte, lt, lte

        Window dedup: skip firing if an event for the same rule fired within
        window_seconds (query recent alert_events for rule_id, tenant).

        Args:
            tenant: Tenant ID
            result: Result dict with test metrics

        Returns:
            Number of alert events fired
        """
        events_fired = 0
        size = self.SWEEP_PAGE_SIZE
        offset = 0
        while True:
            page = await self.db(
                (self.db.alert_rules.tenant == tenant) & (self.db.alert_rules.enabled == True)  # noqa: E712 -- DAL query syntax
            ).select(orderby=[self.db.alert_rules.id], limitby=(offset, offset + size))
            rows = list(page)
            for rule_row in rows:
                if rule_row["device_id"] and result.get("device_id") != rule_row["device_id"]:
                    continue
                if rule_row["test_type"] and result.get("test_type") != rule_row["test_type"]:
                    continue
                metric_value = result.get(rule_row["metric"])
                if metric_value is None or not _breached(
                    rule_row["comparator"], metric_value, rule_row["threshold"]
                ):
                    continue
                window_start = datetime.now(timezone.utc) - timedelta(
                    seconds=rule_row["window_seconds"]
                )
                if await self._fire(
                    rule_row, tenant, result.get("device_id"), metric_value, window_start
                ):
                    events_fired += 1
            if len(rows) < size:
                break
            offset += size
        return events_fired

    async def sweep(self, page_size: int | None = None) -> int:
        """Sweep enabled alert rules across all tenants (scheduler job).

        Bounded batch evaluation: rules are read in keyset pages of ``page_size``
        ordered by (tenant, id), so memory is O(page_size) regardless of table
        size. Every downstream query (devices, results, dedup) is scoped to the
        rule's own tenant; tenant-wide rules page through that tenant's devices.

        Args:
            page_size: Rules/devices per page; defaults to ``SWEEP_PAGE_SIZE``.

        Returns:
            Number of alert events fired during sweep
        """
        size = page_size or self.SWEEP_PAGE_SIZE
        if size < 1:
            raise ValueError("page_size must be >= 1")
        events_fired = 0
        rules_scanned = 0
        offset = 0
        while True:
            page = await self.db(
                self.db.alert_rules.enabled == True  # noqa: E712 -- DAL query syntax
            ).select(
                orderby=[self.db.alert_rules.tenant, self.db.alert_rules.id],
                limitby=(offset, offset + size),
            )
            rows = list(page)
            if not rows:
                break
            for rule_row in rows:
                rules_scanned += 1
                events_fired += await self._sweep_rule(rule_row, size)
            if len(rows) < size:
                break
            offset += size
        log.info("alert_sweep_complete", rules_scanned=rules_scanned, events_fired=events_fired)
        return events_fired

    async def _iter_device_ids(self, tenant: str, size: int) -> AsyncIterator[str]:
        """Yield a tenant's device ids in bounded pages ordered by id."""
        offset = 0
        while True:
            page = await self.db(self.db.devices.tenant == tenant).select(
                orderby=[self.db.devices.id], limitby=(offset, offset + size)
            )
            rows = list(page)
            for d in rows:
                yield d["id"]
            if len(rows) < size:
                return
            offset += size

    async def _sweep_rule(self, rule_row: Any, size: int) -> int:
        """Evaluate one rule against the latest in-window result per device."""
        tenant = rule_row["tenant"]
        window_start = datetime.now(timezone.utc) - timedelta(seconds=rule_row["window_seconds"])
        fired = 0
        if rule_row["device_id"]:
            devices: AsyncIterator[str] = _single(rule_row["device_id"])
        else:
            devices = self._iter_device_ids(tenant, size)
        async for device_id in devices:
            condition = (
                (self.db.perf_test_results.tenant == tenant)
                & (self.db.perf_test_results.device_id == device_id)
                & (self.db.perf_test_results.completed_at >= window_start)
            )
            if rule_row["test_type"]:
                condition = condition & (
                    self.db.perf_test_results.test_type == rule_row["test_type"]
                )
            latest_rows = await self.db(condition).select(
                orderby=self.db.perf_test_results.completed_at.column.desc(),
                limitby=(0, 1),
            )
            latest = latest_rows.first()
            if not latest:
                continue
            metric_value = latest.get(rule_row["metric"])
            if metric_value is None or not _breached(
                rule_row["comparator"], metric_value, rule_row["threshold"]
            ):
                continue
            if await self._fire(rule_row, tenant, device_id, metric_value, window_start):
                fired += 1
        return fired

    async def _fire(
        self,
        rule_row: Any,
        tenant: str,
        device_id: str | None,
        metric_value: float,
        window_start: datetime,
    ) -> bool:
        """Dedup, persist and notify one alert event; return True if fired."""
        rule_id = rule_row["id"]
        recent = await self.db(
            (self.db.alert_events.tenant == tenant)
            & (self.db.alert_events.rule_id == rule_id)
            & (self.db.alert_events.fired_at >= window_start)
        ).select(limitby=(0, 1))
        if recent.first():
            log.info("alert_dedup_skipped", rule_id=rule_id, tenant=tenant)
            return False
        event_id = str(uuid4())
        await self.db.alert_events.async_insert(
            id=event_id,
            tenant=tenant,
            rule_id=rule_id,
            device_id=device_id,
            observed_value=metric_value,
            fired_at=datetime.now(timezone.utc),
            notified=False,
        )
        channel_id = rule_row["channel_id"]
        rule_name = rule_row["name"]
        try:
            await self.notifications.notify(
                tenant,
                f"Alert: {rule_name}",
                f"Rule '{rule_name}' breached: {rule_row['metric']}={metric_value} "
                f"(threshold={rule_row['threshold']})",
                channel_ids=[channel_id] if channel_id else None,
            )
            await self.db(self.db.alert_events.id == event_id).update(notified=True)
            log.info("alert_notification_sent", event_id=event_id, rule_id=rule_id, tenant=tenant)
        except Exception as e:  # evaluation must never fail ingest/sweep
            log.error(
                "alert_notification_failed",
                event_id=event_id,
                rule_id=rule_id,
                tenant=tenant,
                error=str(e),
            )
        log.info(
            "alert_event_fired",
            event_id=event_id,
            rule_id=rule_id,
            tenant=tenant,
            metric=rule_row["metric"],
            observed=metric_value,
            threshold=rule_row["threshold"],
        )
        return True


def _breached(comparator: str, value: float, threshold: float) -> bool:
    """Return True when ``value`` breaches ``threshold`` under ``comparator``."""
    if comparator not in _COMPARATORS:
        log.warning("alert_unknown_comparator", comparator=comparator)
        return False
    return _COMPARATORS[comparator](value, threshold)


async def _single(value: str) -> AsyncIterator[str]:
    """Yield a single value as an async iterator."""
    yield value
