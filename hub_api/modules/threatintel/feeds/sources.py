"""Security feed source parsers and fetchers."""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

import aiohttp
import dns.resolver

logger = logging.getLogger(__name__)


class ThreatType(Enum):
    """Types of threats from security feeds."""

    MALWARE_DOMAIN = "malware_domain"
    PHISHING_DOMAIN = "phishing_domain"
    SPAM_DOMAIN = "spam_domain"
    BOTNET_IP = "botnet_ip"
    MALWARE_IP = "malware_ip"
    SCANNING_IP = "scanning_ip"
    REPUTATION_IP = "reputation_ip"
    BLACKLISTED_DOMAIN = "blacklisted_domain"
    BLACKLISTED_IP = "blacklisted_ip"


class FeedSource(Enum):
    """Security feed sources.

    BLACKWEB/SPAMHAUS/IPVOID/DNSBL are the built-in, hardcoded system feeds
    (SecurityFeedsManager.feed_configs). MISP/STIX/TAXII/CSV identify
    user-configured feed sources (FeedSourceManager) ingested via
    hub_api.modules.threatintel.feeds.ingestor.
    """

    BLACKWEB = "blackweb"
    SPAMHAUS = "spamhaus"
    IPVOID = "ipvoid"
    DNSBL = "dnsbl"
    MISP = "misp"
    STIX = "stix"
    TAXII = "taxii"
    CSV = "csv"


@dataclass(slots=True)
class ThreatIndicator:
    """Security threat indicator."""

    indicator_type: str
    value: str
    threat_types: List[ThreatType]
    source: FeedSource
    confidence: int
    first_seen: datetime
    last_seen: datetime
    ttl: int
    metadata: Dict[str, Any]


def parse_blackweb_domains(content: str) -> List[str]:
    """Parse Blackweb domains file."""
    domains = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("!"):
            domain = line.replace("||", "").replace("^", "").replace("*", "")
            if "." in domain and len(domain) > 3:
                domains.append(domain)
    return domains


def parse_blackweb_ips(content: str) -> List[str]:
    """Parse Blackweb IPs file."""
    ips = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                ipaddress.ip_network(line, strict=False)
                ips.append(line)
            except ValueError:
                continue
    return ips


def parse_spamhaus_drop(content: str) -> List[str]:
    """Parse Spamhaus DROP/EDROP file."""
    networks = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith(";"):
            parts = line.split(";")[0].strip()
            try:
                ipaddress.ip_network(parts, strict=False)
                networks.append(parts)
            except ValueError:
                continue
    return networks


async def fetch_blackweb_domains(session: aiohttp.ClientSession, url: str) -> List[str]:
    """Fetch and parse Blackweb domains feed.

    Raises:
        Exception: On network error or non-200 response (fail-open).
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                content = await resp.text()
                return parse_blackweb_domains(content)
            raise RuntimeError(f"HTTP {resp.status} from Blackweb domains feed")
    except Exception as e:
        logger.error(f"Failed to fetch Blackweb domains: {e}")
        raise


async def fetch_blackweb_ips(session: aiohttp.ClientSession, url: str) -> List[str]:
    """Fetch and parse Blackweb IPs feed.

    Raises:
        Exception: On network error or non-200 response (fail-open).
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                content = await resp.text()
                return parse_blackweb_ips(content)
            raise RuntimeError(f"HTTP {resp.status} from Blackweb IPs feed")
    except Exception as e:
        logger.error(f"Failed to fetch Blackweb IPs: {e}")
        raise


async def fetch_spamhaus_drop(session: aiohttp.ClientSession, url: str) -> List[str]:
    """Fetch and parse Spamhaus DROP feed.

    Raises:
        Exception: On network error or non-200 response (fail-open).
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                content = await resp.text()
                return parse_spamhaus_drop(content)
            raise RuntimeError(f"HTTP {resp.status} from Spamhaus DROP feed")
    except Exception as e:
        logger.error(f"Failed to fetch Spamhaus DROP: {e}")
        raise


async def query_dnsbl(ip_addr: str, dnsbl_providers: List[str]) -> List[str]:
    """Query DNSBL providers for IP reputation."""
    results = []
    try:
        ip_obj = ipaddress.ip_address(ip_addr)
        reversed_ip = str(ip_obj.reverse_pointer)

        for provider in dnsbl_providers:
            query_host = f"{reversed_ip}{provider}"
            try:
                dns.resolver.resolve(query_host, "A", lifetime=2)
                results.append(provider)
            except (dns.resolver.NXDOMAIN, dns.resolver.Timeout, Exception):
                continue
    except Exception as e:
        logger.debug(f"DNSBL query error for {ip_addr}: {e}")
    return results


def build_threat_indicator(
    indicator_type: str,
    value: str,
    threat_types: List[ThreatType],
    source: FeedSource,
    confidence: int,
    ttl: int,
    metadata: Dict[str, Any] | None = None,
) -> ThreatIndicator:
    """Build a ThreatIndicator dataclass."""
    return ThreatIndicator(
        indicator_type=indicator_type,
        value=value,
        threat_types=threat_types,
        source=source,
        confidence=confidence,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        ttl=ttl,
        metadata=metadata or {},
    )
