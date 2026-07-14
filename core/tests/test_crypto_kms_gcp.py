"""Tests for Google Cloud KMS key provider (Phase 4b)."""

from __future__ import annotations

from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
import jwt as pyjwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils

from core.auth.jwt import encode_access_token
from core.crypto import GcpKmsKeyProvider, generate_rsa_key_pair


class FakePublicKey(NamedTuple):
    """Mock GCP KMS GetPublicKey response."""

    pem: str


class FakeSignResponse(NamedTuple):
    """Mock GCP KMS AsymmetricSign response."""

    signature: bytes


class FakeGcpKmsClient:
    """Stands in for google.cloud.kms.KeyManagementServiceClient; signs with a real local RSA key."""

    def __init__(self) -> None:
        """Initialize fake client with a real RSA key for testing."""
        priv_pem, pub_pem = generate_rsa_key_pair()
        self._key = serialization.load_pem_private_key(priv_pem.encode(), password=None)
        self._pub_pem = pub_pem
        self.get_public_key_calls: list[dict[str, Any]] = []
        self.asymmetric_sign_calls: list[dict[str, Any]] = []

    def get_public_key(self, request: dict[str, Any]) -> FakePublicKey:
        """Return the public key in PEM format."""
        self.get_public_key_calls.append(request)
        return FakePublicKey(pem=self._pub_pem)

    def asymmetric_sign(self, request: dict[str, Any]) -> FakeSignResponse:
        """Sign a digest and return the signature."""
        self.asymmetric_sign_calls.append(request)
        sig = self._key.sign(
            request["digest"]["sha256"],
            padding.PKCS1v15(),
            utils.Prehashed(hashes.SHA256()),
        )
        return FakeSignResponse(signature=sig)


class TestGcpKmsKeyProvider:
    """Test Google Cloud KMS signing provider."""

    def test_public_pem_is_valid_and_kid_rule(self) -> None:
        """Test that public_pem is valid PEM and kid follows sha256 rule."""
        fake_client = FakeGcpKmsClient()
        key_name = "projects/my-project/locations/us/keyRings/my-keyring/cryptoKeys/my-key/versions/1"
        provider = GcpKmsKeyProvider(key_name, client=fake_client)

        # Verify public_pem is valid PEM
        assert provider.public_pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert provider.public_pem.endswith("-----END PUBLIC KEY-----\n")

        # Verify kid is sha256(public_pem)[:16]
        import hashlib
        expected_kid = hashlib.sha256(provider.public_pem.encode()).hexdigest()[:16]
        assert provider.kid == expected_kid
        assert len(provider.kid) == 16
        assert provider.kid.isalnum()

    @pytest.mark.asyncio
    async def test_sign_verifies_against_public_pem(self) -> None:
        """Test that await provider.sign(b'data') verifies against public_pem."""
        fake_client = FakeGcpKmsClient()
        key_name = "projects/my-project/locations/us/keyRings/my-keyring/cryptoKeys/my-key/versions/1"
        provider = GcpKmsKeyProvider(key_name, client=fake_client)

        data = b"header.payload"
        sig = await provider.sign(data)

        # Verify signature against public key
        public_key = serialization.load_pem_public_key(provider.public_pem.encode())
        # Raises InvalidSignature on failure
        public_key.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())

    @pytest.mark.asyncio
    async def test_end_to_end_encode_access_token_with_gcp_provider(self) -> None:
        """Test end-to-end: encode_access_token with GCP provider → pyjwt.decode succeeds."""
        fake_client = FakeGcpKmsClient()
        key_name = "projects/my-project/locations/us/keyRings/my-keyring/cryptoKeys/my-key/versions/1"
        provider = GcpKmsKeyProvider(key_name, client=fake_client)

        token = await encode_access_token(
            {"sub": "u1", "iss": "tobogganing", "aud": "api", "tenant": "t1"}, provider
        )

        # Decode with PyJWT using provider's public key
        claims = pyjwt.decode(token, provider.public_pem, algorithms=["RS256"], options={"verify_aud": False})
        assert claims["sub"] == "u1"

        # Verify kid in header
        header = pyjwt.get_unverified_header(token)
        assert header["kid"] == provider.kid
        assert header["alg"] == "RS256"

    def test_get_public_key_called_once_cached(self) -> None:
        """Test that get_public_key is called exactly once and result is cached."""
        fake_client = FakeGcpKmsClient()
        key_name = "projects/my-project/locations/us/keyRings/my-keyring/cryptoKeys/my-key/versions/1"
        provider = GcpKmsKeyProvider(key_name, client=fake_client)

        # Access public_pem and kid multiple times
        _ = provider.public_pem
        _ = provider.kid
        _ = provider.public_pem
        _ = provider.kid

        # Verify get_public_key was called exactly once
        assert len(fake_client.get_public_key_calls) == 1

        # Verify by checking that multiple accesses return the same object (cached)
        pem1 = provider.public_pem
        pem2 = provider.public_pem
        assert pem1 is pem2  # Same object (cached)
