"""RS256 JWT encoding and decoding for authentication tokens."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

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
    *,
    expected_iss: str | None = None,
    expected_aud: str | None = None,
) -> dict[str, Any] | None:
    """
    Decode and validate an RS256 JWT token.

    Validates signature, expiration, and presence of required 'tenant' claim.
    Returns None if the token is invalid, expired, or missing the 'tenant' claim.

    aud/iss verification is opt-in via ``expected_iss``/``expected_aud`` and is
    intentionally NOT performed by default: this decoder is shared across every
    token type in the app (user JWTs, node/cluster JWTs, and machine JWTs), and
    those legitimately use different audiences (e.g. user/node tokens use
    ``aud=="tobogganing"``/``PRODUCT_NAME``, while headend machine-JWTs use
    ``aud=="headend"``, checked separately by
    ``auth/middleware.py::_extract_machine_identity``). Callers on a single,
    known-audience path (e.g. ``auth/middleware.py::_validate_and_store_token``,
    the general user-JWT path) should pass both to reject tokens minted for a
    different issuer/audience.

    Args:
        token: Encoded JWT token string.
        key_provider: KeyProvider instance for verification.
        algorithms: List of allowed algorithms (default ["RS256"]).
        expected_iss: If provided, reject tokens whose 'iss' claim doesn't match.
        expected_aud: If provided, reject tokens whose 'aud' claim doesn't match.

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

        if expected_iss is not None and claims.get("iss") != expected_iss:
            return None

        if expected_aud is not None and claims.get("aud") != expected_aud:
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
