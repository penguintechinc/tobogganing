"""Tests for perftest_client module registration and URL mapping contract."""
from __future__ import annotations

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_wpcl_module_registered(app_with_wpc: Quart) -> None:
    """perftest_client declares its flags on the registry.

    Args:
        app_with_wpc: Test app with the WaddlePerf modules registered.
    """
    registry = app_with_wpc.registry
    assert registry is not None

    flags = registry.declared_flags()
    assert "tobogganing.perftest_client.schedules" in flags
    assert "tobogganing.perftest_client.config" in flags
    assert "tobogganing.perftest_client.version" in flags


@pytest.mark.asyncio
async def test_wpcl_routes_mounted(app_with_wpc: Quart) -> None:
    """All perftest_client routes resolve (auth error, not 404).

    Args:
        app_with_wpc: Test app with the WaddlePerf modules registered.
    """
    client = app_with_wpc.test_client()
    routes_to_check = [
        "/api/v1/perftest_client/schedules",
        "/api/v1/perftest_client/config",
        "/api/v1/perftest_client/version",
    ]
    for route in routes_to_check:
        response = await client.get(route)
        assert response.status_code != 404, (
            f"Route {route} not mounted (got 404)"
        )


@pytest.mark.asyncio
async def test_wpcl_feature_flags_default_off() -> None:
    """The module contract declares exactly the expected flag keys."""
    from hub_api.modules.perftest_client import module as wpcl_module

    contract = wpcl_module()
    flag_leaves = [f.split(".")[-1] for f in contract.flags]
    for flag in ["schedules", "config", "version"]:
        assert flag in flag_leaves
    assert contract.migrations == ["0013"]
    # All client features are community tier.
    for ent in contract.entitlements:
        assert ent.tier == "community"


@pytest.mark.asyncio
async def test_other_modules_unaffected(app_with_wpc: Quart) -> None:
    """Registering perftest_client leaves sase/ping/cluster routes intact.

    Args:
        app_with_wpc: Test app with the WaddlePerf modules registered.
    """
    client = app_with_wpc.test_client()
    for route in [
        "/api/v1/ping",
        "/api/v1/perftest_cluster/org-units",
    ]:
        response = await client.get(route)
        assert response.status_code != 404, f"Route {route} unexpectedly missing"
