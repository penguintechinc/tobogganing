"""Shared HTTP auth helpers for hub-api routes."""
from __future__ import annotations
import hmac
import os
from typing import Mapping, Optional

_PREFIX = "Bearer "


def extract_bearer_token(headers: Mapping[str, str]) -> Optional[str]:
    """Extract bearer token from Authorization header.

    Args:
        headers: Request headers mapping.

    Returns:
        Token string if valid Bearer header found, else None.
    """
    value = headers.get("Authorization", "") or ""
    if not value.startswith(_PREFIX):
        return None
    token = value[len(_PREFIX):].strip()
    return token or None


def verify_bootstrap_token(token: Optional[str]) -> bool:
    """Constant-time check of an enrollment/bootstrap token. Deny if unset.

    Args:
        token: The token to verify.

    Returns:
        True if token matches ENROLLMENT_BOOTSTRAP_TOKEN (constant-time),
        False otherwise or if env var is unset.
    """
    expected = os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)
