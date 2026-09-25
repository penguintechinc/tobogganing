"""Additional coverage for hub_api.entitlements.gate: tier resolution and require_feature.

test_entitlements_gate.py covers _is_licensed_for_tier ordering; this file fills
in tier_of(), _resolve_tier_uncached(), _licensed_tier() caching, and the
require_feature() decorator wrapper branches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.entitlements import gate


class TestTierOf:
    """Tests for tier_of()."""

    def test_no_entitlement_defaults_community(self) -> None:
        """tier_of() returns community when the registry has no entitlement."""
        registry = MagicMock()
        registry.entitlement_for.return_value = None

        assert gate.tier_of("some.feature", registry) == gate.TIER_COMMUNITY

    def test_entitlement_tier_lowercased(self) -> None:
        """tier_of() lowercases the entitlement's tier value."""
        registry = MagicMock()
        entitlement = MagicMock()
        entitlement.tier = "ENTERPRISE"
        registry.entitlement_for.return_value = entitlement

        assert gate.tier_of("some.feature", registry) == "enterprise"


class TestResolveTierUncached:
    """Tests for _resolve_tier_uncached()."""

    def test_no_client_raises_runtime_error(self) -> None:
        """Raises RuntimeError when the license client is unavailable."""
        with patch("shared.licensing.python_client.get_client", return_value=None):
            with pytest.raises(RuntimeError, match="License client not initialized"):
                gate._resolve_tier_uncached()

    def test_success_returns_lowercased_tier(self) -> None:
        """Returns the lowercased tier from a successful validate() call."""
        client = MagicMock()
        client.validate.return_value = {"tier": "Professional"}

        with patch("shared.licensing.python_client.get_client", return_value=client):
            result = gate._resolve_tier_uncached()

        assert result == "professional"

    def test_validate_exception_reraises(self) -> None:
        """Propagates exceptions raised by client.validate()."""
        client = MagicMock()
        client.validate.side_effect = RuntimeError("license server down")

        with patch("shared.licensing.python_client.get_client", return_value=client):
            with pytest.raises(RuntimeError, match="license server down"):
                gate._resolve_tier_uncached()


class TestLicensedTier:
    """Tests for _licensed_tier() caching behavior."""

    def test_returns_cached_value_without_resolving(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the cached tier directly, without calling _resolve_tier_uncached."""
        gate._TIER_CACHE.clear()
        gate._TIER_CACHE["tier"] = "enterprise"

        def boom() -> str:
            raise AssertionError("should not be called when cache is populated")

        monkeypatch.setattr(gate, "_resolve_tier_uncached", boom)
        try:
            assert gate._licensed_tier() == "enterprise"
        finally:
            gate._TIER_CACHE.clear()

    def test_resolves_and_caches_on_first_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Resolves via _resolve_tier_uncached and caches the result."""
        gate._TIER_CACHE.clear()
        monkeypatch.setattr(gate, "_resolve_tier_uncached", lambda: "professional")

        try:
            result = gate._licensed_tier()
            assert result == "professional"
            assert gate._TIER_CACHE["tier"] == "professional"
        finally:
            gate._TIER_CACHE.clear()


class TestRequireFeatureDecorator:
    """Tests for the require_feature() decorator wrapper."""

    @pytest.mark.asyncio
    async def test_flag_disabled_returns_402(self) -> None:
        """Wrapped handler returns 402 when the feature flag is off."""

        @gate.require_feature("mod", "feature")
        async def handler() -> tuple[dict, int]:
            return {"ok": True}, 200

        with patch("hub_api.entitlements.gate.feature_enabled", return_value=False):
            result, status = await handler()

        assert status == 402
        assert result["error"] == "Feature not available"

    @pytest.mark.asyncio
    async def test_tier_check_exception_returns_402(self) -> None:
        """Wrapped handler returns 402 when tier checking raises unexpectedly."""

        @gate.require_feature("mod", "feature")
        async def handler() -> tuple[dict, int]:
            return {"ok": True}, 200

        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            with patch(
                "hub_api.entitlements.gate.current_app",
                new=MagicMock(
                    registry=MagicMock(entitlement_for=MagicMock(side_effect=RuntimeError("boom")))
                ),
            ):
                result, status = await handler()

        assert status == 402
        assert result["error"] == "License check failed"

    @pytest.mark.asyncio
    async def test_unlicensed_tier_returns_402(self) -> None:
        """Wrapped handler returns 402 when the tier isn't licensed."""

        @gate.require_feature("mod", "feature")
        async def handler() -> tuple[dict, int]:
            return {"ok": True}, 200

        registry = MagicMock()
        entitlement = MagicMock(tier="enterprise")
        registry.entitlement_for.return_value = entitlement

        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            with patch("hub_api.entitlements.gate.current_app", new=MagicMock(registry=registry)):
                with patch.object(gate, "_licensed_tier", return_value="community"):
                    result, status = await handler()

        assert status == 402
        assert result["error"] == "License required"
        assert result["tier"] == "enterprise"

    @pytest.mark.asyncio
    async def test_licensed_and_enabled_calls_handler(self) -> None:
        """Wrapped handler is called through when flag is on and tier is licensed."""

        @gate.require_feature("mod", "feature")
        async def handler() -> tuple[dict, int]:
            return {"ok": True}, 200

        registry = MagicMock()
        entitlement = MagicMock(tier="community")
        registry.entitlement_for.return_value = entitlement

        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            with patch("hub_api.entitlements.gate.current_app", new=MagicMock(registry=registry)):
                with patch.object(gate, "_licensed_tier", return_value="enterprise"):
                    result, status = await handler()

        assert status == 200
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_wrapper_forwards_args_and_kwargs(self) -> None:
        """Wrapped handler forwards positional and keyword arguments through."""

        @gate.require_feature("mod", "feature")
        async def handler(a: int, b: int = 0) -> tuple[dict, int]:
            return {"sum": a + b}, 200

        registry = MagicMock()
        registry.entitlement_for.return_value = None

        with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
            with patch("hub_api.entitlements.gate.current_app", new=MagicMock(registry=registry)):
                with patch.object(gate, "_licensed_tier", return_value="community"):
                    result, status = await handler(2, b=3)

        assert status == 200
        assert result["sum"] == 5
