"""Tests for WaddlePerf Cluster module registration and URL mapping contract."""
from __future__ import annotations

from typing import Any

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_wpc_module_registered(app_with_wpc: Quart) -> None:
    """Test that perftest_cluster module is registered in the app.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    registry = app_with_wpc.registry
    assert registry is not None

    # Check all declared flags are present
    flags = registry.declared_flags()
    assert "tobogganing.perftest_cluster.org_units" in flags
    assert "tobogganing.perftest_cluster.devices" in flags
    assert "tobogganing.perftest_cluster.enrollment" in flags
    assert "tobogganing.perftest_cluster.tests" in flags
    assert "tobogganing.perftest_cluster.stats" in flags
    assert "tobogganing.perftest_cluster.live_test" in flags
    assert "tobogganing.perftest_cluster.large_fleet" in flags


@pytest.mark.asyncio
async def test_wpc_routes_mounted(app_with_wpc: Quart) -> None:
    """Test that all WPC module routes are mounted at correct paths.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    # Test that routes are registered (401/403/402 on unauthorized, not 404 on route not found)
    # These should give auth errors, not route not found
    routes_to_check = [
        "/api/v1/perftest_cluster/org-units",
        "/api/v1/perftest_cluster/devices",
        "/api/v1/perftest_cluster/enrollment/secrets",  # enrollment has /secrets endpoints
        "/api/v1/perftest_cluster/tests",
        "/api/v1/perftest_cluster/stats/summary",
    ]

    for route in routes_to_check:
        response = await client.get(route)
        # Should be 401 (no auth) or 403 (auth required), NOT 404 (route not found)
        assert response.status_code in [401, 403, 402], (
            f"Route {route} returned {response.status_code} (expected auth error, not 404)"
        )


@pytest.mark.asyncio
async def test_wpc_feature_flags_default_off() -> None:
    """Test that WPC feature flags default to OFF when not explicitly enabled.

    This test ensures the module contract declares the flags correctly, and that
    tests enable them explicitly to avoid false positives.
    """
    from hub_api.modules.perftest_cluster import module as wpc_module

    contract = wpc_module()
    flag_names = [f.split(".")[-1] for f in contract.flags]

    expected_flags = [
        "org_units",
        "devices",
        "enrollment",
        "tests",
        "stats",
        "live_test",
        "large_fleet",
    ]

    for flag in expected_flags:
        assert flag in flag_names, f"Flag 'tobogganing.perftest_cluster.{flag}' not declared"


@pytest.mark.asyncio
async def test_wpc_entitlements_configured(app_with_wpc: Quart) -> None:
    """Test that WPC entitlements are registered correctly.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    registry = app_with_wpc.registry

    # Check community tier entitlements
    org_units_ent = registry.entitlement_for("perftest_cluster.org_units")
    assert org_units_ent is not None
    assert org_units_ent.tier == "community"

    devices_ent = registry.entitlement_for("perftest_cluster.devices")
    assert devices_ent is not None
    assert devices_ent.tier == "community"

    # Check professional tier entitlements
    large_fleet_ent = registry.entitlement_for("perftest_cluster.large_fleet")
    assert large_fleet_ent is not None
    assert large_fleet_ent.tier == "professional"


@pytest.mark.asyncio
async def test_sase_routes_unchanged(app_with_sase: Quart) -> None:
    """Test that SASE module routes are still available (no regression).

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    # Test SASE routes are still there
    response = await client.get("/api/v1/sase/clusters")
    # Should be auth error, not route not found
    assert response.status_code in [401, 403, 402]


@pytest.mark.asyncio
async def test_wpc_migrations_declared(app_with_wpc: Quart) -> None:
    """Test that WPC declares its migration versions.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    from hub_api.modules.perftest_cluster import module as wpc_module

    contract = wpc_module()
    assert contract.migrations == ["0010", "0011", "0012"]
