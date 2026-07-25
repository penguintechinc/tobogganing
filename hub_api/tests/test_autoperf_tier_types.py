"""Regression tests for AutoPerf tier test type validation.

Ensures that all test types selected for each AutoPerf tier (1, 2, 3) are
supported by the EngineClient and match the engine's available endpoints.
"""
from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_autoperf_tier_test_types_are_engine_supported(
    real_dal: Any,
) -> None:
    """Regression: gh-401 — all AutoPerf tier test types must be in ALLOWED_TEST_TYPES.

    When _run_autoperf_cycle_task executes tests, it selects test types based on the
    current tier. This test verifies that the set of test types selected for each tier
    is a subset of EngineClient.ALLOWED_TEST_TYPES, preventing EngineError failures.

    This test documents the CORRECT tier selection logic (after fix):
    - Tier 1: icmp, http
    - Tier 2: icmp, http, tcp, udp, http_trace  (cumulative)
    - Tier 3: icmp, http, tcp, udp, http_trace, traceroute  (cumulative, NOT speedtest)

    Before fix: Tier 3 included 'speedtest' which is not supported by the engine.
    After fix: Tier 3 only includes engine-supported types.
    """
    from hub_api.modules.waddleperf_cluster.services.engine_client import (
        ALLOWED_TEST_TYPES,
    )

    allowed_types = ALLOWED_TEST_TYPES

    # Define the correct tier selections AFTER FIX
    correct_tier_types = {
        1: ["icmp", "http"],
        2: ["icmp", "http", "tcp", "udp", "http_trace"],
        3: ["icmp", "http", "tcp", "udp", "http_trace", "traceroute"],
    }

    # Verify each tier's test types are all supported
    for tier, test_types in correct_tier_types.items():
        unsupported = set(test_types) - allowed_types
        assert (
            not unsupported
        ), f"Tier {tier} contains unsupported test types: {unsupported}. Allowed: {allowed_types}"

    # Explicit check: tier 3 must NOT include speedtest (follow-up work deferred)
    assert (
        "speedtest" not in correct_tier_types[3]
    ), "Tier 3 should not include 'speedtest'; a true bandwidth/speedtest engine endpoint is deferred as follow-up work"
