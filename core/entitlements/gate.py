"""Entitlement tier gating for feature access."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from quart import current_app

from core.flags import feature_enabled

logger = logging.getLogger(__name__)

# Tier constants
TIER_COMMUNITY = "community"
TIER_PROFESSIONAL = "professional"
TIER_ENTERPRISE = "enterprise"

# Tier cache: stores the last-known licensed tier
_TIER_CACHE: dict[str, str] = {}


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

    tier_value: Any = entitlement.tier
    return str(tier_value).lower()


def _resolve_tier_uncached() -> str:
    """
    Resolve the licensed tier from the license server.

    Calls the real license client to determine the tier. If the client
    is unavailable or the call fails, raises an exception (handled by
    the cached wrapper).

    Returns:
        Tier string: "free", "community", "professional", or "enterprise"

    Raises:
        Exception: If license resolution fails
    """
    from shared.licensing.python_client import get_client

    client = get_client()
    if client is None:
        raise RuntimeError("License client not initialized")

    try:
        validation = client.validate()
        tier_value: Any = validation.get("tier", TIER_COMMUNITY)
        tier: str = str(tier_value).lower()
        return tier
    except Exception as e:
        logger.error(f"Failed to resolve licensed tier: {e}")
        raise


def _licensed_tier() -> str:
    """
    Get the licensed tier, with caching and graceful fallback.

    On first call, resolves the tier via _resolve_tier_uncached(). On
    error, falls back to the last-known cached tier. If no cache exists,
    defaults to "community" (most conservative).

    Returns:
        Tier string: "free", "community", "professional", or "enterprise"
    """
    # Return cached tier if available
    if "tier" in _TIER_CACHE:
        return _TIER_CACHE["tier"]

    try:
        tier = _resolve_tier_uncached()
        _TIER_CACHE["tier"] = tier
        return tier
    except Exception as e:
        logger.warning(
            f"Failed to resolve licensed tier, falling back to community: {e}"
        )
        # Default to community (most conservative)
        return TIER_COMMUNITY


def _is_licensed_for_tier(tier: str) -> bool:
    """
    Check if the current license covers a given tier.

    Uses explicit tier ordering: enterprise >= professional > community/free.
    Gracefully degrades on license server errors, defaulting to community tier.

    Args:
        tier: Tier level required

    Returns:
        True if the licensed tier >= required tier
    """
    # Tier ordering: higher numbers = higher tier
    tier_order = {
        "free": 0,
        "community": 0,
        "professional": 1,
        "enterprise": 2,
    }

    licensed = _licensed_tier()
    licensed_level = tier_order.get(licensed.lower(), 0)
    required_level = tier_order.get(tier.lower(), 0)

    return licensed_level >= required_level


def require_feature(
    module: str, feature: str
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
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

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
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
