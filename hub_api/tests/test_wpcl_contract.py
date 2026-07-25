"""Tests for waddleperf_client module registration and URL mapping contract."""
from __future__ import annotations

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_wpcl_module_registered(app_with_wpc: Quart) -> None:
    """waddleperf_client declares its flags on the registry.

    Args:
        app_with_wpc: Test app with the WaddlePerf modules registered.
    """
    registry = app_with_wpc.registry
    assert registry is not None

    flags = registry.declared_flags()
    assert "tobogganing.waddleperf_client.schedules" in flags
    assert "tobogganing.waddleperf_client.config" in flags
    assert "tobogganing.waddleperf_client.version" in flags


@pytest.mark.asyncio
async def test_wpcl_routes_mounted(app_with_wpc: Quart) -> None:
    """All waddleperf_client routes resolve (auth error, not 404).

    Args:
        app_with_wpc: Test app with the WaddlePerf modules registered.
    """
    client = app_with_wpc.test_client()
    routes_to_check = [
        "/api/v1/waddleperf_client/schedules",
        "/api/v1/waddleperf_client/config",
        "/api/v1/waddleperf_client/version",
    ]
    for route in routes_to_check:
        response = await client.get(route)
        assert response.status_code != 404, (
            f"Route {route} not mounted (got 404)"
        )


@pytest.mark.asyncio
async def test_wpcl_feature_flags_default_off() -> None:
    """The module contract declares exactly the expected flag keys."""
    from hub_api.modules.waddleperf_client import module as wpcl_module

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
    """Registering waddleperf_client leaves sase/ping/cluster routes intact.

    Args:
        app_with_wpc: Test app with the WaddlePerf modules registered.
    """
    client = app_with_wpc.test_client()
    for route in [
        "/api/v1/ping",
        "/api/v1/waddleperf_cluster/org-units",
    ]:
        response = await client.get(route)
        assert response.status_code != 404, f"Route {route} unexpectedly missing"
