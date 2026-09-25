"""Suricata EVE JSON adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from .base import AdapterHit, AnalysisAdapter


logger = structlog.get_logger()

# Map Suricata alert.severity to blocklist severity levels
# 1=critical, 2=high, 3=medium, 4+=low
SEVERITY_MAP = {
    1: "critical",
    2: "high",
    3: "medium",
    4: "low",
}


class SuricataAdapter(AnalysisAdapter):
    """Parse Suricata EVE JSON output and extract IOCs.

    Reads newline-delimited EVE JSON events from Suricata IDS,
    extracts IOCs (dest IP, hostnames, URLs, file hashes) from alerts,
    and emits them as AdapterHits for blocklist storage.
    """

    source = "suricata"

    def parse(self, raw: str) -> list[AdapterHit]:
        """Parse EVE JSON lines and extract IOC hits.

        Args:
            raw: Raw EVE JSON (newline-delimited).

        Returns:
            List of AdapterHits extracted from alert events.
        """
        hits = []
        first_seen_ts = int(datetime.now(timezone.utc).timestamp())

        for line in raw.strip().split("\n"):
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("suricata_eve_malformed_json")
                continue

            # Only process alert events
            if event.get("event_type") != "alert":
                continue

            try:
                severity = self._map_severity(event.get("alert", {}).get("severity"))
                hits.extend(self._extract_hits(event, severity, first_seen_ts))
            except Exception as e:
                logger.warning("suricata_eve_parse_error", error=str(e))
                continue

        return hits

    def _map_severity(self, suricata_severity: int | None) -> str:
        """Map Suricata severity level to blocklist severity.

        Args:
            suricata_severity: Suricata alert severity (1-4+).

        Returns:
            Blocklist severity level (critical, high, medium, low).
        """
        if not suricata_severity:
            return "low"
        if suricata_severity <= 0:
            return "low"
        return SEVERITY_MAP.get(suricata_severity, "low")

    def _extract_hits(
        self, event: dict, severity: str, first_seen_ts: int
    ) -> list[AdapterHit]:
        """Extract IOC hits from an EVE alert event.

        Extracts:
        - dest_ip -> ip IOC
        - tls.sni or http.hostname -> domain IOC
        - http.url -> url IOC
        - fileinfo.sha256 -> hash IOC

        Args:
            event: Parsed EVE event dict.
            severity: Normalized severity level.
            first_seen_ts: Unix timestamp for first_seen.

        Returns:
            List of AdapterHits.
        """
        hits = []

        # Extract destination IP
        dest_ip = event.get("dest_ip")
        if dest_ip:
            hits.append(
                AdapterHit(
                    ioc_type="ip",
                    value=dest_ip,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="dest_ip from alert",
                )
            )

        # Extract hostname from TLS SNI or HTTP
        hostname = event.get("tls", {}).get("sni") or event.get("http", {}).get(
            "hostname"
        )
        if hostname:
            hits.append(
                AdapterHit(
                    ioc_type="domain",
                    value=hostname,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="hostname from tls.sni or http.hostname",
                )
            )

        # Extract URL
        url = event.get("http", {}).get("url")
        if url:
            # Construct full URL if needed
            dest_ip_for_url = event.get("dest_ip", "")
            dest_port = event.get("dest_port", 80)
            protocol = "https" if dest_port == 443 else "http"
            if hostname:
                full_url = f"{protocol}://{hostname}{url}"
            else:
                full_url = f"{protocol}://{dest_ip_for_url}:{dest_port}{url}"

            hits.append(
                AdapterHit(
                    ioc_type="url",
                    value=full_url,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="url from http.url",
                )
            )

        # Extract file hash (SHA-256)
        sha256 = event.get("fileinfo", {}).get("sha256")
        if sha256:
            hits.append(
                AdapterHit(
                    ioc_type="hash",
                    value=sha256,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="sha256 from fileinfo",
                )
            )

        return hits
