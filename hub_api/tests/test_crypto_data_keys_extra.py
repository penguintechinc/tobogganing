"""Additional coverage for hub_api.crypto.data_keys error and lazy-import branches.

test_crypto_data_keys.py already covers the happy paths with injected fake
clients; this file fills in decode failures, invalid-length checks, lazy
SDK-client construction, and wrapped exception branches.
"""

from __future__ import annotations

import base64
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from hub_api.crypto.data_keys import (
    AwsKmsDataKeyProvider,
    GcpKmsDataKeyProvider,
    InAppDataKeyProvider,
)


class TestInAppDataKeyProviderErrors:
    """Error branches for InAppDataKeyProvider."""

    def test_invalid_base64_raises_value_error(self) -> None:
        """Non-base64 DATA_ENCRYPTION_KEY raises ValueError."""
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": "not-valid-base64!!!"}, clear=True):
            with pytest.raises(ValueError, match="Failed to decode"):
                InAppDataKeyProvider()

    def test_wrong_length_key_raises_value_error(self) -> None:
        """Base64-valid but wrong-length key raises ValueError."""
        short_key_b64 = base64.b64encode(b"short").decode("ascii")
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": short_key_b64}, clear=True):
            with pytest.raises(ValueError, match="Invalid key length"):
                InAppDataKeyProvider()


class TestAwsKmsDataKeyProviderErrors:
    """Error and lazy-import branches for AwsKmsDataKeyProvider."""

    def test_invalid_wrapped_key_b64_raises(self) -> None:
        """Invalid base64 wrapped_key_b64 raises ValueError at init."""
        with pytest.raises(ValueError, match="Failed to decode wrapped key"):
            AwsKmsDataKeyProvider(key_arn="arn:test", wrapped_key_b64="!!!not-base64!!!")

    def test_lazy_client_construction(self) -> None:
        """When no client is injected, boto3.client('kms') is lazily constructed."""
        wrapped_b64 = base64.b64encode(b"wrapped").decode("ascii")
        provider = AwsKmsDataKeyProvider(key_arn="arn:test", wrapped_key_b64=wrapped_b64)

        fake_client = MagicMock()
        fake_client.decrypt.return_value = {"Plaintext": os.urandom(32)}

        with patch("boto3.client", return_value=fake_client) as mock_boto_client:
            key = provider.get_data_key()

        mock_boto_client.assert_called_once_with("kms")
        assert len(key) == 32

    def test_invalid_unwrapped_length_raises(self) -> None:
        """AWS KMS returning a non-32-byte plaintext raises ValueError."""
        wrapped_b64 = base64.b64encode(b"wrapped").decode("ascii")
        fake_client = MagicMock()
        fake_client.decrypt.return_value = {"Plaintext": b"too-short"}

        provider = AwsKmsDataKeyProvider(
            key_arn="arn:test", wrapped_key_b64=wrapped_b64, client=fake_client
        )
        with pytest.raises(ValueError, match="Invalid unwrapped key length"):
            provider.get_data_key()

    def test_decrypt_exception_wrapped_as_value_error(self) -> None:
        """AWS KMS decrypt() raising is wrapped in ValueError."""
        wrapped_b64 = base64.b64encode(b"wrapped").decode("ascii")
        fake_client = MagicMock()
        fake_client.decrypt.side_effect = RuntimeError("kms down")

        provider = AwsKmsDataKeyProvider(
            key_arn="arn:test", wrapped_key_b64=wrapped_b64, client=fake_client
        )
        with pytest.raises(ValueError, match="Failed to unwrap key via AWS KMS"):
            provider.get_data_key()


class TestGcpKmsDataKeyProviderErrors:
    """Error and lazy-import branches for GcpKmsDataKeyProvider."""

    def test_invalid_wrapped_key_b64_raises(self) -> None:
        """Invalid base64 wrapped_key_b64 raises ValueError at init."""
        with pytest.raises(ValueError, match="Failed to decode wrapped key"):
            GcpKmsDataKeyProvider(key_name="projects/p/x", wrapped_key_b64="!!!bad!!!")

    def test_lazy_client_construction(self) -> None:
        """When no client is injected, google.cloud.kms client is lazily constructed.

        Uses a sys.modules fake to avoid the pre-existing protobuf/proto-plus
        version mismatch in this environment that breaks a real
        `from google.cloud import kms` (see test_wrap_data_key_extra.py).
        """
        wrapped_b64 = base64.b64encode(b"wrapped").decode("ascii")
        provider = GcpKmsDataKeyProvider(key_name="projects/p/x", wrapped_key_b64=wrapped_b64)

        fake_response = MagicMock()
        fake_response.plaintext = os.urandom(32)
        fake_client = MagicMock()
        fake_client.decrypt.return_value = fake_response
        fake_kms_module = MagicMock()
        fake_kms_module.KeyManagementServiceClient.return_value = fake_client

        with patch.dict(sys.modules, {"google.cloud.kms": fake_kms_module}):
            key = provider.get_data_key()

        fake_kms_module.KeyManagementServiceClient.assert_called_once()
        assert len(key) == 32

    def test_invalid_unwrapped_length_raises(self) -> None:
        """GCP KMS returning a non-32-byte plaintext raises ValueError."""
        wrapped_b64 = base64.b64encode(b"wrapped").decode("ascii")
        fake_response = MagicMock()
        fake_response.plaintext = b"too-short"
        fake_client = MagicMock()
        fake_client.decrypt.return_value = fake_response

        provider = GcpKmsDataKeyProvider(
            key_name="projects/p/x", wrapped_key_b64=wrapped_b64, client=fake_client
        )
        with pytest.raises(ValueError, match="Invalid unwrapped key length"):
            provider.get_data_key()

    def test_decrypt_exception_wrapped_as_value_error(self) -> None:
        """GCP KMS decrypt() raising is wrapped in ValueError."""
        wrapped_b64 = base64.b64encode(b"wrapped").decode("ascii")
        fake_client = MagicMock()
        fake_client.decrypt.side_effect = RuntimeError("kms down")

        provider = GcpKmsDataKeyProvider(
            key_name="projects/p/x", wrapped_key_b64=wrapped_b64, client=fake_client
        )
        with pytest.raises(ValueError, match="Failed to unwrap key via GCP KMS"):
            provider.get_data_key()
