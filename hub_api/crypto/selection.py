"""KMS provider selection with feature gating and license checks."""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from hub_api.crypto.data_keys import (
    DataKeyProvider,
    InAppDataKeyProvider,
    AwsKmsDataKeyProvider,
    GcpKmsDataKeyProvider,
)
from hub_api.crypto.keys import (
    KeyProvider,
    InAppKeyProvider,
    AwsKmsKeyProvider,
    GcpKmsKeyProvider,
)
from hub_api.entitlements.gate import tier_of, _is_licensed_for_tier
from hub_api.flags import feature_enabled

logger = logging.getLogger(__name__)


def build_signing_provider(
    registry: Any, client_factory: Optional[Callable[[], Any]] = None
) -> KeyProvider:
    """Build a signing key provider based on environment and licensing.

    Reads KMS_PROVIDER env var (default: "inapp"). For aws/gcp KMS providers,
    requires both the feature flag and license entitlement. On gate failure,
    logs a warning and falls back to in-app. If gate passes but required env
    vars are missing, raises ValueError (misconfiguration fails loud).

    Args:
        registry: ModuleRegistry instance for entitlement lookup.
        client_factory: Optional callable returning an SDK client for testing.
                       If provided, called to get the client to inject.
                       If None, provider handles lazy SDK import.

    Returns:
        KeyProvider instance (InApp, AwsKms, or GcpKms).

    Raises:
        ValueError: If KMS_PROVIDER is selected but required env vars are missing.
    """
    kms_provider = os.getenv("KMS_PROVIDER", "inapp").lower()

    if kms_provider == "inapp":
        return InAppKeyProvider._build_from_env()

    # Check feature gate and license for external KMS
    is_flag_enabled = feature_enabled("core", "external_kms")
    tier = tier_of("hub_api.external_kms", registry)
    is_licensed = _is_licensed_for_tier(tier)

    if not is_flag_enabled or not is_licensed:
        logger.warning(
            "external_kms_not_entitled_falling_back_inapp: "
            "flag_enabled=%s, licensed=%s, tier=%s",
            is_flag_enabled,
            is_licensed,
            tier,
        )
        return InAppKeyProvider._build_from_env()

    # Gate passed; validate required env vars and build provider
    if kms_provider == "aws":
        key_arn = os.getenv("AWS_KMS_SIGNING_KEY_ARN")
        if not key_arn:
            raise ValueError(
                "AWS_KMS_SIGNING_KEY_ARN is not configured for KMS_PROVIDER=aws"
            )
        client = client_factory() if client_factory else None
        return AwsKmsKeyProvider(key_arn, client=client)

    if kms_provider == "gcp":
        key_name = os.getenv("GCP_KMS_SIGNING_KEY")
        if not key_name:
            raise ValueError(
                "GCP_KMS_SIGNING_KEY is not configured for KMS_PROVIDER=gcp"
            )
        client = client_factory() if client_factory else None
        return GcpKmsKeyProvider(key_name, client=client)

    # Unknown KMS_PROVIDER value
    raise ValueError(f"Unknown KMS_PROVIDER: {kms_provider}")


def build_data_key_provider(
    registry: Any, client_factory: Optional[Callable[[], Any]] = None
) -> DataKeyProvider:
    """Build a data key provider based on environment and licensing.

    Reads KMS_PROVIDER env var (default: "inapp"). For aws/gcp KMS providers,
    requires both the feature flag and license entitlement. On gate failure,
    logs a warning and falls back to in-app. If gate passes but required env
    vars are missing, raises ValueError (misconfiguration fails loud).

    Args:
        registry: ModuleRegistry instance for entitlement lookup.
        client_factory: Optional callable returning an SDK client for testing.
                       If provided, called to get the client to inject.
                       If None, provider handles lazy SDK import.

    Returns:
        DataKeyProvider instance (InApp, AwsKms, or GcpKms).

    Raises:
        ValueError: If KMS_PROVIDER is selected but required env vars are missing.
    """
    kms_provider = os.getenv("KMS_PROVIDER", "inapp").lower()

    if kms_provider == "inapp":
        return InAppDataKeyProvider()

    # Check feature gate and license for external KMS
    is_flag_enabled = feature_enabled("core", "external_kms")
    tier = tier_of("hub_api.external_kms", registry)
    is_licensed = _is_licensed_for_tier(tier)

    if not is_flag_enabled or not is_licensed:
        logger.warning(
            "external_kms_not_entitled_falling_back_inapp: "
            "flag_enabled=%s, licensed=%s, tier=%s",
            is_flag_enabled,
            is_licensed,
            tier,
        )
        return InAppDataKeyProvider()

    # Gate passed; validate required env vars and build provider
    wrapped_key_b64 = os.getenv("WRAPPED_DATA_KEY")
    if not wrapped_key_b64:
        raise ValueError("WRAPPED_DATA_KEY is not configured for external KMS")

    if kms_provider == "aws":
        key_arn = os.getenv("AWS_KMS_DATA_KEY_ARN")
        if not key_arn:
            raise ValueError(
                "AWS_KMS_DATA_KEY_ARN is not configured for KMS_PROVIDER=aws"
            )
        client = client_factory() if client_factory else None
        return AwsKmsDataKeyProvider(key_arn, wrapped_key_b64, client=client)

    if kms_provider == "gcp":
        key_name = os.getenv("GCP_KMS_DATA_KEY")
        if not key_name:
            raise ValueError(
                "GCP_KMS_DATA_KEY is not configured for KMS_PROVIDER=gcp"
            )
        client = client_factory() if client_factory else None
        return GcpKmsDataKeyProvider(key_name, wrapped_key_b64, client=client)

    # Unknown KMS_PROVIDER value
    raise ValueError(f"Unknown KMS_PROVIDER: {kms_provider}")
