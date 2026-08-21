"""Additional coverage for hub_api.core.backup.crypto: unavailable-library branches.

test_core_backup.py exercises the full encrypt/decrypt round trip; this file
covers the CRYPTO_AVAILABLE=False fallback paths and the too-short-file error
in decrypt_file, by monkeypatching the module-level availability flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import hub_api.core.backup.crypto as crypto_module
from hub_api.core.backup.crypto import decrypt_file, encrypt_file


def test_derive_key_raises_when_crypto_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """_derive_key() raises ImportError when CRYPTO_AVAILABLE is False."""
    monkeypatch.setattr(crypto_module, "CRYPTO_AVAILABLE", False)
    with pytest.raises(ImportError, match="cryptography library required"):
        crypto_module._derive_key("password")


def test_encrypt_file_skipped_when_crypto_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """encrypt_file() returns the original path unchanged when crypto is unavailable."""
    test_file = tmp_path / "data.txt"
    test_file.write_text("plaintext")

    monkeypatch.setattr(crypto_module, "CRYPTO_AVAILABLE", False)
    result = encrypt_file(test_file, "password")

    assert result == test_file
    assert test_file.exists()  # File untouched, not renamed to .enc


def test_decrypt_file_skipped_when_crypto_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """decrypt_file() returns the original path unchanged when crypto is unavailable."""
    test_file = tmp_path / "data.txt.enc"
    test_file.write_text("ciphertext-ish")

    monkeypatch.setattr(crypto_module, "CRYPTO_AVAILABLE", False)
    result = decrypt_file(test_file, "password")

    assert result == test_file


def test_decrypt_file_too_short_raises_value_error(tmp_path: Path) -> None:
    """decrypt_file() raises ValueError when the file is shorter than the salt length."""
    test_file = tmp_path / "tiny.enc"
    test_file.write_bytes(b"short")  # < 16 bytes

    with pytest.raises(ValueError, match="too short"):
        decrypt_file(test_file, "password")
