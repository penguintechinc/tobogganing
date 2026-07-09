"""PostHog feature flags integration for PenguinTech products."""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# PostHog client instance cache
_posthog_client: Optional[object] = None


def _get_posthog_client() -> Optional[object]:
    """Lazy-load and cache the PostHog client."""
    global _posthog_client

    if _posthog_client is not None:
        return _posthog_client

    try:
        import posthog

        api_key = os.getenv("POSTHOG_KEY", "")
        api_host = os.getenv("POSTHOG_HOST", "https://license.penguintech.io")

        if api_key:
            posthog.api_key = api_key
            posthog.personal_api_key = api_key

            # Configure the host if it's not the default
            if api_host and api_host != "https://posthog.com":
                posthog.api_host = api_host

            _posthog_client = posthog
            return posthog
        else:
            logger.warning("POSTHOG_KEY not configured, feature flags disabled")
            return None
    except ImportError:
        logger.warning("posthog not installed, feature flags disabled")
        return None


# Feature flag cache: {flag_key: {distinct_id: cached_result}}
_flag_cache: dict[str, dict[str, bool]] = {}


def feature_enabled(
    module: str,
    feature: str,
    distinct_id: str = "system",
    licensed: bool = False,
) -> bool:
    """
    Check if a feature flag is enabled via PostHog.

    Falls back to cached value on PostHog error; defaults to OFF for unknown flags.

    Args:
        module: Module name (e.g., "ping")
        feature: Feature name (e.g., "enabled")
        distinct_id: Distinct ID for flag evaluation (default: "system")
        licensed: Whether the feature requires a license entitlement
                 (if True and license is missing, returns False)

    Returns:
        True if the feature flag is enabled, False otherwise.
    """
    flag_key = f"tobogganing.{module}.{feature}"

    # Check cache first
    if flag_key in _flag_cache:
        if distinct_id in _flag_cache[flag_key]:
            return _flag_cache[flag_key][distinct_id]

    # Try to evaluate the flag via PostHog
    try:
        client = _get_posthog_client()
        if client is None:
            # PostHog not configured; default to OFF
            # Cache the result
            if flag_key not in _flag_cache:
                _flag_cache[flag_key] = {}
            _flag_cache[flag_key][distinct_id] = False
            return False

        # Evaluate the feature flag
        is_enabled = client.feature_enabled(flag_key, distinct_id, only_evaluate=True)

        # Cache the result
        if flag_key not in _flag_cache:
            _flag_cache[flag_key] = {}
        _flag_cache[flag_key][distinct_id] = is_enabled

        return is_enabled
    except Exception as e:
        logger.error(f"PostHog flag evaluation failed for {flag_key}: {e}")

        # Graceful degradation: use cached value if available
        if flag_key in _flag_cache and distinct_id in _flag_cache[flag_key]:
            return _flag_cache[flag_key][distinct_id]

        # Default to OFF for unknown flags
        return False
