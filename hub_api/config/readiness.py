"""Production readiness validation for hub-api configuration."""

from __future__ import annotations


def validate_prod_readiness(config: dict[str, int | str]) -> list[str]:
    """Validate production readiness of hub-api deployment.

    Checks that production deployments meet minimum HA requirements (≥2 hub-routers).
    Non-production environments skip validation.

    Args:
        config: Configuration dictionary with keys "env" and "hub_router_count".

    Returns:
        List of warning strings (empty if all checks pass).
    """
    warnings: list[str] = []

    # Only check production deployments
    if config.get("env") != "production":
        return warnings

    # Check minimum hub-router count for HA
    hub_router_count = config.get("hub_router_count", 1)
    if isinstance(hub_router_count, str):
        hub_router_count = int(hub_router_count)
    if hub_router_count < 2:
        warnings.append(
            f"Hub-API deployment is not production ready: "
            f"hub-router count is {hub_router_count} (minimum 2 required for HA)"
        )

    return warnings
