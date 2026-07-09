"""Tests for JWT encoding and decoding."""

from __future__ import annotations

import time
from typing import Any

import pytest
import jwt as pyjwt

from core.auth.jwt import decode_token, encode_access_token
from core.crypto import generate_rsa_key_pair, InAppKeyProvider


class TestJwtEncoding:
    """Test JWT token encoding."""

    def test_encode_access_token_success(self) -> None:
        """Test successful JWT encoding with RS256."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read *:write",
            "teams": ["team1"],
            "roles": ["admin"],
        }

        token = encode_access_token(claims, provider, ttl_hours=1)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_encode_access_token_missing_required_claim(self) -> None:
        """Test that encoding fails if required claims are missing."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        # Missing 'tenant' claim
        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
        }

        with pytest.raises(ValueError, match="Missing required claims"):
            encode_access_token(claims, provider)

    def test_encode_includes_iat_and_exp(self) -> None:
        """Test that encoding includes iat and exp claims."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
        }

        token = encode_access_token(claims, provider, ttl_hours=1)

        # Decode without verification to check claims
        decoded = pyjwt.decode(token, options={"verify_signature": False})

        assert "iat" in decoded
        assert "exp" in decoded
        assert decoded["exp"] - decoded["iat"] == 3600  # 1 hour


class TestJwtDecoding:
    """Test JWT token decoding and validation."""

    def test_decode_token_success(self) -> None:
        """Test successful JWT decoding."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read *:write",
        }

        token = encode_access_token(claims, provider, ttl_hours=1)
        decoded = decode_token(token, provider)

        assert decoded is not None
        assert decoded["sub"] == "user123"
        assert decoded["tenant"] == "tenant1"
        assert decoded["scope"] == "*:read *:write"

    def test_decode_token_missing_tenant_returns_none(self) -> None:
        """Test that decoding fails when tenant claim is missing."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        # Create token manually without tenant claim
        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
        }

        now = int(time.time())
        payload = {
            **claims,
            "iat": now,
            "exp": now + 3600,
        }

        token = pyjwt.encode(
            payload,
            private_pem,
            algorithm="RS256",
            headers={"kid": provider.kid},
        )

        decoded = decode_token(token, provider)

        assert decoded is None

    def test_decode_token_tampered_returns_none(self) -> None:
        """Test that decoding tampered token returns None."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
        }

        token = encode_access_token(claims, provider, ttl_hours=1)

        # Tamper with the token
        tampered = token[:-10] + "corrupted!"

        decoded = decode_token(tampered, provider)

        assert decoded is None

    def test_decode_token_expired_returns_none(self) -> None:
        """Test that decoding expired token returns None."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        # Create an already-expired token
        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
        }

        now = int(time.time())
        payload = {
            **claims,
            "iat": now - 7200,  # 2 hours ago
            "exp": now - 3600,  # 1 hour ago
        }

        token = pyjwt.encode(
            payload,
            private_pem,
            algorithm="RS256",
            headers={"kid": provider.kid},
        )

        decoded = decode_token(token, provider)

        assert decoded is None

    def test_decode_token_invalid_signature_returns_none(self) -> None:
        """Test that decoding token with invalid signature returns None."""
        private_pem1, public_pem1 = generate_rsa_key_pair()
        private_pem2, public_pem2 = generate_rsa_key_pair()

        provider1 = InAppKeyProvider(private_pem1, public_pem1)
        provider2 = InAppKeyProvider(private_pem2, public_pem2)

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
        }

        token = encode_access_token(claims, provider1, ttl_hours=1)

        # Try to decode with different provider
        decoded = decode_token(token, provider2)

        assert decoded is None

    def test_decode_token_kid_in_header(self) -> None:
        """Test that kid is included in token header."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
        }

        token = encode_access_token(claims, provider, ttl_hours=1)

        # Decode header without verification
        header = pyjwt.get_unverified_header(token)

        assert "kid" in header
        assert header["kid"] == provider.kid


class TestJwtRoundTrip:
    """Test full encode/decode round trips."""

    def test_round_trip_preserves_all_claims(self) -> None:
        """Test that all claims survive a round trip."""
        private_pem, public_pem = generate_rsa_key_pair()
        provider = InAppKeyProvider(private_pem, public_pem)

        original_claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read *:write *:admin",
            "teams": ["team1", "team2"],
            "roles": ["admin"],
        }

        token = encode_access_token(original_claims, provider, ttl_hours=1)
        decoded = decode_token(token, provider)

        assert decoded is not None
        for key in original_claims:
            assert decoded[key] == original_claims[key]
