"""Additional coverage for hub_api.crypto.secrets error branches and set_encryptor."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from hub_api.crypto import secrets as secrets_module
from hub_api.crypto.secrets import SecretEncryptor, get_encryptor, set_encryptor


def test_explicit_key_wrong_length_raises() -> None:
    """Constructor raises ValueError when an explicit key isn't 32 bytes."""
    with pytest.raises(ValueError, match="Invalid key length"):
        SecretEncryptor(b"too-short")


def test_env_key_invalid_base64_raises() -> None:
    """Constructor raises ValueError when DATA_ENCRYPTION_KEY isn't valid base64."""
    with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": "!!!not-base64!!!"}, clear=True):
        with pytest.raises(ValueError, match="Failed to decode DATA_ENCRYPTION_KEY"):
            SecretEncryptor()


def test_env_key_wrong_length_raises() -> None:
    """Constructor raises ValueError when DATA_ENCRYPTION_KEY decodes to the wrong length."""
    import base64

    short_key_b64 = base64.b64encode(b"short").decode("ascii")
    with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": short_key_b64}, clear=True):
        with pytest.raises(ValueError, match="Invalid key length"):
            SecretEncryptor()


def test_encrypt_wraps_unexpected_exception() -> None:
    """encrypt() wraps unexpected cipher exceptions in ValueError."""
    encryptor = SecretEncryptor(os.urandom(32))
    encryptor._cipher.encrypt = lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Failed to encrypt secret"):
        encryptor.encrypt("plaintext")


def test_decrypt_wraps_unexpected_exception() -> None:
    """decrypt() wraps non-InvalidToken exceptions in ValueError."""
    encryptor = SecretEncryptor(os.urandom(32))
    ciphertext = encryptor.encrypt("plaintext")
    encryptor._cipher.decrypt = lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Failed to decrypt secret"):
        encryptor.decrypt(ciphertext)


def test_set_encryptor_overrides_global() -> None:
    """set_encryptor() replaces the module-level singleton used by get_encryptor()."""
    original = secrets_module._encryptor
    try:
        custom = SecretEncryptor(os.urandom(32))
        set_encryptor(custom)

        assert get_encryptor() is custom
    finally:
        secrets_module._encryptor = original
