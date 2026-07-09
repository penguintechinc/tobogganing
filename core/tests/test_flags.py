"""Tests for feature flags and tier entitlements."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from quart import Quart

from core.entitlements.gate import (
    TIER_COMMUNITY,
    TIER_ENTERPRISE,
    TIER_PROFESSIONAL,
    _is_licensed_for_tier,
    require_feature,
    tier_of,
)
from core.flags import feature_enabled
from core.registry.contract import Entitlement


def test_feature_enabled_off() -> None:
    """Test that feature_enabled returns False when flag is off."""
    # Clear cache first
    import shared.licensing.entitlements
    shared.licensing.entitlements._flag_cache.clear()

    with patch("shared.licensing.entitlements._get_posthog_client") as mock_client:
        client_mock = MagicMock()
        client_mock.feature_enabled.return_value = False
        mock_client.return_value = client_mock

        result = feature_enabled("test", "feature1", distinct_id="user1")
        assert result is False


def test_feature_enabled_on() -> None:
    """Test that feature_enabled returns True when flag is on."""
    # Clear cache first
    import shared.licensing.entitlements
    shared.licensing.entitlements._flag_cache.clear()

    with patch("shared.licensing.entitlements._get_posthog_client") as mock_client:
        client_mock = MagicMock()
        client_mock.feature_enabled.return_value = True
        mock_client.return_value = client_mock

        result = feature_enabled("test", "feature1", distinct_id="user1")
        assert result is True


def test_feature_enabled_no_posthog() -> None:
    """Test that feature_enabled defaults to False when PostHog is not configured."""
    # Clear cache first
    import shared.licensing.entitlements
    shared.licensing.entitlements._flag_cache.clear()

    with patch("shared.licensing.entitlements._get_posthog_client") as mock_client:
        mock_client.return_value = None

        result = feature_enabled("test", "feature1")
        assert result is False


def test_feature_enabled_posthog_error() -> None:
    """Test that feature_enabled falls back to cache on PostHog error."""
    # Clear cache first
    import shared.licensing.entitlements
    shared.licensing.entitlements._flag_cache.clear()

    with patch("shared.licensing.entitlements._get_posthog_client") as mock_client:
        # First call succeeds
        client_mock = MagicMock()
        client_mock.feature_enabled.return_value = True
        mock_client.return_value = client_mock
        result1 = feature_enabled("test", "feature2", distinct_id="user1")
        assert result1 is True

        # Second call raises exception
        client_mock.feature_enabled.side_effect = Exception("API error")
        result2 = feature_enabled("test", "feature2", distinct_id="user1")
        # Should return cached value
        assert result2 is True


def test_tier_of_community() -> None:
    """Test tier_of for a community feature."""
    registry = MagicMock()
    registry.entitlement_for.return_value = Entitlement(
        feature="test.feature", tier=TIER_COMMUNITY
    )

    tier = tier_of("test.feature", registry)
    assert tier == TIER_COMMUNITY


def test_tier_of_professional() -> None:
    """Test tier_of for a professional feature."""
    registry = MagicMock()
    registry.entitlement_for.return_value = Entitlement(
        feature="test.pro_feature", tier=TIER_PROFESSIONAL
    )

    tier = tier_of("test.pro_feature", registry)
    assert tier == TIER_PROFESSIONAL


def test_tier_of_enterprise() -> None:
    """Test tier_of for an enterprise feature."""
    registry = MagicMock()
    registry.entitlement_for.return_value = Entitlement(
        feature="test.enterprise_feature", tier=TIER_ENTERPRISE
    )

    tier = tier_of("test.enterprise_feature", registry)
    assert tier == TIER_ENTERPRISE


def test_tier_of_not_found() -> None:
    """Test tier_of returns community when entitlement not found."""
    registry = MagicMock()
    registry.entitlement_for.return_value = None

    tier = tier_of("unknown.feature", registry)
    assert tier == TIER_COMMUNITY


def test_is_licensed_for_tier_community() -> None:
    """Test that community tier is always licensed."""
    assert _is_licensed_for_tier(TIER_COMMUNITY) is True


def test_is_licensed_for_tier_professional() -> None:
    """Test that professional tier is not licensed by default."""
    assert _is_licensed_for_tier(TIER_PROFESSIONAL) is False


def test_is_licensed_for_tier_enterprise() -> None:
    """Test that enterprise tier is not licensed by default."""
    assert _is_licensed_for_tier(TIER_ENTERPRISE) is False


@pytest.mark.asyncio
async def test_require_feature_flag_off(app: Quart) -> None:
    """Test that require_feature returns 402 when flag is off."""
    # Mock the registry
    app.registry.entitlement_for = MagicMock(
        return_value=Entitlement(feature="test.feature", tier=TIER_COMMUNITY)
    )

    with patch("core.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        @require_feature("test", "feature")
        async def handler() -> tuple[dict, int]:
            return {"status": "ok"}, 200

        # Call within app context
        async with app.app_context():
            result = await handler()
            assert result[1] == 402
            assert result[0]["error"] == "Feature not available"


@pytest.mark.asyncio
async def test_require_feature_flag_on(app: Quart) -> None:
    """Test that require_feature allows access when flag is on and community tier."""
    # Mock the registry
    app.registry.entitlement_for = MagicMock(
        return_value=Entitlement(feature="test.feature", tier=TIER_COMMUNITY)
    )

    with patch("core.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        @require_feature("test", "feature")
        async def handler() -> tuple[dict, int]:
            return {"status": "ok"}, 200

        # Call within app context
        async with app.app_context():
            result = await handler()
            assert result[1] == 200
            assert result[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_require_feature_professional_not_licensed(app: Quart) -> None:
    """Test that require_feature returns 402 for professional feature without entitlement."""
    # Mock the registry
    app.registry.entitlement_for = MagicMock(
        return_value=Entitlement(feature="test.pro_feature", tier=TIER_PROFESSIONAL)
    )

    with patch("core.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        with patch("core.entitlements.gate._is_licensed_for_tier") as mock_licensed:
            mock_licensed.return_value = False

            @require_feature("test", "pro_feature")
            async def handler() -> tuple[dict, int]:
                return {"status": "ok"}, 200

            # Call within app context
            async with app.app_context():
                result = await handler()
                assert result[1] == 402
                assert result[0]["error"] == "License required"
                assert result[0]["tier"] == TIER_PROFESSIONAL


@pytest.mark.asyncio
async def test_require_feature_professional_licensed(app: Quart) -> None:
    """Test that require_feature allows professional features with entitlement."""
    # Mock the registry
    app.registry.entitlement_for = MagicMock(
        return_value=Entitlement(feature="test.pro_feature", tier=TIER_PROFESSIONAL)
    )

    with patch("core.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        with patch("core.entitlements.gate._is_licensed_for_tier") as mock_licensed:
            mock_licensed.return_value = True

            @require_feature("test", "pro_feature")
            async def handler() -> tuple[dict, int]:
                return {"status": "ok"}, 200

            # Call within app context
            async with app.app_context():
                result = await handler()
                assert result[1] == 200
                assert result[0]["status"] == "ok"
