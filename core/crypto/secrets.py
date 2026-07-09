"""Encryption for sensitive secrets at rest (MFA, tokens)."""
from __future__ import annotations

import logging
import os
from base64 import b64decode, b64encode

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SecretEncryptor:
    """Encrypts and decrypts sensitive secrets using Fernet (AES-128-CBC)."""

    def __init__(self) -> None:
        """Initialize with encryption key from env or ephemeral key."""
        key_b64 = os.environ.get("DATA_ENCRYPTION_KEY")

        if not key_b64:
            logger.warning(
                "DATA_ENCRYPTION_KEY not set; generating ephemeral key (dev only)"
            )
            self._key = Fernet.generate_key()
        else:
            try:
                self._key = b64decode(key_b64)
                if len(self._key) != 32:
                    raise ValueError(
                        f"Invalid key length: expected 32 bytes, got {len(self._key)}"
                    )
            except Exception as e:
                raise ValueError(f"Failed to decode DATA_ENCRYPTION_KEY: {e}")

        self._cipher = Fernet(self._key)

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

    Returns:
        SecretEncryptor instance.
    """
    global _encryptor
    if _encryptor is None:
        _encryptor = SecretEncryptor()
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
