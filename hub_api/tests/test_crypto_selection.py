"""Tests for KMS provider selection and gating logic."""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from hub_api.crypto.data_keys import (
    InAppDataKeyProvider,
    AwsKmsDataKeyProvider,
    GcpKmsDataKeyProvider,
)
from hub_api.crypto.keys import InAppKeyProvider, AwsKmsKeyProvider, GcpKmsKeyProvider
from hub_api.crypto.selection import build_signing_provider, build_data_key_provider
from hub_api.registry.registry import ModuleRegistry
from hub_api.registry.contract import Entitlement


@pytest.fixture
def registry() -> ModuleRegistry:
    """Create a fresh module registry."""
    return ModuleRegistry()


@pytest.fixture
def fake_aws_client() -> MagicMock:
    """Fake AWS KMS client for testing."""
    client = MagicMock()
    client.get_public_key.return_value = {
        "PublicKey": b"fake_der_key_data"
    }
    client.sign.return_value = {"Signature": b"fake_signature"}
    return client


@pytest.fixture
def fake_gcp_client() -> MagicMock:
    """Fake GCP KMS client for testing."""
    client = MagicMock()
    response = MagicMock()
    response.pem = "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----\n"
    client.get_public_key.return_value = response
    response_sign = MagicMock()
    response_sign.signature = b"fake_signature"
    client.asymmetric_sign.return_value = response_sign
    return client


@pytest.fixture
def fake_data_key_client() -> MagicMock:
    """Fake KMS client for data key operations."""
    client = MagicMock()
    client.decrypt.return_value = {"Plaintext": b"0" * 32}  # 32-byte key
    return client


def test_default_env_returns_inapp_key_provider(registry: ModuleRegistry) -> None:
    """Test (a): Default env (no KMS_PROVIDER) returns InAppKeyProvider."""
    with patch.dict("os.environ", {}, clear=False):
        if "KMS_PROVIDER" in __import__("os").environ:
            del __import__("os").environ["KMS_PROVIDER"]
        provider = build_signing_provider(registry)
        assert isinstance(provider, InAppKeyProvider)


def test_aws_provider_flag_off_returns_inapp(
    registry: ModuleRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    """Test (b): KMS_PROVIDER=aws + flag OFF → in-app with warning logged."""
    with patch.dict("os.environ", {"KMS_PROVIDER": "aws"}):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=False):
            with caplog.at_level(logging.WARNING):
                provider = build_signing_provider(registry)
            assert isinstance(provider, InAppKeyProvider)
            assert "external_kms_not_entitled_falling_back_inapp" in caplog.text


def test_aws_provider_unlicensed_returns_inapp(
    registry: ModuleRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    """Test (c): flag ON + unlicensed → in-app with warning."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    with patch.dict("os.environ", {"KMS_PROVIDER": "aws"}):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch(
                "hub_api.crypto.selection._is_licensed_for_tier", return_value=False
            ):
                with caplog.at_level(logging.WARNING):
                    provider = build_signing_provider(registry)
                assert isinstance(provider, InAppKeyProvider)
                assert "external_kms_not_entitled_falling_back_inapp" in caplog.text


def test_aws_provider_licensed_returns_aws_provider(
    registry: ModuleRegistry, fake_aws_client: MagicMock
) -> None:
    """Test (d): flag ON + licensed + fake client → AwsKmsKeyProvider."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    with patch.dict(
        "os.environ",
        {
            "KMS_PROVIDER": "aws",
            "AWS_KMS_SIGNING_KEY_ARN": "arn:aws:kms:us-east-1:123456789012:key/12345",
        },
    ):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch(
                "hub_api.crypto.selection._is_licensed_for_tier", return_value=True
            ):
                def fake_factory() -> Any:
                    return fake_aws_client

                provider = build_signing_provider(registry, client_factory=fake_factory)
                assert isinstance(provider, AwsKmsKeyProvider)


def test_gcp_provider_licensed_returns_gcp_provider(
    registry: ModuleRegistry, fake_gcp_client: MagicMock
) -> None:
    """Test (e): GCP with flag ON + licensed → GcpKmsKeyProvider."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    with patch.dict(
        "os.environ",
        {
            "KMS_PROVIDER": "gcp",
            "GCP_KMS_SIGNING_KEY": "projects/my-project/locations/us/keyRings/ring/cryptoKeys/key/versions/1",
        },
    ):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch(
                "hub_api.crypto.selection._is_licensed_for_tier", return_value=True
            ):
                def fake_factory() -> Any:
                    return fake_gcp_client

                provider = build_signing_provider(registry, client_factory=fake_factory)
                assert isinstance(provider, GcpKmsKeyProvider)


def test_aws_provider_missing_env_raises_valueerror(
    registry: ModuleRegistry,
) -> None:
    """Test (f): KMS_PROVIDER=aws licensed but missing ARN env → ValueError."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    with patch.dict("os.environ", {"KMS_PROVIDER": "aws"}):
        # Remove the required env var
        with patch.dict("os.environ", {"AWS_KMS_SIGNING_KEY_ARN": ""}, clear=False):
            if "AWS_KMS_SIGNING_KEY_ARN" in __import__("os").environ:
                del __import__("os").environ["AWS_KMS_SIGNING_KEY_ARN"]
            with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
                with patch(
                    "hub_api.crypto.selection._is_licensed_for_tier", return_value=True
                ):
                    with pytest.raises(
                        ValueError,
                        match="AWS_KMS_SIGNING_KEY_ARN.*not configured",
                    ):
                        build_signing_provider(registry)


def test_registry_entitlement_for_core_external_kms(
    registry: ModuleRegistry,
) -> None:
    """Test (g): entitlement_for('hub_api.external_kms').tier == 'enterprise' after registration."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    entitlement = registry.entitlement_for("hub_api.external_kms")
    assert entitlement is not None
    assert entitlement.tier == "enterprise"


def test_registry_entitlement_bare_not_prefixed(
    registry: ModuleRegistry,
) -> None:
    """Test (h): entitlement key is BARE (core.external_kms not tobogganing.core.external_kms)."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    # Should find bare key
    entitlement = registry.entitlement_for("hub_api.external_kms")
    assert entitlement is not None
    # Should NOT find prefixed key
    prefixed_entitlement = registry.entitlement_for("tobogganing.core.external_kms")
    assert prefixed_entitlement is None


def test_data_key_provider_aws_licensed(
    registry: ModuleRegistry, fake_data_key_client: MagicMock
) -> None:
    """Test data key provider selection for AWS."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    with patch.dict(
        "os.environ",
        {
            "KMS_PROVIDER": "aws",
            "AWS_KMS_DATA_KEY_ARN": "arn:aws:kms:us-east-1:123456789012:key/12345",
            "WRAPPED_DATA_KEY": "YWJjZGVmZ2hpams=",  # base64 of some data
        },
    ):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch(
                "hub_api.crypto.selection._is_licensed_for_tier", return_value=True
            ):
                def fake_factory() -> Any:
                    return fake_data_key_client

                provider = build_data_key_provider(
                    registry, client_factory=fake_factory
                )
                assert isinstance(provider, AwsKmsDataKeyProvider)


def test_data_key_provider_inapp_default() -> None:
    """Test data key provider defaults to in-app when no KMS_PROVIDER."""
    registry = ModuleRegistry()
    with patch.dict("os.environ", {}, clear=False):
        if "KMS_PROVIDER" in __import__("os").environ:
            del __import__("os").environ["KMS_PROVIDER"]
        provider = build_data_key_provider(registry)
        assert isinstance(provider, InAppDataKeyProvider)


def test_gcp_data_key_provider_licensed(
    registry: ModuleRegistry, fake_data_key_client: MagicMock
) -> None:
    """Test data key provider selection for GCP."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    with patch.dict(
        "os.environ",
        {
            "KMS_PROVIDER": "gcp",
            "GCP_KMS_DATA_KEY": "projects/my-project/locations/us/keyRings/ring/cryptoKeys/key/versions/1",
            "WRAPPED_DATA_KEY": "YWJjZGVmZ2hpams=",
        },
    ):
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch(
                "hub_api.crypto.selection._is_licensed_for_tier", return_value=True
            ):
                def fake_factory() -> Any:
                    return fake_data_key_client

                provider = build_data_key_provider(
                    registry, client_factory=fake_factory
                )
                assert isinstance(provider, GcpKmsDataKeyProvider)


def test_gcp_data_key_provider_missing_env_raises(
    registry: ModuleRegistry,
) -> None:
    """Test data key provider raises when required env is missing."""
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    with patch.dict(
        "os.environ", {"KMS_PROVIDER": "gcp", "WRAPPED_DATA_KEY": "YWJjZGVm"}
    ):
        # Missing GCP_KMS_DATA_KEY
        if "GCP_KMS_DATA_KEY" in __import__("os").environ:
            del __import__("os").environ["GCP_KMS_DATA_KEY"]
        with patch("hub_api.crypto.selection.feature_enabled", return_value=True):
            with patch(
                "hub_api.crypto.selection._is_licensed_for_tier", return_value=True
            ):
                with pytest.raises(ValueError, match="GCP_KMS_DATA_KEY.*not configured"):
                    build_data_key_provider(registry)
