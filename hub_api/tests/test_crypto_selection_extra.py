"""Additional coverage for hub_api.crypto.selection: remaining error/fallback branches."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hub_api.crypto.data_keys import InAppDataKeyProvider
from hub_api.crypto.selection import build_data_key_provider, build_signing_provider
from hub_api.registry.contract import Entitlement
from hub_api.registry.registry import ModuleRegistry


@pytest.fixture
def registry() -> ModuleRegistry:
    """Fresh module registry."""
    return ModuleRegistry()


def test_signing_provider_unknown_kms_provider_raises(registry: ModuleRegistry) -> None:
    """build_signing_provider() raises ValueError for an unrecognized KMS_PROVIDER."""
    registry.register_entitlements([Entitlement(feature="hub_api.external_kms", tier="enterprise")])
    with patch.dict("os.environ", {"KMS_PROVIDER": "azure"}):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch("hub_api.crypto.selection._is_licensed_for_tier", return_value=True):
                with pytest.raises(ValueError, match="Unknown KMS_PROVIDER: azure"):
                    build_signing_provider(registry)


def test_signing_provider_gcp_missing_env_raises(registry: ModuleRegistry) -> None:
    """build_signing_provider() raises ValueError when GCP_KMS_SIGNING_KEY is missing."""
    registry.register_entitlements([Entitlement(feature="hub_api.external_kms", tier="enterprise")])
    with patch.dict("os.environ", {"KMS_PROVIDER": "gcp"}, clear=True):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch("hub_api.crypto.selection._is_licensed_for_tier", return_value=True):
                with pytest.raises(ValueError, match="GCP_KMS_SIGNING_KEY.*not configured"):
                    build_signing_provider(registry)


def test_data_key_provider_flag_off_falls_back_to_inapp(
    registry: ModuleRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    """build_data_key_provider() falls back to in-app when the feature flag is off."""
    import logging

    with patch.dict("os.environ", {"KMS_PROVIDER": "aws"}):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=False):
            with caplog.at_level(logging.WARNING):
                provider = build_data_key_provider(registry)
    assert isinstance(provider, InAppDataKeyProvider)
    assert "external_kms_not_entitled_falling_back_inapp" in caplog.text


def test_data_key_provider_missing_wrapped_key_raises(registry: ModuleRegistry) -> None:
    """build_data_key_provider() raises ValueError when WRAPPED_DATA_KEY is missing."""
    registry.register_entitlements([Entitlement(feature="hub_api.external_kms", tier="enterprise")])
    with patch.dict(
        "os.environ",
        {"KMS_PROVIDER": "aws", "AWS_KMS_DATA_KEY_ARN": "arn:aws:kms:us-east-1:1:key/x"},
        clear=True,
    ):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch("hub_api.crypto.selection._is_licensed_for_tier", return_value=True):
                with pytest.raises(ValueError, match="WRAPPED_DATA_KEY is not configured"):
                    build_data_key_provider(registry)


def test_data_key_provider_aws_missing_key_arn_raises(registry: ModuleRegistry) -> None:
    """build_data_key_provider() raises ValueError when AWS_KMS_DATA_KEY_ARN is missing."""
    registry.register_entitlements([Entitlement(feature="hub_api.external_kms", tier="enterprise")])
    with patch.dict(
        "os.environ",
        {
            "KMS_PROVIDER": "aws",
            "WRAPPED_DATA_KEY": "YWJjZGVmZ2hpams=",  # gitleaks:allow (test fixture, not a real key)
        },
        clear=True,
    ):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch("hub_api.crypto.selection._is_licensed_for_tier", return_value=True):
                with pytest.raises(ValueError, match="AWS_KMS_DATA_KEY_ARN.*not configured"):
                    build_data_key_provider(registry)


def test_data_key_provider_unknown_kms_provider_raises(registry: ModuleRegistry) -> None:
    """build_data_key_provider() raises ValueError for an unrecognized KMS_PROVIDER."""
    registry.register_entitlements([Entitlement(feature="hub_api.external_kms", tier="enterprise")])
    with patch.dict(
        "os.environ",
        {
            "KMS_PROVIDER": "azure",
            "WRAPPED_DATA_KEY": "YWJjZGVmZ2hpams=",  # gitleaks:allow (test fixture, not a real key)
        },
        clear=True,
    ):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch("hub_api.crypto.selection._is_licensed_for_tier", return_value=True):
                with pytest.raises(ValueError, match="Unknown KMS_PROVIDER: azure"):
                    build_data_key_provider(registry)
