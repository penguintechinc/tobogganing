"""Tests for the PenguinTech license client's request timeout handling.

Regression coverage: `requests.Session.timeout` is not a real attribute —
`requests` silently ignores it, so a hung license server could block
validate()/check_feature()/keepalive() forever, defeating the "never
crash, fall back to cached value" graceful-degradation contract
(critical-rules.md Feature Flags & License Tiers).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from shared.licensing.python_client import (
    LicenseValidationError,
    PenguinTechLicenseClient,
)


@pytest.fixture
def client() -> PenguinTechLicenseClient:
    return PenguinTechLicenseClient(
        license_key="PENG-AAAA-BBBB-CCCC-DDDD-EEEE",
        product="tobogganing",
        base_url="https://license.example.test",
        timeout=7,
    )


def _mock_response(json_data: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = json_data
    return response


class TestSessionHasNoNoOpTimeout:
    def test_session_timeout_attribute_is_not_set(self, client: PenguinTechLicenseClient) -> None:
        """The misleading no-op `session.timeout = timeout` assignment is gone."""
        assert not hasattr(client.session, "timeout") or client.session.timeout is None


class TestValidateTimeout:
    def test_validate_passes_explicit_timeout(self, client: PenguinTechLicenseClient) -> None:
        with patch.object(
            client.session, "post", return_value=_mock_response({"valid": True, "features": []})
        ) as mock_post:
            client.validate()

        assert mock_post.call_args.kwargs["timeout"] == 7

    def test_validate_request_exception_raises_license_error_not_hang(
        self, client: PenguinTechLicenseClient
    ) -> None:
        import requests

        with patch.object(client.session, "post", side_effect=requests.Timeout("boom")):
            with pytest.raises(LicenseValidationError):
                client.validate()


class TestCheckFeatureTimeout:
    def test_check_feature_passes_explicit_timeout(self, client: PenguinTechLicenseClient) -> None:
        with patch.object(
            client.session,
            "post",
            return_value=_mock_response({"features": [{"entitled": True}]}),
        ) as mock_post:
            client.check_feature("sso", use_cache=False)

        assert mock_post.call_args.kwargs["timeout"] == 7


class TestCheckFeatureGracefulDegradation:
    """regression (ops audit O5): an unreachable license server must fall
    back to the last-known cached entitlement, never hard-disable a
    previously-entitled feature (client.md / critical-rules.md Feature
    Flags & License Tiers: "unreachable -> allow continued use with cached
    result -- never crash or disable features on network error")."""

    def test_unreachable_server_falls_back_to_cached_true(
        self, client: PenguinTechLicenseClient
    ) -> None:
        """A feature previously entitled=True stays available on a network error."""
        import requests

        # Prime the cache with a previously-successful entitlement, then
        # force it to be treated as stale so check_feature() re-queries.
        client._feature_cache["sso"] = True
        client._cache_timestamp = time.time() - client._cache_ttl - 1

        with patch.object(client.session, "post", side_effect=requests.ConnectionError("down")):
            result = client.check_feature("sso")

        assert result is True

    def test_unreachable_server_falls_back_to_cached_false(
        self, client: PenguinTechLicenseClient
    ) -> None:
        """A feature previously entitled=False stays disabled (not upgraded to
        True by a failure) on a network error."""
        import requests

        client._feature_cache["sso"] = False
        client._cache_timestamp = time.time() - client._cache_ttl - 1

        with patch.object(client.session, "post", side_effect=requests.ConnectionError("down")):
            result = client.check_feature("sso")

        assert result is False

    def test_unreachable_server_with_no_prior_cache_defaults_closed(
        self, client: PenguinTechLicenseClient
    ) -> None:
        """A feature that has never been validated has nothing to fall back to,
        so it defaults closed (fail closed only for never-seen entitlements)."""
        import requests

        with patch.object(client.session, "post", side_effect=requests.ConnectionError("down")):
            result = client.check_feature("never-checked-before")

        assert result is False


class TestKeepaliveTimeout:
    def test_keepalive_passes_explicit_timeout(self, client: PenguinTechLicenseClient) -> None:
        client.server_id = "srv-1"
        with patch.object(
            client.session, "post", return_value=_mock_response({"ok": True})
        ) as mock_post:
            client.keepalive()

        assert mock_post.call_args.kwargs["timeout"] == 7


class TestTimeoutIsConfigurable:
    def test_custom_timeout_propagates_to_requests(self) -> None:
        custom_client = PenguinTechLicenseClient(
            license_key="PENG-AAAA-BBBB-CCCC-DDDD-EEEE",
            product="tobogganing",
            timeout=2,
        )
        assert custom_client.timeout == 2
        with patch.object(
            custom_client.session,
            "post",
            return_value=_mock_response({"valid": True, "features": []}),
        ) as mock_post:
            custom_client.validate()

        assert mock_post.call_args.kwargs["timeout"] == 2
