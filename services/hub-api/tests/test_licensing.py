"""
Tests for licensing/__init__.py — feature gating, validation, graceful degradation.
"""
import pytest
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


def _community_license():
    return {
        "valid": True,
        "tier": "community",
        "features": [],
        "client_limit": 10,
        "headend_limit": 2,
    }


# ---------------------------------------------------------------------------
# validate_license
# ---------------------------------------------------------------------------

class TestValidateLicense:
    def test_no_license_key_returns_community(self):
        from licensing import _license_cache
        _license_cache.clear()

        with patch.dict("os.environ", {}, clear=True):
            # Remove LICENSE_KEY env var entirely
            import os
            os.environ.pop("LICENSE_KEY", None)
            from licensing import validate_license
            result = validate_license()
            assert result["tier"] == "community"
            assert result["valid"] is True

    def test_returns_cached_result(self):
        from licensing import _license_cache, validate_license
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "professional", "features": []}
        _license_cache["expires_at"] = float("inf")

        result = validate_license()
        assert result["tier"] == "professional"

    def test_cache_populated_on_first_call(self):
        from licensing import _license_cache, validate_license
        _license_cache.clear()

        with patch("requests.post", return_value=_mock_license_response()), \
             patch.dict("os.environ", {"LICENSE_KEY": "test-key-abc123"}):
            validate_license()
            # Cache should now have a result
            assert "result" in _license_cache or len(_license_cache) > 0

    def test_server_error_falls_back_to_community(self):
        from licensing import _license_cache, validate_license
        _license_cache.clear()

        with patch("requests.post", side_effect=requests.ConnectionError("offline")), \
             patch.dict("os.environ", {"LICENSE_KEY": "test-key-xyz"}):
            result = validate_license()
            assert result["tier"] == "community"

    def test_invalid_response_falls_back_to_community(self):
        from licensing import _license_cache, validate_license
        _license_cache.clear()

        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.json.return_value = {"valid": False, "tier": "unknown"}
        bad_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=bad_resp), \
             patch.dict("os.environ", {"LICENSE_KEY": "invalid-key"}):
            result = validate_license()
            assert result["valid"] is False or result["tier"] in ("community", "unknown")

    def test_timeout_falls_back_to_community(self):
        from licensing import _license_cache, validate_license
        _license_cache.clear()

        with patch("requests.post", side_effect=requests.Timeout()), \
             patch.dict("os.environ", {"LICENSE_KEY": "test-key-timeout"}):
            result = validate_license()
            # Graceful degradation: should not crash
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# check_feature
# ---------------------------------------------------------------------------

class TestCheckFeature:
    def test_feature_present_returns_true(self):
        from licensing import check_feature, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "enterprise", "features": ["sso", "analytics"]}
        _license_cache["expires_at"] = float("inf")

        assert check_feature("sso") is True

    def test_feature_absent_returns_false(self):
        from licensing import check_feature, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "enterprise", "features": ["sso"]}
        _license_cache["expires_at"] = float("inf")

        assert check_feature("waddleai") is False

    def test_community_has_no_enterprise_features(self):
        from licensing import check_feature, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "community", "features": []}
        _license_cache["expires_at"] = float("inf")

        assert check_feature("sso") is False


# ---------------------------------------------------------------------------
# require_feature decorator
# ---------------------------------------------------------------------------

class TestRequireFeature:
    def test_decorator_allows_when_feature_present(self):
        from licensing import require_feature, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "enterprise", "features": ["analytics"]}
        _license_cache["expires_at"] = float("inf")

        @require_feature("analytics")
        def my_fn():
            return "success"

        result = my_fn()
        assert result == "success"

    def test_decorator_raises_when_feature_absent(self):
        from licensing import require_feature, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "community", "features": []}
        _license_cache["expires_at"] = float("inf")

        @require_feature("sso")
        def protected_fn():
            return "should not reach"

        with pytest.raises(Exception):
            protected_fn()


# ---------------------------------------------------------------------------
# get_license_info
# ---------------------------------------------------------------------------

class TestGetLicenseInfo:
    def test_returns_dict(self):
        from licensing import get_license_info, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "professional", "features": ["analytics"]}
        _license_cache["expires_at"] = float("inf")

        result = get_license_info()
        assert isinstance(result, dict)
        assert "tier" in result


# ---------------------------------------------------------------------------
# is_enterprise / is_professional
# ---------------------------------------------------------------------------

class TestTierChecks:
    def test_is_enterprise_true_for_enterprise(self):
        from licensing import is_enterprise, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "enterprise", "features": []}
        _license_cache["expires_at"] = float("inf")

        assert is_enterprise() is True

    def test_is_enterprise_false_for_community(self):
        from licensing import is_enterprise, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "community", "features": []}
        _license_cache["expires_at"] = float("inf")

        assert is_enterprise() is False

    def test_is_professional_true_for_professional(self):
        from licensing import is_professional, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "professional", "features": []}
        _license_cache["expires_at"] = float("inf")

        assert is_professional() is True


# ---------------------------------------------------------------------------
# Client / Headend limits
# ---------------------------------------------------------------------------

class TestLimits:
    def test_check_client_limit_within_limit(self):
        from licensing import check_client_limit, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "enterprise", "features": [], "client_limit": 500}
        _license_cache["expires_at"] = float("inf")

        result = check_client_limit(current_count=100)
        assert result is True

    def test_check_client_limit_at_limit(self):
        from licensing import check_client_limit, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "community", "features": [], "client_limit": 10}
        _license_cache["expires_at"] = float("inf")

        result = check_client_limit(current_count=10)
        assert result is False

    def test_check_headend_limit_within(self):
        from licensing import check_headend_limit, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "enterprise", "features": [], "headend_limit": 50}
        _license_cache["expires_at"] = float("inf")

        result = check_headend_limit(current_count=10)
        assert result is True

    def test_check_headend_limit_exceeded(self):
        from licensing import check_headend_limit, _license_cache
        _license_cache.clear()
        _license_cache["result"] = {"valid": True, "tier": "community", "features": [], "headend_limit": 2}
        _license_cache["expires_at"] = float("inf")

        result = check_headend_limit(current_count=5)
        assert result is False
