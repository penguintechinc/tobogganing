"""Tests for the entitlements tier gating logic."""

from __future__ import annotations

import pytest

from hub_api.entitlements import gate


@pytest.mark.parametrize(
    "licensed,required,ok",
    [
        ("enterprise", "enterprise", True),
        ("enterprise", "professional", True),
        ("professional", "enterprise", False),
        ("professional", "professional", True),
        ("free", "professional", False),
        ("community", "community", True),
        ("community", "professional", False),
        ("community", "free", True),
    ],
)
def test_tier_ordering(
    monkeypatch: any, licensed: str, required: str, ok: bool
) -> None:
    """Test tier ordering: enterprise >= professional > community/free."""
    monkeypatch.setattr(gate, "_licensed_tier", lambda: licensed)
    assert gate._is_licensed_for_tier(required) is ok


def test_graceful_degradation_defaults_community(monkeypatch: any) -> None:
    """Test that errors in license resolution gracefully default to community tier."""

    def boom() -> str:
        raise RuntimeError("license server down")

    monkeypatch.setattr(gate, "_resolve_tier_uncached", boom)
    gate._TIER_CACHE.clear()

    # Professional feature should fail (community < professional)
    assert gate._is_licensed_for_tier("professional") is False

    # Community feature should succeed
    assert gate._is_licensed_for_tier("community") is True
