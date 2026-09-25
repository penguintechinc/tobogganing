"""Strelka file scanning adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from .base import AdapterHit, AnalysisAdapter


logger = structlog.get_logger()


class StrelkaAdapter(AnalysisAdapter):
    """Parse Strelka scan events and extract IOC hits.

    Reads Strelka file scan results, checks for YARA matches and suspicious
    indicators, and extracts file hashes as IOCs.
    """

    source = "strelka"

    def parse(self, raw: str) -> list[AdapterHit]:
        """Parse Strelka scan results and extract IOC hits.

        Args:
            raw: Raw Strelka scan result (JSON).

        Returns:
            List of AdapterHits extracted from scan results.
        """
        hits = []
        first_seen_ts = int(datetime.now(timezone.utc).timestamp())

        for line in raw.strip().split("\n"):
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("strelka_scan_malformed_json")
                continue

            try:
                # Only emit hits if YARA rules matched or file is tagged as malware
                hits.extend(
                    self._extract_hits(event, first_seen_ts)
                )
            except Exception as e:
                logger.warning("strelka_scan_parse_error", error=str(e))
                continue

        return hits

    def _extract_hits(
        self, event: dict, first_seen_ts: int
    ) -> list[AdapterHit]:
        """Extract IOC hits from a Strelka scan result.

        Extracts: file hash (SHA-256) if YARA matches or malware tags present.

        Args:
            event: Parsed Strelka scan event dict.
            first_seen_ts: Unix timestamp for first_seen.

        Returns:
            List of AdapterHits (empty if no indicators of compromise).
        """
        hits = []

        # Check for YARA matches or malware tags
        has_yara_matches = False
        yara_module = event.get("modules", {}).get("yara")
        if yara_module:
            rules = yara_module.get("rules", [])
            has_yara_matches = len(rules) > 0 and any(
                r.get("matches") for r in rules
            )

        tags = event.get("tags", [])
        has_malware_tag = any(
            tag in ["malware", "trojan", "ransomware", "worm", "virus"]
            for tag in tags
        )

        # Only extract hash if there's an indication of compromise
        if has_yara_matches or has_malware_tag:
            sha256 = event.get("hashes", {}).get("sha256")
            if sha256:
                # Determine severity based on YARA match count
                severity = "high"
                if has_yara_matches and yara_module:
                    rule_count = len(yara_module.get("rules", []))
                    if rule_count >= 3:
                        severity = "critical"

                hits.append(
                    AdapterHit(
                        ioc_type="hash",
                        value=sha256,
                        severity=severity,
                        first_seen=first_seen_ts,
                        detail="malicious file from Strelka scan",
                    )
                )

        return hits
