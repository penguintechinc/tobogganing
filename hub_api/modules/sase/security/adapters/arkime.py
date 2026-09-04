"""Arkime network session adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from .base import AdapterHit, AnalysisAdapter


logger = structlog.get_logger()


class ArkimeAdapter(AnalysisAdapter):
    """Parse Arkime session tags and extract IOC hits.

    Reads Arkime session data, checks for malicious tags, and extracts
    source/destination IPs and hostnames as IOCs.
    """

    source = "arkime"

    def parse(self, raw: str) -> list[AdapterHit]:
        """Parse Arkime session data and extract IOC hits.

        Args:
            raw: Raw Arkime session (JSON).

        Returns:
            List of AdapterHits extracted from sessions.
        """
        hits = []
        first_seen_ts = int(datetime.now(timezone.utc).timestamp())

        for line in raw.strip().split("\n"):
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("arkime_session_malformed_json")
                continue

            try:
                hits.extend(
                    self._extract_hits(event, first_seen_ts)
                )
            except Exception as e:
                logger.warning("arkime_session_parse_error", error=str(e))
                continue

        return hits

    def _extract_hits(
        self, event: dict, first_seen_ts: int
    ) -> list[AdapterHit]:
        """Extract IOC hits from an Arkime session.

        Extracts: src/dst IPs and hostnames if session has malicious tags.

        Args:
            event: Parsed Arkime session dict.
            first_seen_ts: Unix timestamp for first_seen.

        Returns:
            List of AdapterHits (empty if session has no malicious tags).
        """
        hits = []

        # Only emit hits if session has malicious tags
        tags = event.get("tags", [])
        malicious_keywords = [
            "malware",
            "c2",
            "c2-traffic",
            "botnet",
            "exploit",
            "trojan",
            "ransomware",
            "suspicious",
        ]

        has_malicious_tag = any(
            tag.lower() in malicious_keywords
            or any(kw in tag.lower() for kw in malicious_keywords)
            for tag in tags
        )

        if not has_malicious_tag:
            return hits

        # Map tags to severity
        severity = "high"
        if any("c2" in tag.lower() for tag in tags):
            severity = "critical"

        # Extract source IP
        src_ip = event.get("srcIp")
        if src_ip:
            hits.append(
                AdapterHit(
                    ioc_type="ip",
                    value=src_ip,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="src IP from Arkime session",
                )
            )

        # Extract destination IP
        dst_ip = event.get("dstIp")
        if dst_ip and dst_ip != src_ip:
            hits.append(
                AdapterHit(
                    ioc_type="ip",
                    value=dst_ip,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="dst IP from Arkime session",
                )
            )

        # Extract hostnames
        hostnames = event.get("hostnames", [])
        for hostname in hostnames:
            if hostname:
                hits.append(
                    AdapterHit(
                        ioc_type="domain",
                        value=hostname,
                        severity=severity,
                        first_seen=first_seen_ts,
                        detail="hostname from Arkime session",
                    )
                )

        return hits
