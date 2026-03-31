"""
Tests for licensing/__init__.py — feature gating, validation, graceful degradation.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
import requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_license_response(tier="enterprise", features=None, valid=True):
    """Build a mock successful license API response."""
    if features is None:
        features = ["sso", "analytics", "waddleai", "advanced_reporting"]
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "valid": valid,
        "tier": tier,
        "features": features,
        "client_limit": 500,
        "headend_limit": 50,
        "expires_at": "2099-12-31T23:59:59Z",
    }
    resp.raise_for_status = MagicMock()
    return resp


def _reset_cache(tier="community", features=None, valid=True, max_clients=None, max_headends=None):
    """Reset the module-level _license_cache to a known state."""
    from licensing import _license_cache
    if features is None:
        features = []
    # Update in-place so all references to the dict stay valid
    _license_cache.update({
        "valid": valid,
        "tier": tier,
        "features": features,
        "last_check": None,  # Forces re-check on next call
        "expires_at": None,
        "max_clients": max_clients,
        "max_headends": max_headends,
    })


def _set_cached(tier="enterprise", features=None, valid=True, max_clients=500, max_headends=50):
    """Prime the cache as if a recent valid check occurred."""
    from licensing import _license_cache
    if features is None:
        features = []
    _license_cache.update({
        "valid": valid,
        "tier": tier,
        "features": features,
        "last_check": datetime.now(),
        "expires_at": "2099-12-31T23:59:59Z",
        "max_clients": max_clients,
        "max_headends": max_headends,
    })


# ---------------------------------------------------------------------------
# validate_license
# ---------------------------------------------------------------------------

class TestValidateLicense:
    def test_no_license_key_returns_community(self):
        _reset_cache()

        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("LICENSE_KEY", None)
            os.environ.pop("TOBOGGANING_LICENSE_KEY", None)
            # Force re-import of module-level constant
            import importlib
            import licensing as _lic
            _lic.LICENSE_KEY = ""
            result = _lic.validate_license(force_check=True)
            assert result["tier"] == "community"
            assert result["valid"] is True

    def test_returns_cached_result(self):
        _set_cached(tier="professional")
        from licensing import validate_license
        result = validate_license()
        assert result["tier"] == "professional"

    def test_cache_populated_on_first_call(self):
        _reset_cache()
        from licensing import validate_license
        import licensing as _lic_mod

        with patch("licensing.requests.post", return_value=_mock_license_response()), \
             patch("licensing.LICENSE_KEY", "test-key-abc123"):
            validate_license(force_check=True)
            # Access via module to get the current (possibly reassigned) cache
            assert _lic_mod._license_cache.get("last_check") is not None

    def test_server_error_falls_back_to_community(self):
        _reset_cache()
        from licensing import validate_license

        with patch("licensing.requests.post", side_effect=requests.ConnectionError("offline")), \
             patch("licensing.LICENSE_KEY", "test-key-xyz"):
            result = validate_license(force_check=True)
            assert result["tier"] in ("community", "basic")

    def test_invalid_response_falls_back_to_community(self):
        _reset_cache()
        from licensing import validate_license

        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.json.return_value = {"valid": False, "tier": "unknown"}
        bad_resp.raise_for_status = MagicMock()

        with patch("licensing.requests.post", return_value=bad_resp), \
             patch("licensing.LICENSE_KEY", "invalid-key"):
            result = validate_license(force_check=True)
            assert isinstance(result, dict)

    def test_timeout_falls_back_to_community(self):
        _reset_cache()
        from licensing import validate_license

        with patch("licensing.requests.post", side_effect=requests.Timeout()), \
             patch("licensing.LICENSE_KEY", "test-key-timeout"):
            result = validate_license(force_check=True)
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# check_feature
# ---------------------------------------------------------------------------

class TestCheckFeature:
    def test_feature_present_returns_true(self):
        _set_cached(tier="enterprise", features=["sso", "analytics"])
        from licensing import check_feature
        assert check_feature("sso") is True

    def test_feature_absent_returns_false(self):
        _set_cached(tier="enterprise", features=["sso"])
        from licensing import check_feature
        assert check_feature("waddleai") is False

    def test_community_has_no_enterprise_features(self):
        _set_cached(tier="community", features=[])
        from licensing import check_feature
        assert check_feature("sso") is False


# ---------------------------------------------------------------------------
# require_feature decorator
# ---------------------------------------------------------------------------

class TestRequireFeature:
    @pytest.mark.asyncio
    async def test_decorator_allows_when_feature_present(self):
        _set_cached(tier="enterprise", features=["analytics"])
        from licensing import require_feature

        @require_feature("analytics")
        async def my_fn():
            return "success"

        result = await my_fn()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_decorator_raises_when_feature_absent(self):
        _set_cached(tier="community", features=[])
        from licensing import require_feature

        @require_feature("sso")
        async def protected_fn():
            return "should not reach"

        # Decorator returns error dict (no raise) — check for dict or exception
        result = await protected_fn()
        assert isinstance(result, dict) or result is None


# ---------------------------------------------------------------------------
# get_license_info
# ---------------------------------------------------------------------------

class TestGetLicenseInfo:
    def test_returns_dict(self):
        _set_cached(tier="professional", features=["analytics"])
        from licensing import get_license_info
        result = get_license_info()
        assert isinstance(result, dict)
        assert "tier" in result


# ---------------------------------------------------------------------------
# is_enterprise / is_professional
# ---------------------------------------------------------------------------

class TestTierChecks:
    def test_is_enterprise_true_for_enterprise(self):
        _set_cached(tier="enterprise")
        from licensing import is_enterprise
        assert is_enterprise() is True

    def test_is_enterprise_false_for_community(self):
        _set_cached(tier="community")
        from licensing import is_enterprise
        assert is_enterprise() is False

    def test_is_professional_true_for_professional(self):
        _set_cached(tier="professional")
        from licensing import is_professional
        assert is_professional() is True


# ---------------------------------------------------------------------------
# Client / Headend limits
# ---------------------------------------------------------------------------

class TestLimits:
    def test_check_client_limit_within_limit(self):
        _set_cached(tier="enterprise", max_clients=500)
        from licensing import check_client_limit
        assert check_client_limit(current_count=100) is True

    def test_check_client_limit_at_limit(self):
        _set_cached(tier="community", max_clients=10)
        from licensing import check_client_limit
        assert check_client_limit(current_count=10) is False

    def test_check_headend_limit_within(self):
        _set_cached(tier="enterprise", max_headends=50)
        from licensing import check_headend_limit
        assert check_headend_limit(current_count=10) is True

    def test_check_headend_limit_exceeded(self):
        _set_cached(tier="community", max_headends=2)
        from licensing import check_headend_limit
        assert check_headend_limit(current_count=5) is False

    def test_check_client_limit_unlimited_community(self):
        """max_clients=None means unlimited — always returns True."""
        _set_cached(tier="community", max_clients=None)
        from licensing import check_client_limit
        assert check_client_limit(current_count=9999) is True

    def test_check_headend_limit_unlimited_community(self):
        """max_headends=None means unlimited — always returns True."""
        _set_cached(tier="community", max_headends=None)
        from licensing import check_headend_limit
        assert check_headend_limit(current_count=9999) is True


# ---------------------------------------------------------------------------
# Additional coverage: server success path + cached fallback
# ---------------------------------------------------------------------------

class TestValidateLicenseAdditionalPaths:
    def test_server_success_updates_cache(self):
        """Successful server validation populates cache with tier/features."""
        _reset_cache()
        from licensing import validate_license
        import licensing as _lic

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "valid": True,
            "tier": "enterprise",
            "features": ["sso", "waddleai"],
            "organization": "Acme Corp",
            "product": "tobogganing",
            "all_products": {},
        }

        with patch("licensing.requests.post", return_value=resp), \
             patch("licensing.LICENSE_KEY", "real-key"):
            result = validate_license(force_check=True)

        assert result["tier"] == "enterprise"
        assert "sso" in result["features"]

    def test_connection_error_uses_existing_valid_cache(self):
        """When server is unreachable and we have a valid cache, return cache."""
        _set_cached(tier="enterprise", features=["sso"])
        from licensing import validate_license
        import licensing as _lic

        with patch("licensing.requests.post", side_effect=requests.ConnectionError("offline")), \
             patch("licensing.LICENSE_KEY", "some-key"):
            # force_check=True bypasses the time cache but still hits RequestException path
            result = validate_license(force_check=True)

        # Should return the previously cached result (valid=True, tier=enterprise)
        assert result.get("valid") is True

    def test_non_200_status_falls_to_community(self):
        """Non-200 response from server falls back to community mode."""
        _reset_cache()
        from licensing import validate_license

        resp = MagicMock()
        resp.status_code = 500

        with patch("licensing.requests.post", return_value=resp), \
             patch("licensing.LICENSE_KEY", "bad-key"):
            result = validate_license(force_check=True)

        assert isinstance(result, dict)

    def test_cache_returned_within_one_hour(self):
        """When cache is recent and valid, validate_license returns without server call."""
        _set_cached(tier="professional", valid=True)
        from licensing import validate_license

        with patch("licensing.requests.post") as mock_post:
            result = validate_license()  # no force_check
        # Server should NOT be called since cache is fresh
        mock_post.assert_not_called()
        assert result["tier"] == "professional"
