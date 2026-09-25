"""Unified feature gate: PostHog flag AND (optional) license entitlement."""
from __future__ import annotations
import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)
_cache: Dict[str, bool] = {}
_posthog = None


def _client():
    global _posthog
    if _posthog is None:
        key = os.getenv("POSTHOG_KEY")
        if not key:
            return None
        import posthog
        posthog.project_api_key = key
        posthog.host = os.getenv("POSTHOG_HOST", "https://license.penguintech.io")
        _posthog = posthog
    return _posthog


def _flag_on(key: str, distinct_id: str) -> bool:
    client = _client()
    if client is None:
        return _cache.get(key, False)  # no flags configured → default OFF
    try:
        result = bool(client.feature_enabled(key, distinct_id))
        _cache[key] = result
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("posthog flag lookup failed for %s: %s", key, exc)
        return _cache.get(key, False)


def _licensed(feature: str) -> bool:
    try:
        from shared.licensing.python_client import check_feature
        return bool(check_feature(feature))
    except Exception as exc:  # noqa: BLE001
        logger.warning("license check failed for %s: %s", feature, exc)
        return False


def feature_enabled(module: str, feature: str, distinct_id: str = "system",
                    licensed: bool = False) -> bool:
    key = f"tobogganing.{module}.{feature}"
    if not _flag_on(key, distinct_id):
        return False
    if licensed and not _licensed(feature):
        return False
    return True
