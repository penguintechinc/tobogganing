"""Tests for production readiness validation."""
from __future__ import annotations

from hub_api.config.readiness import validate_prod_readiness


def test_single_hub_router_warns() -> None:
    """Single hub-router in production should emit warning."""
    warns = validate_prod_readiness({"env": "production", "hub_router_count": 1})
    assert len(warns) == 1
    assert "not production ready" in warns[0]
    assert "hub-router" in warns[0]


def test_two_hub_routers_ok() -> None:
    """Two hub-routers in production should pass without warnings."""
    warns = validate_prod_readiness({"env": "production", "hub_router_count": 2})
    assert warns == []


def test_three_hub_routers_ok() -> None:
    """Three or more hub-routers in production should pass without warnings."""
    warns = validate_prod_readiness({"env": "production", "hub_router_count": 3})
    assert warns == []


def test_non_production_single_router_ok() -> None:
    """Single hub-router in non-production environments should pass."""
    for env in ["dev", "staging", "test"]:
        warns = validate_prod_readiness({"env": env, "hub_router_count": 1})
        assert warns == [], f"Expected no warnings for env={env}"


def test_missing_env_no_warning() -> None:
    """Missing env key should not trigger warning."""
    warns = validate_prod_readiness({"hub_router_count": 1})
    assert warns == []


def test_missing_hub_router_count_defaults_to_one() -> None:
    """Missing hub_router_count should default to 1 and warn in production."""
    warns = validate_prod_readiness({"env": "production"})
    assert len(warns) == 1
    assert "not production ready" in warns[0]
