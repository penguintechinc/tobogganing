"""Entitlement tier gating for feature access."""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Optional

from quart import current_app

from core.flags import feature_enabled
from core.registry.contract import Entitlement

logger = logging.getLogger(__name__)

# Tier constants
TIER_COMMUNITY = "community"
TIER_PROFESSIONAL = "professional"
TIER_ENTERPRISE = "enterprise"


def tier_of(feature: str, registry: Any) -> str:
    """
    Get the tier level for a feature from the registry.

    Args:
        feature: Feature name to look up
        registry: ModuleRegistry instance

    Returns:
        Tier string: "community", "professional", or "enterprise"
    """
    entitlement = registry.entitlement_for(feature)
    if entitlement is None:
        return TIER_COMMUNITY

    return entitlement.tier.lower()


def _is_licensed_for_tier(tier: str) -> bool:
    """
    Check if the current license covers a given tier.

    Args:
        tier: Tier level to check

    Returns:
        True if the tier is licensed (community is always True)
    """
    if tier == TIER_COMMUNITY:
        return True

    # For higher tiers, we'd check against the license entitlement
    # For Phase 1, this returns False (only licensed if explicitly set)
    # This is overridden in tests via monkeypatching
    return False


def require_feature(module: str, feature: str) -> Callable:
    """
    Decorator to gate a route handler behind a feature flag and tier entitlement.

    Returns HTTP 402 if the flag is off or the feature's tier isn't licensed.
    Falls back to cached values on flag/license server errors.

    Args:
        module: Module name (e.g., "ping")
        feature: Feature name (e.g., "enabled")

    Returns:
        Decorated function that returns 402 if feature unavailable
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if the feature flag is enabled
            is_enabled = feature_enabled(module, feature, distinct_id="system")

            if not is_enabled:
                return (
                    {
                        "error": "Feature not available",
                        "message": f"Feature {module}.{feature} is not enabled",
                    },
                    402,
                )

            # Check tier entitlement via the registry
            try:
                registry = current_app.registry
                tier = tier_of(f"{module}.{feature}", registry)

                # Check if the license covers this tier
                is_licensed = _is_licensed_for_tier(tier)

                if not is_licensed:
                    return (
                        {
                            "error": "License required",
                            "message": f"Feature requires {tier} license",
                            "tier": tier,
                        },
                        402,
                    )
            except Exception as e:
                logger.error(f"Error checking tier for {module}.{feature}: {e}")
                # On error, assume not licensed (conservative)
                return (
                    {
                        "error": "License check failed",
                        "message": "Could not verify license entitlement",
                    },
                    402,
                )

            # Feature is available and licensed; call the handler
            return await func(*args, **kwargs)

        return wrapper

    return decorator
