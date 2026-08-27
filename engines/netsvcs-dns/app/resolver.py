"""Async DNS resolution service using dnspython.

Resolves DNS queries via dnspython's async resolver, returning responses
in Google DoH-JSON format. Supports both upstream recursion and custom-zone serving.
"""
from __future__ import annotations

import logging
from typing import Any

import dns.asyncresolver
import dns.rdatatype
import dns.resolver

logger = logging.getLogger(__name__)


class DNSResolver:
    """Async DNS resolution service."""

    def __init__(self, timeout: float = 5.0, lifetime: float = 5.0) -> None:
        """Initialize resolver with timeouts.

        Args:
            timeout: Timeout per query in seconds.
            lifetime: Total lifetime for a query in seconds.
        """
        self.resolver = dns.asyncresolver.Resolver()
        self.resolver.timeout = timeout
        self.resolver.lifetime = lifetime

    async def resolve(
        self, domain: str, record_type: str = "A"
    ) -> dict[str, Any]:
        """Resolve domain via upstream DNS recursion.

        Returns Google DoH-JSON response format:
        {
            "Status": <0|2|3>,  # 0=NOERROR, 2=SERVFAIL, 3=NXDOMAIN
            "Question": [{"name": domain, "type": record_type}],
            "Answer": [{"name": domain, "type": record_type, "TTL": ttl, "data": value}]
        }

        Args:
            domain: Domain name to resolve.
            record_type: DNS record type (A, AAAA, CNAME, MX, TXT, etc.).

        Returns:
            Dict matching Google DoH-JSON shape.
        """
        try:
            # Parse record type
            try:
                rdtype = dns.rdatatype.from_text(record_type.upper())
            except Exception:
                logger.error(f"Invalid record type: {record_type}")
                return {
                    "Status": 2,  # SERVFAIL
                    "Question": [{"name": domain, "type": record_type}],
                    "Answer": [],
                }

            # Perform async DNS query
            answers = await self.resolver.resolve(domain, rdtype)

            # Build response
            answer_records = []
            for rdata in answers:
                answer_records.append(
                    {
                        "name": domain,
                        "type": record_type,
                        "TTL": answers.rrset.ttl,
                        "data": str(rdata),
                    }
                )

            return {
                "Status": 0,  # NOERROR
                "Question": [{"name": domain, "type": record_type}],
                "Answer": answer_records,
            }

        except dns.resolver.NXDOMAIN:
            logger.info(f"NXDOMAIN: {domain}")
            return {
                "Status": 3,  # NXDOMAIN
                "Question": [{"name": domain, "type": record_type}],
                "Answer": [],
            }

        except dns.resolver.Timeout:
            logger.warning(f"DNS query timeout for {domain}")
            return {
                "Status": 2,  # SERVFAIL
                "Question": [{"name": domain, "type": record_type}],
                "Answer": [],
            }

        except dns.resolver.NoAnswer:
            logger.info(f"No answer for {domain} {record_type}")
            return {
                "Status": 0,  # NOERROR but no answers
                "Question": [{"name": domain, "type": record_type}],
                "Answer": [],
            }

        except Exception as e:
            logger.error(f"DNS resolution error for {domain}: {e}")
            return {
                "Status": 2,  # SERVFAIL
                "Question": [{"name": domain, "type": record_type}],
                "Answer": [],
            }

    def resolve_custom_zone(
        self, domain: str, record_type: str, zone_records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Resolve from custom zone records (Manager-provided zones).

        Returns Google DoH-JSON format. Synchronous method for custom zone serving.

        Args:
            domain: Domain to resolve.
            record_type: Record type.
            zone_records: List of zone records {name, type, ttl, value}.

        Returns:
            Dict matching Google DoH-JSON shape.
        """
        matching_records = []

        for record in zone_records:
            if record.get("name") == domain and record.get("type") == record_type:
                matching_records.append(
                    {
                        "name": domain,
                        "type": record_type,
                        "TTL": record.get("ttl", 300),
                        "data": record.get("value", ""),
                    }
                )

        if matching_records:
            return {
                "Status": 0,  # NOERROR
                "Question": [{"name": domain, "type": record_type}],
                "Answer": matching_records,
            }
        else:
            return {
                "Status": 3,  # NXDOMAIN
                "Question": [{"name": domain, "type": record_type}],
                "Answer": [],
            }
