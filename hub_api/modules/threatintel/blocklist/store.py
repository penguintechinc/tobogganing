"""BlocklistStore for O(1) IOC lookup in Valkey."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

import structlog

from hub_api.cache.client import CacheClient
from .models import Verdict, SEVERITIES


logger = structlog.get_logger()


@dataclass(slots=True)
class BlocklistStore:
    """Store IOC verdicts in Valkey with deduplication and TTL.

    Provides O(1) lookup for Inspection Points via sase:blocklist:* namespace.
    All writes are best-effort; reads fail open on cache error.
    """

    cache: CacheClient

    def _key(self, ioc_type: str, value: str) -> tuple[str, str]:
        """Build cache key parts for an IOC.

        Args:
            ioc_type: Type of IOC (ip, domain, url, hash).
            value: IOC value.

        Returns:
            Tuple of (ioc_type, key_value) for prefixed() call.

        For URLs, key is sha256(value) to bound key length.
        """
        if ioc_type == "url":
            key_value = hashlib.sha256(value.encode()).hexdigest()
        else:
            key_value = value
        return ioc_type, key_value

    async def put(self, verdict: Verdict) -> None:
        """Store a verdict, deduping on higher severity or newer first_seen.

        Deduplication: if an entry exists for the same IOC value,
        keep the one with higher SEVERITIES.index, or if equal,
        keep the one with newer (higher) first_seen.

        TTL: if verdict.expiry is set, compute ttl_seconds = expiry - now.

        Writes fail silently (logged) to never block traffic.

        Args:
            verdict: Verdict to store.
        """
        ioc_type, key_value = self._key(verdict.ioc_type, verdict.value)

        # Check if entry exists
        existing_json = await self.cache.get("threatintel:blocklist", ioc_type, key_value)
        if existing_json:
            try:
                existing_data = json.loads(existing_json)
                existing_verdict = Verdict(**existing_data)
                # Compare severity index
                existing_idx = SEVERITIES.index(existing_verdict.severity)
                new_idx = SEVERITIES.index(verdict.severity)
                if existing_idx > new_idx:
                    # Existing is higher severity, keep it
                    return
                elif existing_idx == new_idx and existing_verdict.first_seen >= verdict.first_seen:
                    # Same severity, existing is newer or equal, keep it
                    return
            except (json.JSONDecodeError, ValueError, IndexError) as e:
                logger.warning("sase_blocklist_dedup_error", error=str(e))

        # Serialize and store
        try:
            data = {
                "ioc_type": verdict.ioc_type,
                "value": verdict.value,
                "severity": verdict.severity,
                "source": verdict.source,
                "stix_id": verdict.stix_id,
                "first_seen": verdict.first_seen,
                "expiry": verdict.expiry,
            }
            json_value = json.dumps(data)
            ttl_seconds = None
            if verdict.expiry:
                ttl_seconds = max(1, verdict.expiry - int(time.time()))
            await self.cache.set(
                "threatintel:blocklist", ioc_type, key_value, value=json_value, ttl_seconds=ttl_seconds
            )
        except Exception as e:
            logger.warning("sase_blocklist_put_error", error=str(e))

    async def check(self, ioc_type: str, value: str) -> Verdict | None:
        """Check if an IOC is in the blocklist.

        Fails OPEN: any cache error returns None (traffic allowed).
        This is an out-of-band mandate: never add latency.

        Args:
            ioc_type: Type of IOC.
            value: IOC value.

        Returns:
            Verdict if found, None otherwise or on cache error.
        """
        ioc_type_key, key_value = self._key(ioc_type, value)
        try:
            json_value = await self.cache.get("threatintel:blocklist", ioc_type_key, key_value, fail_closed=False)
            if not json_value:
                return None
            data = json.loads(json_value)
            return Verdict(**data)
        except Exception as e:
            logger.debug("sase_blocklist_check_error", error=str(e))
            return None  # Fail open

    async def remove(self, ioc_type: str, value: str) -> None:
        """Remove a verdict from the blocklist.

        Args:
            ioc_type: Type of IOC.
            value: IOC value.
        """
        ioc_type_key, key_value = self._key(ioc_type, value)
        try:
            await self.cache.delete("threatintel:blocklist", ioc_type_key, key_value)
        except Exception as e:
            logger.warning("sase_blocklist_remove_error", error=str(e))
