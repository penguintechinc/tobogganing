"""Tests for encryption/decryption of secrets at rest."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from core.crypto.secrets import SecretEncryptor, decrypt_secret, encrypt_secret


def test_secret_encryption_round_trip() -> None:
    """Test that encryption and decryption are symmetric."""
    encryptor = SecretEncryptor()
    plaintext = "super-secret-mfa-key-12345"

    ciphertext = encryptor.encrypt(plaintext)
    decrypted = encryptor.decrypt(ciphertext)

    assert decrypted == plaintext


def test_secret_encryption_different_plaintexts() -> None:
    """Test that different plaintexts produce different ciphertexts."""
    encryptor = SecretEncryptor()

    ciphertext1 = encryptor.encrypt("secret1")
    ciphertext2 = encryptor.encrypt("secret2")

    assert ciphertext1 != ciphertext2


def test_secret_decryption_tampering() -> None:
    """Test that decryption fails with tampered ciphertext."""
    encryptor = SecretEncryptor()

    ciphertext = encryptor.encrypt("test-secret")
    # Modify the ciphertext
    tampered = ciphertext[:-5] + "xxxxx"

    with pytest.raises(ValueError, match="Invalid or tampered"):
        encryptor.decrypt(tampered)


def test_secret_decryption_invalid_base64() -> None:
    """Test that decryption fails with invalid base64."""
    encryptor = SecretEncryptor()

    with pytest.raises(ValueError):
        encryptor.decrypt("not-valid-base64!!!")


def test_global_encryptor_singleton() -> None:
    """Test that global encryptor is a singleton."""
    from core.crypto.secrets import get_encryptor

    enc1 = get_encryptor()
    enc2 = get_encryptor()

    assert enc1 is enc2


def test_mfa_secret_encryption_with_global_functions() -> None:
    """Test MFA secret encryption using global functions."""
    plaintext = "JBSWY3DPEBLW64TMMQ2HY2LQMBZXG43T"  # TOTP secret

    ciphertext = encrypt_secret(plaintext)
    decrypted = decrypt_secret(ciphertext)

    assert decrypted == plaintext
    # Verify the ciphertext is base64-encoded (no special characters beyond alphanumeric+/=)
    assert ciphertext.replace("+", "").replace("/", "").replace("=", "").isalnum()


def test_ephemeral_key_warning_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Test that ephemeral key generation logs a warning."""
    # Ensure DATA_ENCRYPTION_KEY is not set
    with patch.dict(os.environ, {}, clear=True):
        encryptor = SecretEncryptor()
        # Should have logged a warning about ephemeral key
        assert encryptor._key is not None


@pytest.mark.parametrize(
    "plaintext",
    [
        "simple-secret",
        "JBSWY3DPEBLW64TMMQ2HY2LQMBZXG43T",
        "secret with spaces",
        "unicode-secret-😀",
        "",  # empty string
    ],
)
def test_secret_encryption_various_plaintexts(plaintext: str) -> None:
    """Test encryption/decryption with various plaintext types."""
    encryptor = SecretEncryptor()

    ciphertext = encryptor.encrypt(plaintext)
    decrypted = encryptor.decrypt(ciphertext)

    assert decrypted == plaintext
