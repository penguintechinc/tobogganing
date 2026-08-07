"""Zeek notice log adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from .base import AdapterHit, AnalysisAdapter


logger = structlog.get_logger()


class ZeekAdapter(AnalysisAdapter):
    """Parse Zeek notice.log JSON and extract IOC hits.

    Reads notice.log entries (typically JSON or TSV), extracts suspicious
    IPs and domains from fields like src, dst, query, or hostname.
    """

    source = "zeek"

    def parse(self, raw: str) -> list[AdapterHit]:
        """Parse Zeek notice.log JSON lines and extract IOC hits.

        Args:
            raw: Raw Zeek notice.log JSON (newline-delimited or single).

        Returns:
            List of AdapterHits extracted from notices.
        """
        hits = []
        first_seen_ts = int(datetime.now(timezone.utc).timestamp())

        for line in raw.strip().split("\n"):
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("zeek_notice_malformed_json")
                continue

            try:
                severity = self._severity_from_note(event.get("note", ""))
                hits.extend(
                    self._extract_hits(event, severity, first_seen_ts)
                )
            except Exception as e:
                logger.warning("zeek_notice_parse_error", error=str(e))
                continue

        return hits

    def _severity_from_note(self, note: str) -> str:
        """Map Zeek notice type to severity level.

        Args:
            note: Zeek notice type (e.g., "Phishing::Suspicious_IP").

        Returns:
            Severity level (critical, high, medium, low).
        """
        # Heuristic: certain keywords in notice type imply higher severity
        lower_note = note.lower()
        if any(kw in lower_note for kw in ["malware", "trojan", "ransomware"]):
            return "critical"
        elif any(
            kw in lower_note
            for kw in ["suspicious", "exploit", "phishing", "c2"]
        ):
            return "high"
        elif any(kw in lower_note for kw in ["anomaly", "policy"]):
            return "medium"
        else:
            return "low"

    def _extract_hits(
        self, event: dict, severity: str, first_seen_ts: int
    ) -> list[AdapterHit]:
        """Extract IOC hits from a Zeek notice event.

        Extracts: src (IP), dst (IP), query/domain (domain).

        Args:
            event: Parsed Zeek event dict.
            severity: Normalized severity level.
            first_seen_ts: Unix timestamp for first_seen.

        Returns:
            List of AdapterHits.
        """
        hits = []

        # Extract source IP
        src = event.get("src") or event.get("id.orig_h")
        if src:
            hits.append(
                AdapterHit(
                    ioc_type="ip",
                    value=src,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="src from Zeek notice",
                )
            )

        # Extract destination IP
        dst = event.get("dst") or event.get("id.resp_h")
        if dst and dst != src:  # Avoid duplicates
            hits.append(
                AdapterHit(
                    ioc_type="ip",
                    value=dst,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="dst from Zeek notice",
                )
            )

        # Extract domain from query or hostname
        domain = event.get("query") or event.get("hostname")
        if domain:
            hits.append(
                AdapterHit(
                    ioc_type="domain",
                    value=domain,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="domain from Zeek notice",
                )
            )

        return hits
