"""RS256 JWT encoding and decoding for authentication tokens."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Optional

import jwt as pyjwt

from hub_api.crypto.keys import KeyProvider


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding (JWS serialization)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


async def encode_access_token(
    claims: dict[str, Any],
    key_provider: KeyProvider,
    ttl_hours: int = 1,
) -> str:
    """
    Encode an access token with RS256 signature via manual JWS assembly.

    Args:
        claims: Dictionary of claims to include in the token (must include 'sub', 'iss', 'aud', 'tenant').
        key_provider: KeyProvider instance for signing.
        ttl_hours: Time-to-live in hours (default 1).

    Returns:
        Encoded JWT token as string.

    Raises:
        ValueError: If required claims are missing.
    """
    required_claims = {"sub", "iss", "aud", "tenant"}
    if not required_claims.issubset(claims.keys()):
        raise ValueError(f"Missing required claims: {required_claims - set(claims.keys())}")

    now = int(time.time())
    payload = {
        **claims,
        "iat": now,
        "exp": now + (ttl_hours * 3600),
    }

    header = {"alg": "RS256", "typ": "JWT", "kid": key_provider.kid}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = await key_provider.sign(signing_input.encode("ascii"))
    return signing_input + "." + _b64url(signature)


def decode_token(
    token: str,
    key_provider: KeyProvider,
    algorithms: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Decode and validate an RS256 JWT token.

    Validates signature, expiration, and presence of required 'tenant' claim.
    Returns None if the token is invalid, expired, or missing the 'tenant' claim.

    Args:
        token: Encoded JWT token string.
        key_provider: KeyProvider instance for verification.
        algorithms: List of allowed algorithms (default ["RS256"]).

    Returns:
        Dictionary of decoded claims if valid, None otherwise.
    """
    if algorithms is None:
        algorithms = ["RS256"]

    try:
        claims = pyjwt.decode(
            token,
            key_provider.public_pem,
            algorithms=algorithms,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False,
            },
        )

        # Verify mandatory tenant claim
        if "tenant" not in claims:
            return None

        return claims
    except pyjwt.InvalidSignatureError:
        return None
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None
    except Exception:
        return None
