"""Threat detection logging and statistics."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List
import uuid

import structlog

from .models import ThreatDetection, ThreatIndicator

logger = logging.getLogger(__name__)
slog = structlog.get_logger()


class DetectionLogger:
    """Log threat detection events."""

    def __init__(self, db: Any) -> None:
        """Initialize detection logger.

        Args:
            db: penguin-dal DAL instance.
        """
        self.db = db

    async def log_threat_detection(
        self,
        tenant_id: str,
        client_ip: str,
        requested_domain: str | None = None,
        requested_ip: str | None = None,
        action_taken: str = "blocked",
        threat_details: List[Dict[str, Any]] | None = None,
    ) -> str:
        """Log a threat detection event.

        Args:
            tenant_id: Tenant ID for tenant-scoping.
            client_ip: Client IP address.
            requested_domain: Requested domain (if applicable).
            requested_ip: Requested IP (if applicable).
            action_taken: Action taken (blocked/logged/allowed).
            threat_details: List of threat details.

        Returns:
            Detection record ID.
        """
        try:
            highest_confidence = 0
            all_threat_types = []
            sources = []

            if threat_details:
                for threat in threat_details:
                    conf = threat.get("confidence", 0)
                    if conf > highest_confidence:
                        highest_confidence = conf

                    all_threat_types.extend(threat.get("threat_types", []))
                    src = threat.get("source")
                    if src and src not in sources:
                        sources.append(src)

            detection_id = str(uuid.uuid4())

            # Insert via penguin-dal
            await self.db.threat_detections.async_insert(
                id=detection_id,
                tenant_id=tenant_id,
                client_ip=client_ip,
                requested_domain=requested_domain,
                requested_ip=requested_ip,
                action_taken=action_taken,
                threat_types=json.dumps(list(set(all_threat_types))),
                confidence=highest_confidence,
                source=",".join(sources) if sources else None,
                metadata=json.dumps(
                    {
                        "threat_details": threat_details,
                        "detection_method": "security_feeds",
                    }
                ),
            )

            slog.warning(
                "threat_detected",
                client_ip=client_ip,
                requested_domain=requested_domain,
                requested_ip=requested_ip,
                action=action_taken,
                confidence=highest_confidence,
                tenant_id=tenant_id,
            )

            return detection_id
        except Exception as e:
            logger.error(f"Failed to log threat detection: {e}")
            return ""

    async def get_threat_statistics(
        self, tenant_id: str, hours_back: int = 24
    ) -> Dict[str, Any]:
        """Get threat detection statistics for a tenant.

        Args:
            tenant_id: Tenant ID.
            hours_back: Hours to look back (default 24).

        Returns:
            Statistics dictionary.
        """
        since = datetime.utcnow() - timedelta(hours=hours_back)

        try:
            # Total detections
            total_detections = await self.db(
                (self.db.threat_detections.tenant_id == tenant_id)
                & (self.db.threat_detections.detected_at >= since)
            ).async_count()

            # Detections by action (simplified for penguin-dal)
            action_counts = {}
            for action in ["blocked", "logged", "allowed"]:
                count = await self.db(
                    (self.db.threat_detections.tenant_id == tenant_id)
                    & (self.db.threat_detections.action_taken == action)
                    & (self.db.threat_detections.detected_at >= since)
                ).async_count()
                if count > 0:
                    action_counts[action] = count

            # Active indicators count
            active_indicators = await self.db(
                (self.db.threat_indicators.tenant_id == tenant_id)
                & (self.db.threat_indicators.active == True)
            ).async_count()

            # Indicators by source
            source_counts = {}
            for source in ["blackweb", "spamhaus", "ipvoid", "dnsbl"]:
                count = await self.db(
                    (self.db.threat_indicators.tenant_id == tenant_id)
                    & (self.db.threat_indicators.source == source)
                    & (self.db.threat_indicators.active == True)
                ).async_count()
                if count > 0:
                    source_counts[source] = count

            return {
                "period_hours": hours_back,
                "total_detections": total_detections,
                "action_counts": action_counts,
                "active_indicators": active_indicators,
                "indicators_by_source": source_counts,
            }
        except Exception as e:
            logger.error(f"Failed to get threat statistics: {e}")
            return {
                "period_hours": hours_back,
                "total_detections": 0,
                "action_counts": {},
                "active_indicators": 0,
                "indicators_by_source": {},
            }

    async def get_top_threat_sources(
        self, tenant_id: str, hours_back: int = 24, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top threat sources by detection count.

        Args:
            tenant_id: Tenant ID.
            hours_back: Hours to look back.
            limit: Max number of results.

        Returns:
            List of top sources with counts.
        """
        since = datetime.utcnow() - timedelta(hours=hours_back)
        top_sources = []

        try:
            rows = await self.db(
                (self.db.threat_detections.tenant_id == tenant_id)
                & (self.db.threat_detections.detected_at >= since)
            ).async_select(
                self.db.threat_detections.source,
                orderby=~self.db.threat_detections.id.count(),
                groupby=self.db.threat_detections.source,
                limitby=(0, limit),
            )

            for row in rows:
                if row.get("source"):
                    top_sources.append(
                        {"source": row["source"], "count": row.get("count", 0)}
                    )
        except Exception as e:
            logger.debug(f"Failed to get top threat sources: {e}")

        return top_sources
