"""Regression tests for AutoPerf tier test type validation.

Ensures that all test types selected for each AutoPerf tier are supported by
the EngineClient and match the tiered end-user-experience monitoring design:
Tier 1 is a continuous, cheap path-localization probe set; breaching it
escalates to a heavier throughput diagnostic.
"""
from __future__ import annotations

from hub_api.modules.perftest_cluster.services.engine_client import (
    ALLOWED_TEST_TYPES,
)
from hub_api.modules.perftest_cluster.worker.tasks import _test_types_for_tier


def test_autoperf_tier_test_types_are_engine_supported() -> None:
    """Regression: gh-401 -- all AutoPerf tier test types must be in ALLOWED_TEST_TYPES.

    ``_test_types_for_tier`` selects test types based on the current tier.
    This verifies the set of test types selected for every reachable tier
    (1-3; the escalation state machine caps at 3) is a subset of
    EngineClient.ALLOWED_TEST_TYPES, preventing EngineError failures.
    """
    for tier in (1, 2, 3):
        test_types = _test_types_for_tier(tier)
        unsupported = set(test_types) - ALLOWED_TEST_TYPES
        assert not unsupported, (
            f"Tier {tier} contains unsupported test types: {unsupported}. "
            f"Allowed: {ALLOWED_TEST_TYPES}"
        )


def test_tier1_is_the_continuous_path_localization_probe_set() -> None:
    """Tier 1 (baseline, continuous): http_trace, traceroute, udp, http2.

    These cheaply localize a degradation to wifi vs ISP vs upstream vs
    whole-path (and, via http2, HTTP/2-specific issues like multiplexing/
    HOL or CDN/proxy handling divergent from h1.1) without invoking any
    heavy diagnostic.
    """
    assert _test_types_for_tier(1) == ["http_trace", "traceroute", "udp", "http2"]


def test_tier2_and_tier3_escalate_to_heavy_throughput() -> None:
    """Breach escalation (tier >= 2) adds the heavy `throughput` test on
    top of the tier-1 baseline set; there is currently one heavy
    diagnostic, so tier 2 and tier 3 run the same set."""
    expected = ["http_trace", "traceroute", "udp", "http2", "throughput"]
    assert _test_types_for_tier(2) == expected
    assert _test_types_for_tier(3) == expected
