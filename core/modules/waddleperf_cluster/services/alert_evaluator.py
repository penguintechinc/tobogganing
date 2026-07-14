"""Alert rule evaluation and event generation for performance metrics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import structlog
from penguin_dal import AsyncDB

from core.notifications.service import NotificationService

log = structlog.get_logger(__name__)


class AlertEvaluator:
    """Evaluate performance results against alert rules and fire notifications."""

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

        # Get all enabled rules for this tenant
        rules_rowset = await self.db(
            (self.db.alert_rules.tenant == tenant) & (self.db.alert_rules.enabled == True)
        ).select()

        for rule_row in rules_rowset:
            rule_id = rule_row["id"]
            metric_name = rule_row["metric"]
            comparator = rule_row["comparator"]
            threshold = rule_row["threshold"]
            window_seconds = rule_row["window_seconds"]
            device_filter = rule_row["device_id"]
            test_type_filter = rule_row["test_type"]
            channel_id = rule_row["channel_id"]

            # Filter: if rule has device_filter, result's device_id must match
            if device_filter and result.get("device_id") != device_filter:
                continue

            # Filter: if rule has test_type_filter, result's test_type must match
            if test_type_filter and result.get("test_type") != test_type_filter:
                continue

            # Extract metric value from result
            # Metrics come from individual result fields (latency_ms, throughput, etc.)
            metric_value = result.get(metric_name)
            if metric_value is None:
                continue

            # Evaluate comparator
            breach = False
            if comparator == "gt":
                breach = metric_value > threshold
            elif comparator == "gte":
                breach = metric_value >= threshold
            elif comparator == "lt":
                breach = metric_value < threshold
            elif comparator == "lte":
                breach = metric_value <= threshold

            if not breach:
                continue

            # Dedup: check if an event for this rule fired within window
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(seconds=window_seconds)

            recent_events = await self.db(
                (self.db.alert_events.tenant == tenant)
                & (self.db.alert_events.rule_id == rule_id)
                & (self.db.alert_events.fired_at >= window_start)
            ).select()

            if recent_events.first():
                # Event already fired within window, skip
                log.info(
                    "alert_dedup_skipped",
                    rule_id=rule_id,
                    tenant=tenant,
                    metric=metric_name,
                )
                continue

            # Insert alert event
            event_id = str(uuid4())
            await self.db.alert_events.async_insert(
                id=event_id,
                tenant=tenant,
                rule_id=rule_id,
                device_id=result.get("device_id"),
                observed_value=metric_value,
                fired_at=now,
                notified=False,
            )

            # Send notification if channel is configured
            if channel_id:
                try:
                    rule_name = rule_row["name"]
                    subject = f"Alert: {rule_name}"
                    body = f"Rule '{rule_name}' breached: {metric_name}={metric_value} (threshold={threshold})"

                    await self.notifications.notify(
                        tenant,
                        subject,
                        body,
                        channel_ids=[channel_id],
                    )

                    # Mark event as notified
                    await self.db(
                        self.db.alert_events.id == event_id
                    ).update(notified=True)

                    log.info(
                        "alert_notification_sent",
                        event_id=event_id,
                        rule_id=rule_id,
                        tenant=tenant,
                    )

                except Exception as e:
                    log.error(
                        "alert_notification_failed",
                        event_id=event_id,
                        rule_id=rule_id,
                        tenant=tenant,
                        error=str(e),
                    )
                    # Do NOT re-raise; evaluation must never fail ingest

            events_fired += 1
            log.info(
                "alert_event_fired",
                event_id=event_id,
                rule_id=rule_id,
                tenant=tenant,
                metric=metric_name,
                observed=metric_value,
                threshold=threshold,
            )

        return events_fired

    async def sweep(self) -> int:
        """Sweep for alerts across all tenants (scheduler job).

        MVP: re-check latest result per (rule, device) within window.

        Returns:
            Number of alert events fired during sweep
        """
        # Placeholder MVP: iterate all rules, check most recent result per (rule, device)
        # For production, would use aggregation from StatsManager
        events_fired = 0

        # Get all enabled rules across all tenants
        rules_rowset = await self.db(
            self.db.alert_rules.enabled == True
        ).select()

        for rule_row in rules_rowset:
            tenant = rule_row["tenant"]
            rule_id = rule_row["id"]
            device_filter = rule_row["device_id"]
            test_type_filter = rule_row["test_type"]
            metric_name = rule_row["metric"]
            threshold = rule_row["threshold"]
            comparator = rule_row["comparator"]
            window_seconds = rule_row["window_seconds"]
            channel_id = rule_row["channel_id"]

            # Determine device scope
            devices_to_check = []
            if device_filter:
                devices_to_check = [device_filter]
            else:
                # Check all devices for this tenant
                device_rowset = await self.db(
                    self.db.devices.tenant == tenant
                ).select()
                devices_to_check = [d["id"] for d in device_rowset]

            for device_id in devices_to_check:
                # Get latest result for this device within window
                now = datetime.now(timezone.utc)
                window_start = now - timedelta(seconds=window_seconds)

                query_parts = [
                    self.db.perf_test_results.tenant == tenant,
                    self.db.perf_test_results.device_id == device_id,
                    self.db.perf_test_results.completed_at >= window_start,
                ]

                if test_type_filter:
                    query_parts.append(self.db.perf_test_results.test_type == test_type_filter)

                # Combine conditions
                condition = query_parts[0]
                for part in query_parts[1:]:
                    condition = condition & part

                result_rowset = await self.db(condition).select()

                if not result_rowset:
                    continue

                # Get latest result
                latest = result_rowset.last()
                if not latest:
                    continue

                # Extract metric value
                metric_value = latest.get(metric_name)
                if metric_value is None:
                    continue

                # Evaluate breachcondition
                breach = False
                if comparator == "gt":
                    breach = metric_value > threshold
                elif comparator == "gte":
                    breach = metric_value >= threshold
                elif comparator == "lt":
                    breach = metric_value < threshold
                elif comparator == "lte":
                    breach = metric_value <= threshold

                if not breach:
                    continue

                # Check dedup
                recent_events = await self.db(
                    (self.db.alert_events.tenant == tenant)
                    & (self.db.alert_events.rule_id == rule_id)
                    & (self.db.alert_events.fired_at >= window_start)
                ).select()

                if recent_events.first():
                    # Event already fired within window
                    continue

                # Fire event
                event_id = str(uuid4())
                await self.db.alert_events.async_insert(
                    id=event_id,
                    tenant=tenant,
                    rule_id=rule_id,
                    device_id=device_id,
                    observed_value=metric_value,
                    fired_at=now,
                    notified=False,
                )

                # Send notification if channel configured
                if channel_id:
                    try:
                        rule_name = rule_row["name"]
                        subject = f"Alert: {rule_name}"
                        body = f"Rule '{rule_name}' breached: {metric_name}={metric_value} (threshold={threshold})"

                        await self.notifications.notify(
                            tenant,
                            subject,
                            body,
                            channel_ids=[channel_id],
                        )

                        await self.db(
                            self.db.alert_events.id == event_id
                        ).update(notified=True)

                    except Exception as e:
                        log.error(
                            "alert_sweep_notification_failed",
                            event_id=event_id,
                            rule_id=rule_id,
                            error=str(e),
                        )

                events_fired += 1
                log.info(
                    "alert_sweep_fired",
                    event_id=event_id,
                    rule_id=rule_id,
                    device_id=device_id,
                )

        return events_fired
