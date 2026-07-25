"""Data key providers for envelope encryption (at-rest data encryption)."""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class DataKeyProvider(Protocol):
    """Protocol for data encryption key providers (returns raw 32 bytes; sync)."""

    def get_data_key(self) -> bytes:
        """Retrieve the data encryption key (32 raw bytes).

        Returns:
            32-byte data encryption key (DEK).

        Raises:
            ValueError: If the key cannot be retrieved or decrypted.
        """
        ...


class InAppDataKeyProvider:
    """In-application data key provider (env-based or ephemeral)."""

    def __init__(self) -> None:
        """Initialize with key from env or generate ephemeral key."""
        key_b64 = os.environ.get("DATA_ENCRYPTION_KEY")

        if not key_b64:
            logger.warning(
                "DATA_ENCRYPTION_KEY not set; generating ephemeral key (dev only)"
            )
            self._key = os.urandom(32)
        else:
            try:
                self._key = base64.b64decode(key_b64)
                if len(self._key) != 32:
                    raise ValueError(
                        f"Invalid key length: expected 32 bytes, got {len(self._key)}"
                    )
            except Exception as e:
                raise ValueError(f"Failed to decode DATA_ENCRYPTION_KEY: {e}")

    def get_data_key(self) -> bytes:
        """Return the 32-byte data encryption key.

        Returns:
            32-byte data encryption key.
        """
        return self._key


class AwsKmsDataKeyProvider:
    """AWS KMS data key provider (unwraps key blob via KMS Decrypt)."""

    def __init__(self, key_arn: str, wrapped_key_b64: str, client: Any | None = None) -> None:
        """Initialize with KMS key ARN and base64-encoded wrapped key blob.

        Args:
            key_arn: AWS KMS key ARN (used as KeyId in Decrypt call).
            wrapped_key_b64: Base64-encoded ciphertext blob from a previous Encrypt call.
            client: boto3 KMS client (if None, will be imported lazily).

        Raises:
            ValueError: If wrapped_key_b64 is not valid base64.
        """
        self._key_arn = key_arn
        try:
            self._wrapped_blob = base64.b64decode(wrapped_key_b64)
        except Exception as e:
            raise ValueError(f"Failed to decode wrapped key: {e}")

        self._client = client
        self._cached_key: bytes | None = None

    def get_data_key(self) -> bytes:
        """Unwrap and return the 32-byte data key via KMS Decrypt.

        Uses cached result on subsequent calls (Decrypt called exactly once).

        Returns:
            32-byte data encryption key.

        Raises:
            ValueError: If unwrapping fails or result is not 32 bytes.
        """
        if self._cached_key is not None:
            return self._cached_key

        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ValueError(
                    "boto3 required for AWS KMS; install with: pip install boto3"
                )
            self._client = boto3.client("kms")

        try:
            response = self._client.decrypt(KeyId=self._key_arn, CiphertextBlob=self._wrapped_blob)
            plaintext = response["Plaintext"]

            if len(plaintext) != 32:
                raise ValueError(
                    f"Invalid unwrapped key length: expected 32 bytes, got {len(plaintext)}"
                )

            self._cached_key = plaintext
            return self._cached_key
        except Exception as e:
            raise ValueError(f"Failed to unwrap key via AWS KMS: {e}")


class GcpKmsDataKeyProvider:
    """Google Cloud KMS data key provider (unwraps key blob via KMS Decrypt)."""

    def __init__(self, key_name: str, wrapped_key_b64: str, client: Any | None = None) -> None:
        """Initialize with GCP KMS key name and base64-encoded wrapped key blob.

        Args:
            key_name: Full GCP CryptoKeyVersion resource name.
            wrapped_key_b64: Base64-encoded ciphertext blob from a previous Encrypt call.
            client: google.cloud.kms.KeyManagementServiceClient (if None, imported lazily).

        Raises:
            ValueError: If wrapped_key_b64 is not valid base64.
        """
        self._key_name = key_name
        try:
            self._wrapped_blob = base64.b64decode(wrapped_key_b64)
        except Exception as e:
            raise ValueError(f"Failed to decode wrapped key: {e}")

        self._client = client
        self._cached_key: bytes | None = None

    def get_data_key(self) -> bytes:
        """Unwrap and return the 32-byte data key via KMS Decrypt.

        Uses cached result on subsequent calls (Decrypt called exactly once).

        Returns:
            32-byte data encryption key.

        Raises:
            ValueError: If unwrapping fails or result is not 32 bytes.
        """
        if self._cached_key is not None:
            return self._cached_key

        if self._client is None:
            try:
                from google.cloud import kms
            except ImportError:
                raise ValueError(
                    "google-cloud-kms required for GCP KMS; "
                    "install with: pip install google-cloud-kms"
                )
            self._client = kms.KeyManagementServiceClient()

        try:
            response = self._client.decrypt(
                request={"name": self._key_name, "ciphertext": self._wrapped_blob}
            )
            plaintext = response.plaintext

            if len(plaintext) != 32:
                raise ValueError(
                    f"Invalid unwrapped key length: expected 32 bytes, got {len(plaintext)}"
                )

            self._cached_key = plaintext
            return self._cached_key
        except Exception as e:
            raise ValueError(f"Failed to unwrap key via GCP KMS: {e}")
