"""Tests for cryptographic key providers."""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from core.crypto import (
    AwsKmsKeyProvider,
    GcpKmsKeyProvider,
    InAppKeyProvider,
    build_key_provider,
    generate_rsa_key_pair,
)


class TestKeyGeneration:
    """Test RSA key pair generation."""

    def test_generate_rsa_key_pair(self) -> None:
        """Test that RSA key pair generation produces valid PEM keys."""
        private_pem, public_pem = generate_rsa_key_pair()

        assert private_pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert private_pem.endswith("-----END PRIVATE KEY-----\n")

        assert public_pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert public_pem.endswith("-----END PUBLIC KEY-----\n")

    def test_generated_keys_are_distinct(self) -> None:
        """Test that different calls generate different keys."""
        private_pem1, public_pem1 = generate_rsa_key_pair()
        private_pem2, public_pem2 = generate_rsa_key_pair()

        assert private_pem1 != private_pem2
        assert public_pem1 != public_pem2


class TestInAppKeyProvider:
    """Test the in-app key provider."""

    def test_init_and_properties(self) -> None:
        """Test KeyProvider initialization and property access."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        assert provider.public_pem == public_pem

    def test_kid_is_stable_and_non_empty(self) -> None:
        """Test that kid is stable and derived from public key."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        kid1 = provider.kid
        kid2 = provider.kid

        assert kid1 == kid2
        assert len(kid1) == 16
        assert kid1.isalnum()

    def test_kid_differs_between_providers(self) -> None:
        """Test that different keys produce different kids."""
        private_pem1, public_pem1 = generate_rsa_key_pair()
        private_pem2, public_pem2 = generate_rsa_key_pair()

        provider1 = InAppKeyProvider(private_pem1, public_pem1)
        provider2 = InAppKeyProvider(private_pem2, public_pem2)

        assert provider1.kid != provider2.kid

    @pytest.mark.asyncio
    async def test_inapp_sign_verifies_against_public_key(self) -> None:
        """InAppKeyProvider.sign produces a PKCS1v15/SHA256 signature verifiable with its public key."""
        priv, pub = generate_rsa_key_pair()
        provider = InAppKeyProvider(priv, pub)
        data = b"header.payload"
        sig = await provider.sign(data)
        public_key = serialization.load_pem_public_key(pub.encode())
        # Raises InvalidSignature on failure
        public_key.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())

    def test_protocol_has_no_private_pem(self) -> None:
        """The KeyProvider protocol no longer exposes private key material."""
        from core.crypto.keys import KeyProvider
        # Structural check: annotations/members on the Protocol class
        assert not hasattr(KeyProvider, "private_pem")


class TestBuildKeyProvider:
    """Test the build_key_provider factory function."""

    def test_build_from_env_jwt_private_key_pem(self, monkeypatch: Any) -> None:
        """Test loading key provider from JWT_PRIVATE_KEY_PEM env var."""
        private_pem, public_pem = generate_rsa_key_pair()
        monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", private_pem)
        monkeypatch.delenv("JWT_PRIVATE_KEY_PATH", raising=False)

        provider = build_key_provider()

        assert provider.public_pem == public_pem

    def test_build_from_env_jwt_private_key_path(self, monkeypatch: Any) -> None:
        """Test loading key provider from JWT_PRIVATE_KEY_PATH env var."""
        private_pem, public_pem = generate_rsa_key_pair()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(private_pem)
            temp_path = f.name

        try:
            monkeypatch.delenv("JWT_PRIVATE_KEY_PEM", raising=False)
            monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", temp_path)

            provider = build_key_provider()

            assert provider.public_pem == public_pem
        finally:
            os.unlink(temp_path)

    def test_build_from_env_preferred_order(self, monkeypatch: Any) -> None:
        """Test that JWT_PRIVATE_KEY_PEM takes precedence over JWT_PRIVATE_KEY_PATH."""
        private_pem1, public_pem1 = generate_rsa_key_pair()
        private_pem2, public_pem2 = generate_rsa_key_pair()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(private_pem2)
            temp_path = f.name

        try:
            monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", private_pem1)
            monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", temp_path)

            provider = build_key_provider()

            # Should use JWT_PRIVATE_KEY_PEM (env var takes precedence)
            assert provider.public_pem == public_pem1
        finally:
            os.unlink(temp_path)

    def test_build_dev_fallback(self, monkeypatch: Any) -> None:
        """Test that development fallback generates a key pair when env vars unset."""
        monkeypatch.delenv("JWT_PRIVATE_KEY_PEM", raising=False)
        monkeypatch.delenv("JWT_PRIVATE_KEY_PATH", raising=False)

        provider = build_key_provider()

        assert provider.public_pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert len(provider.kid) == 16


