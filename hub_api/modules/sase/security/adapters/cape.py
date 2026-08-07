"""CAPE sandbox verdict adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from .base import AdapterHit, AnalysisAdapter


logger = structlog.get_logger()


class CapeAdapter(AnalysisAdapter):
    """Parse CAPE sandbox verdicts and extract IOC hits.

    Reads CAPE sandbox analysis results, extracts indicators of compromise
    (file hashes, C2 IPs, C2 domains) from malicious verdicts.
    """

    source = "cape"

    def parse(self, raw: str) -> list[AdapterHit]:
        """Parse CAPE verdicts and extract IOC hits.

        Args:
            raw: Raw CAPE verdict (JSON).

        Returns:
            List of AdapterHits extracted from verdict.
        """
        hits = []
        first_seen_ts = int(datetime.now(timezone.utc).timestamp())

        for line in raw.strip().split("\n"):
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("cape_verdict_malformed_json")
                continue

            try:
                hits.extend(
                    self._extract_hits(event, first_seen_ts)
                )
            except Exception as e:
                logger.warning("cape_verdict_parse_error", error=str(e))
                continue

        return hits

    def _extract_hits(
        self, event: dict, first_seen_ts: int
    ) -> list[AdapterHit]:
        """Extract IOC hits from a CAPE verdict.

        Extracts: sample SHA-256, C2 IPs and domains from network indicators.

        Args:
            event: Parsed CAPE verdict dict.
            first_seen_ts: Unix timestamp for first_seen.

        Returns:
            List of AdapterHits (empty if verdict is benign).
        """
        hits = []

        # Only emit hits if verdict is malicious (malscore > 5.0)
        malscore = event.get("malscore", 0.0)
        verdict = event.get("verdict", "").lower()
        is_malicious = malscore > 5.0 or verdict == "malicious"

        if not is_malicious:
            return hits

        # Map malscore to severity
        if malscore >= 8.0 or verdict == "malicious":
            severity = "critical"
        elif malscore >= 6.0:
            severity = "high"
        else:
            severity = "medium"

        # Extract sample hash
        sha256 = event.get("sha256")
        if sha256:
            hits.append(
                AdapterHit(
                    ioc_type="hash",
                    value=sha256,
                    severity=severity,
                    first_seen=first_seen_ts,
                    detail="malware sample from CAPE",
                )
            )

        # Extract network indicators from sandbox network activity
        network = event.get("network", {})

        # TCP connections (potential C2)
        tcp_connections = network.get("tcp", [])
        for conn in tcp_connections:
            dst_ip = conn.get("dst")
            if dst_ip:
                hits.append(
                    AdapterHit(
                        ioc_type="ip",
                        value=dst_ip,
                        severity=severity,
                        first_seen=first_seen_ts,
                        detail="C2 IP from CAPE TCP connection",
                    )
                )

        # DNS queries (potential C2 domains)
        dns_requests = network.get("dns", [])
        for dns in dns_requests:
            domain = dns.get("request")
            if domain:
                hits.append(
                    AdapterHit(
                        ioc_type="domain",
                        value=domain,
                        severity=severity,
                        first_seen=first_seen_ts,
                        detail="C2 domain from CAPE DNS query",
                    )
                )

        # HTTP requests (potential malware download URLs)
        http_requests = network.get("http", [])
        for http in http_requests:
            uri = http.get("uri")
            if uri:
                hits.append(
                    AdapterHit(
                        ioc_type="url",
                        value=uri,
                        severity=severity,
                        first_seen=first_seen_ts,
                        detail="malware download URL from CAPE HTTP",
                    )
                )

        return hits
