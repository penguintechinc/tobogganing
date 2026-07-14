"""Encryption for sensitive secrets at rest (MFA, tokens)."""
from __future__ import annotations

import base64
import logging
import os
from base64 import b64decode, b64encode

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SecretEncryptor:
    """Encrypts and decrypts sensitive secrets using Fernet (AES-128-CBC)."""

    def __init__(self, key: bytes | None = None) -> None:
        """Initialize with encryption key from parameter or env or ephemeral key.

        Args:
            key: 32-byte raw encryption key. If None, read from DATA_ENCRYPTION_KEY env
                 or generate ephemeral key.

        Raises:
            ValueError: If key is not 32 bytes or decoding fails.
        """
        if key is not None:
            if len(key) != 32:
                raise ValueError(
                    f"Invalid key length: expected 32 bytes, got {len(key)}"
                )
            self._raw_key = key
        else:
            key_b64 = os.environ.get("DATA_ENCRYPTION_KEY")

            if not key_b64:
                logger.warning(
                    "DATA_ENCRYPTION_KEY not set; generating ephemeral key (dev only)"
                )
                self._raw_key = os.urandom(32)
            else:
                try:
                    self._raw_key = b64decode(key_b64)
                    if len(self._raw_key) != 32:
                        raise ValueError(
                            f"Invalid key length: expected 32 bytes, got {len(self._raw_key)}"
                        )
                except Exception as e:
                    raise ValueError(f"Failed to decode DATA_ENCRYPTION_KEY: {e}")

        # Convert raw 32 bytes to Fernet-compatible base64url-encoded key
        # This FIXES the pre-existing bug where env-set keys could never construct Fernet
        self._cipher = Fernet(base64.urlsafe_b64encode(self._raw_key))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext secret to base64-encoded ciphertext.

        Args:
            plaintext: Secret to encrypt (e.g., TOTP secret, token).

        Returns:
            Base64-encoded ciphertext.

        Raises:
            ValueError: If encryption fails.
        """
        try:
            ciphertext_bytes = self._cipher.encrypt(plaintext.encode("utf-8"))
            return b64encode(ciphertext_bytes).decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to encrypt secret: {e}")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64-encoded ciphertext to plaintext secret.

        Args:
            ciphertext: Base64-encoded ciphertext.

        Returns:
            Decrypted plaintext.

        Raises:
            ValueError: If decryption fails or ciphertext is invalid.
        """
        try:
            ciphertext_bytes = b64decode(ciphertext)
            plaintext_bytes = self._cipher.decrypt(ciphertext_bytes)
            return plaintext_bytes.decode("utf-8")
        except InvalidToken:
            raise ValueError("Invalid or tampered ciphertext")
        except Exception as e:
            raise ValueError(f"Failed to decrypt secret: {e}")


# Global encryptor instance
_encryptor: SecretEncryptor | None = None


def get_encryptor() -> SecretEncryptor:
    """Get or initialize the global secret encryptor.

    Uses the configured data key provider (in-app by default; external KMS in Task 6).

    Returns:
        SecretEncryptor instance.
    """
    global _encryptor
    if _encryptor is None:
        # For now, use in-app provider; Task 6 will replace this with gated selection
        from core.crypto.data_keys import InAppDataKeyProvider

        provider = InAppDataKeyProvider()
        _encryptor = SecretEncryptor(provider.get_data_key())
    return _encryptor


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret.

    Args:
        plaintext: Secret to encrypt.

    Returns:
        Encrypted ciphertext.
    """
    return get_encryptor().encrypt(plaintext)


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a secret.

    Args:
        ciphertext: Encrypted ciphertext.

    Returns:
        Decrypted plaintext.
    """
    return get_encryptor().decrypt(ciphertext)
