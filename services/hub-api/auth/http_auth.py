"""Shared HTTP auth helpers for hub-api routes."""
from __future__ import annotations
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
