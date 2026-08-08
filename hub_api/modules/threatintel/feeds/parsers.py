"""Threat intelligence feed parsers for MISP, OpenIOC, CSV, and STIX formats."""
from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime
from io import StringIO
from typing import Any, Dict
from urllib.parse import urlparse

try:
    from defusedxml import ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

try:
    import stix2
except ImportError:
    stix2 = None  # type: ignore

from .sources import FeedSource, ThreatIndicator, ThreatType

logger = logging.getLogger(__name__)


def parse_misp_feed(payload: Dict | list) -> list[ThreatIndicator]:
    """Parse MISP JSON export format.

    Args:
        payload: MISP JSON payload (dict or list).

    Returns:
        List of ThreatIndicator dataclass instances.
        Malformed records are skipped; returns partial results.
    """
    indicators = []

    try:
        # Handle MISP event structure
        if isinstance(payload, dict) and "Event" in payload:
            events = (
                [payload["Event"]]
                if isinstance(payload["Event"], dict)
                else payload["Event"]
            )
        elif isinstance(payload, dict) and "response" in payload:
            events = payload["response"]
        elif isinstance(payload, list):
            events = payload
        else:
            events = [payload]

        for event in events:
            try:
                event_id = event.get("id", "")
                event_info = event.get("info", "")

                # Process attributes
                attributes = event.get("Attribute", [])
                for attr in attributes:
                    try:
                        attr_type = attr.get("type", "")
                        attr_value = attr.get("value", "")
                        attr_confidence = int(attr.get("confidence", 50))

                        # Map MISP types to indicator types
                        indicator_type = _misp_type_to_indicator_type(attr_type)
                        if indicator_type and _is_valid_indicator(attr_value, indicator_type):
                            threat_types = [ThreatType.BLACKLISTED_DOMAIN]
                            if indicator_type == "ip":
                                threat_types = [ThreatType.BLACKLISTED_IP]

                            metadata: Dict[str, Any] = {
                                "source_format": "misp",
                                "misp_event_id": str(event_id),
                                "misp_attribute_id": str(attr.get("id", "")),
                                "misp_event": event_info,
                                "misp_category": attr.get("category", ""),
                                "misp_comment": attr.get("comment", ""),
                                "tags": [tag.get("name", "") for tag in attr.get("Tag", [])],
                            }

                            indicator = ThreatIndicator(
                                indicator_type=indicator_type,
                                value=attr_value.lower() if indicator_type == "domain" else attr_value,
                                threat_types=threat_types,
                                source=FeedSource.BLACKWEB,  # Default source
                                confidence=attr_confidence,
                                first_seen=_parse_misp_date(attr.get("first_seen")) or datetime.utcnow(),
                                last_seen=_parse_misp_date(attr.get("last_seen")) or datetime.utcnow(),
                                ttl=86400,  # 1 day default
                                metadata=metadata,
                            )
                            indicators.append(indicator)
                    except (KeyError, ValueError, TypeError):
                        # Skip malformed attributes
                        continue
            except (KeyError, ValueError, TypeError):
                # Skip malformed events
                continue

    except Exception as e:
        logger.warning(f"Error parsing MISP feed: {e}")

    return indicators


def parse_openioc_feed(xml_text: str) -> list[ThreatIndicator]:
    """Parse OpenIOC XML format.

    Args:
        xml_text: OpenIOC XML content.

    Returns:
        List of ThreatIndicator dataclass instances.
        Malformed records are skipped; returns partial results.
    """
    indicators = []

    try:
        root = ET.fromstring(xml_text)

        # Extract metadata from IOC definition
        ioc_id = root.get("id", "")
        ioc_name = ""
        ioc_description = ""

        # Get IOC metadata
        short_desc = root.find(".//short_description")
        if short_desc is not None:
            ioc_name = short_desc.text or ""

        desc = root.find(".//description")
        if desc is not None:
            ioc_description = desc.text or ""

        # OpenIOC uses IndicatorItem elements within Definition/Criteria
        for indicator_item in root.findall(".//IndicatorItem"):
            try:
                context_elem = indicator_item.find("Context")
                content_elem = indicator_item.find("Content")

                if context_elem is not None and content_elem is not None:
                    context_type = context_elem.get("type", "")
                    context_document = context_elem.get("document", "")
                    context_search = context_elem.get("search", "")
                    indicator_value = content_elem.text

                    if not indicator_value:
                        continue

                    indicator_value = indicator_value.strip()

                    # Map OpenIOC context types to indicators
                    if any(
                        net_type in context_type
                        for net_type in [
                            "Network/DNS",
                            "DnsEntryItem",
                            "DNS",
                            "HostnameItem",
                        ]
                    ):
                        # DNS/Domain indicators
                        if _is_valid_domain(indicator_value):
                            metadata: Dict[str, Any] = {
                                "source_format": "openioc",
                                "openioc_context": context_type,
                                "openioc_document": context_document,
                                "openioc_search": context_search,
                                "openioc_id": ioc_id,
                                "openioc_name": ioc_name,
                                "openioc_description": ioc_description,
                            }
                            indicator = ThreatIndicator(
                                indicator_type="domain",
                                value=indicator_value.lower(),
                                threat_types=[ThreatType.BLACKLISTED_DOMAIN],
                                source=FeedSource.BLACKWEB,
                                confidence=75,
                                first_seen=datetime.utcnow(),
                                last_seen=datetime.utcnow(),
                                ttl=86400,
                                metadata=metadata,
                            )
                            indicators.append(indicator)

                    elif any(
                        ip_type in context_type
                        for ip_type in [
                            "Network/IP",
                            "NetworkItem",
                            "PortItem/remoteIP",
                            "RouteEntryItem",
                        ]
                    ):
                        # IP indicators
                        ip_values = _extract_ips_from_openioc_value(indicator_value)
                        for ip in ip_values:
                            try:
                                if _is_valid_ip(ip):
                                    metadata: Dict[str, Any] = {
                                        "source_format": "openioc",
                                        "openioc_context": context_type,
                                        "openioc_document": context_document,
                                        "openioc_search": context_search,
                                        "openioc_id": ioc_id,
                                        "openioc_name": ioc_name,
                                        "openioc_description": ioc_description,
                                        "original_value": indicator_value,
                                    }
                                    indicator = ThreatIndicator(
                                        indicator_type="ip",
                                        value=ip,
                                        threat_types=[ThreatType.BLACKLISTED_IP],
                                        source=FeedSource.BLACKWEB,
                                        confidence=75,
                                        first_seen=datetime.utcnow(),
                                        last_seen=datetime.utcnow(),
                                        ttl=86400,
                                        metadata=metadata,
                                    )
                                    indicators.append(indicator)
                            except (ValueError, TypeError):
                                continue

                    elif any(
                        url_type in context_type
                        for url_type in [
                            "Network/URI",
                            "UrlHistoryItem",
                            "Network/UserAgent",
                        ]
                    ):
                        # URL indicators - extract domains
                        try:
                            parsed_url = urlparse(indicator_value)
                            if parsed_url.netloc and _is_valid_domain(parsed_url.netloc):
                                metadata: Dict[str, Any] = {
                                    "source_format": "openioc",
                                    "openioc_context": context_type,
                                    "openioc_id": ioc_id,
                                    "openioc_name": ioc_name,
                                    "original_url": indicator_value,
                                }
                                indicator = ThreatIndicator(
                                    indicator_type="domain",
                                    value=parsed_url.netloc.lower(),
                                    threat_types=[ThreatType.BLACKLISTED_DOMAIN],
                                    source=FeedSource.BLACKWEB,
                                    confidence=75,
                                    first_seen=datetime.utcnow(),
                                    last_seen=datetime.utcnow(),
                                    ttl=86400,
                                    metadata=metadata,
                                )
                                indicators.append(indicator)
                        except (ValueError, TypeError):
                            continue

            except Exception as e:
                logger.debug(f"Failed to parse OpenIOC indicator item: {e}")
                continue

    except ET.ParseError as e:
        logger.warning(f"Error parsing OpenIOC XML: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error parsing OpenIOC feed: {e}")

    return indicators


def parse_threat_csv(text: str) -> list[ThreatIndicator]:
    """Parse CSV-based threat feeds.

    Args:
        text: CSV content as string.

    Returns:
        List of ThreatIndicator dataclass instances.
        Malformed records are skipped; returns partial results.
    """
    indicators = []

    try:
        reader = csv.DictReader(StringIO(text), delimiter=",")
        for row in reader:
            try:
                # Check for domain column
                domain = None
                for col in ["domain", "Domain", "hostname", "Hostname"]:
                    if col in row and row[col]:
                        domain = row[col].strip().lower()
                        if _is_valid_domain(domain):
                            break
                        domain = None

                if domain:
                    try:
                        confidence = int(row.get("confidence", row.get("Confidence", 50)))
                    except (ValueError, TypeError):
                        confidence = 50

                    category = row.get("category", row.get("Category", "unknown"))

                    metadata: Dict[str, Any] = {
                        "source_format": "csv",
                        "csv_row": dict(row),
                        "category": category,
                    }

                    indicator = ThreatIndicator(
                        indicator_type="domain",
                        value=domain,
                        threat_types=[ThreatType.BLACKLISTED_DOMAIN],
                        source=FeedSource.BLACKWEB,
                        confidence=confidence,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        ttl=86400,
                        metadata=metadata,
                    )
                    indicators.append(indicator)
                    continue

                # Check for IP column
                ip = None
                for col in ["ip", "IP", "address", "Address"]:
                    if col in row and row[col]:
                        ip = row[col].strip()
                        if _is_valid_ip(ip):
                            break
                        ip = None

                if ip:
                    try:
                        confidence = int(row.get("confidence", row.get("Confidence", 50)))
                    except (ValueError, TypeError):
                        confidence = 50

                    category = row.get("category", row.get("Category", "unknown"))

                    metadata: Dict[str, Any] = {
                        "source_format": "csv",
                        "csv_row": dict(row),
                        "category": category,
                    }

                    indicator = ThreatIndicator(
                        indicator_type="ip",
                        value=ip,
                        threat_types=[ThreatType.BLACKLISTED_IP],
                        source=FeedSource.BLACKWEB,
                        confidence=confidence,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        ttl=86400,
                        metadata=metadata,
                    )
                    indicators.append(indicator)

            except (ValueError, TypeError, KeyError):
                # Skip malformed rows
                continue

    except Exception as e:
        logger.warning(f"Error parsing CSV feed: {e}")

    return indicators


def parse_stix_bundle(payload: Dict | str) -> list[ThreatIndicator]:
    """Parse STIX 2.x bundle format using the stix2 library.

    Args:
        payload: STIX bundle as dict or JSON string.

    Returns:
        List of ThreatIndicator dataclass instances.
        Malformed records are skipped; returns partial results.
    """
    indicators = []

    try:
        # Parse string if needed
        if isinstance(payload, str):
            data = json.loads(payload)
        else:
            data = payload

        # Extract objects directly from dict (don't validate with stix2)
        if isinstance(data, dict) and "objects" in data:
            objects = data["objects"]
        elif isinstance(data, list):
            objects = data
        else:
            return indicators

        # Extract indicators from objects
        for obj in objects:
            try:
                # Handle as dict
                if isinstance(obj, dict):
                    obj_dict = obj
                else:
                    # Try to convert stix2 object to dict
                    obj_dict = obj.to_dict() if hasattr(obj, "to_dict") else obj

                obj_type = obj_dict.get("type", "")

                if obj_type != "indicator":
                    continue

                pattern = obj_dict.get("pattern", "")
                if not pattern:
                    continue

                labels = obj_dict.get("labels", [])
                confidence_str = obj_dict.get("confidence", "medium")
                if isinstance(confidence_str, str):
                    confidence_str = confidence_str.lower()
                else:
                    confidence_str = "medium"

                # Map confidence string to int
                confidence_mapping = {"high": 90, "medium": 70, "low": 30}
                confidence = confidence_mapping.get(confidence_str, 50)

                # Extract indicators from STIX pattern using regex
                extracted = _extract_from_stix_pattern(pattern)
                for indicator_value, indicator_type in extracted:
                    try:
                        if _is_valid_indicator(indicator_value, indicator_type):
                            metadata: Dict[str, Any] = {
                                "source_format": "stix",
                                "stix_id": obj_dict.get("id", ""),
                                "stix_pattern": pattern,
                                "stix_valid_from": obj_dict.get("valid_from", ""),
                                "stix_valid_until": obj_dict.get("valid_until", ""),
                                "stix_labels": labels,
                            }

                            threat_types = [ThreatType.BLACKLISTED_DOMAIN]
                            if indicator_type == "ip":
                                threat_types = [ThreatType.BLACKLISTED_IP]

                            indicator = ThreatIndicator(
                                indicator_type=indicator_type,
                                value=indicator_value.lower() if indicator_type == "domain" else indicator_value,
                                threat_types=threat_types,
                                source=FeedSource.BLACKWEB,
                                confidence=confidence,
                                first_seen=datetime.utcnow(),
                                last_seen=datetime.utcnow(),
                                ttl=86400,
                                metadata=metadata,
                            )
                            indicators.append(indicator)
                    except (ValueError, TypeError):
                        continue

            except Exception as e:
                logger.debug(f"Failed to parse STIX indicator object: {e}")
                continue

    except json.JSONDecodeError as e:
        logger.warning(f"Error parsing STIX payload: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error parsing STIX feed: {e}")

    return indicators


# Helper functions


def _misp_type_to_indicator_type(misp_type: str) -> str | None:
    """Convert MISP attribute type to indicator type."""
    mapping = {
        "domain": "domain",
        "hostname": "domain",
        "ip-src": "ip",
        "ip-dst": "ip",
        "url": "url",
        "email": "email",
    }
    return mapping.get(misp_type)


def _parse_misp_date(date_str: str | None) -> datetime | None:
    """Parse MISP date format (ISO8601)."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def _extract_from_stix_pattern(pattern: str) -> list[tuple[str, str]]:
    """Extract indicators from STIX pattern using regex.

    Returns list of (value, type) tuples where type is 'domain' or 'ip'.
    """
    indicators = []

    try:
        # Extract domain-name patterns: [domain-name:value = 'example.com']
        domain_pattern = r"\[domain-name:value\s*=\s*'([^']+)'\]"
        for match in re.finditer(domain_pattern, pattern):
            value = match.group(1)
            if _is_valid_domain(value):
                indicators.append((value, "domain"))

        # Extract ipv4-addr patterns: [ipv4-addr:value = '1.1.1.1']
        ipv4_pattern = r"\[ipv4-addr:value\s*=\s*'([^']+)'\]"
        for match in re.finditer(ipv4_pattern, pattern):
            value = match.group(1)
            if _is_valid_ip(value):
                indicators.append((value, "ip"))

        # Extract ipv6-addr patterns
        ipv6_pattern = r"\[ipv6-addr:value\s*=\s*'([^']+)'\]"
        for match in re.finditer(ipv6_pattern, pattern):
            value = match.group(1)
            if _is_valid_ip(value):
                indicators.append((value, "ip"))

    except Exception as e:
        logger.debug(f"Error parsing STIX pattern: {e}")

    return indicators


def _extract_ips_from_openioc_value(value: str) -> list[str]:
    """Extract IP addresses from OpenIOC value (handles CIDR, ranges, etc.)."""
    import ipaddress

    ips = []

    try:
        # Handle CIDR notation
        if "/" in value:
            try:
                network = ipaddress.ip_network(value, strict=False)
                # For small networks, extract individual IPs
                if network.num_addresses <= 256:
                    ips.extend([str(ip) for ip in network.hosts()])
                else:
                    # For large networks, just add the network address
                    ips.append(str(network.network_address))
            except ValueError:
                pass

        # Handle IP ranges (e.g., 192.168.1.1-192.168.1.10)
        elif "-" in value and "." in value:
            try:
                start_ip_str, end_ip_str = value.split("-", 1)
                start_addr = ipaddress.IPv4Address(start_ip_str.strip())
                end_addr = ipaddress.IPv4Address(end_ip_str.strip())

                # Only extract ranges with reasonable size
                if int(end_addr) - int(start_addr) <= 256:
                    current = start_addr
                    while current <= end_addr:
                        ips.append(str(current))
                        current += 1
                else:
                    ips.extend([str(start_addr), str(end_addr)])
            except ValueError:
                pass

        # Handle single IP
        else:
            if _is_valid_ip(value):
                ips.append(value)

    except Exception as e:
        logger.debug(f"Failed to extract IPs from OpenIOC value '{value}': {e}")

    return ips


def _is_valid_indicator(value: str, indicator_type: str) -> bool:
    """Validate indicator based on type."""
    if indicator_type == "domain":
        return _is_valid_domain(value)
    elif indicator_type == "ip":
        return _is_valid_ip(value)
    elif indicator_type in ["url", "email"]:
        return len(value) > 3
    return False


def _is_valid_domain(domain: str) -> bool:
    """Validate domain format."""
    if len(domain) > 255 or len(domain) < 4:
        return False

    # Check for valid characters
    if not re.match(r"^[a-zA-Z0-9.-]+$", domain):
        return False

    # Must have at least one dot
    if "." not in domain:
        return False

    # Check each part
    parts = domain.split(".")
    for part in parts:
        if len(part) == 0 or len(part) > 63:
            return False
        if part.startswith("-") or part.endswith("-"):
            return False

    return True


def _is_valid_ip(ip: str) -> bool:
    """Validate IP address (IPv4 or IPv6, non-private/loopback)."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
        # Skip private/local/multicast IPs for threat intelligence
        return not (
            addr.is_private
            or addr.is_loopback
            or addr.is_multicast
            or addr.is_reserved
        )
    except ValueError:
        return False
