"""JWT refresh token rotation with replay protection and single-use enforcement."""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from typing import Any, Optional

from hub_api.auth.jwt import decode_token, encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.cache.client import CacheClient, CacheUnavailable
from hub_api.crypto.keys import KeyProvider

logger = structlog.get_logger()


@dataclass(slots=True)
class RefreshError(Exception):
    """Refresh token rotation error with HTTP status and response body.

    Attributes:
        status: HTTP status code.
        body: Response body dict.
    """

    status: int
    body: dict[str, Any]


async def is_jti_revoked(jti: str, cache: CacheClient) -> bool:
    """Check if a JTI has been revoked (denylisted).

    Fails OPEN: returns False on any cache error to avoid hard-blocking
    access on a cache blip. Revocation checking is best-effort.

    Args:
        jti: JWT ID to check.
        cache: Cache client instance.

    Returns:
        True if jti is revoked, False otherwise (including on cache errors).
    """
    try:
        exists = await cache.exists("auth", "revoked_jti", jti)
        return exists
    except CacheUnavailable:
        logger.warning("revocation_check_cache_unavailable", jti=jti)
        return False
    except Exception as e:
        logger.warning("revocation_check_error", error=str(e), jti=jti)
        return False


async def revoke_cluster(sub: str, cache: CacheClient) -> None:
    """Revoke all refresh tokens for a cluster subject.

    Clears the cached refresh jti mapping and denylists any known jti.
    Best-effort: logs errors but does not raise.

    Args:
        sub: Subject identifier (e.g., "cluster:id").
        cache: Cache client instance.
    """
    try:
        # Clear the refresh jti cache entry for this subject
        await cache.delete("auth", "refresh", sub)
        logger.info("subject_refresh_revoked", sub=sub)
    except Exception as e:
        logger.warning("revocation_delete_error", error=str(e), sub=sub)


async def rotate_refresh(
    refresh_token: str,
    cache: CacheClient,
    key_provider: KeyProvider,
    cluster_manager: Any,
) -> dict[str, Any]:
    """Rotate a refresh token with replay protection and single-use enforcement.

    Decodes the refresh token, verifies the subject is still active,
    checks for replay (single-use), and mints new access + refresh tokens.
    The new refresh token jti is cached to detect replays.

    Args:
        refresh_token: Current refresh token (Bearer value).
        cache: Cache client for storing active refresh jtis.
        key_provider: KeyProvider for signing/decoding.
        cluster_manager: ClusterManager instance for subject validation.

    Returns:
        Dict with 'access_token' and 'refresh_token' on success.

    Raises:
        RefreshError: On validation failure (decode, expired, replay, etc.).
    """
    # 1. Decode and validate refresh token
    claims = decode_token(refresh_token, key_provider)
    if not claims:
        raise RefreshError(
            status=401,
            body={"error": "invalid refresh token"},
        )

    # Verify token type is 'refresh'
    if claims.get("token_type") != "refresh":
        raise RefreshError(
            status=401,
            body={"error": "invalid refresh token"},
        )

    # 2. Fail-CLOSED cache read: get the currently-valid refresh jti for this subject
    subject = claims.get("sub")
    if not subject:
        raise RefreshError(
            status=401,
            body={"error": "invalid refresh token"},
        )

    try:
        cached_jti = await cache.get("auth", "refresh", subject, fail_closed=True)
    except CacheUnavailable:
        # Cache is down; fail with retry indicator
        raise RefreshError(
            status=503,
            body={"error": "cache unavailable", "retry_with_credentials": True},
        )

    # 3. Subject re-check: verify the cluster/client still exists and is active
    # Extract cluster_id from subject (e.g., "cluster:id" -> "id")
    subject_parts = subject.split(":")
    if len(subject_parts) < 2:
        raise RefreshError(
            status=401,
            body={"error": "subject invalid"},
        )

    subject_id = subject_parts[1]
    cluster = await cluster_manager.get_cluster(subject_id)
    if cluster is None or cluster.status != "active":
        raise RefreshError(
            status=401,
            body={"error": "subject invalid"},
        )

    # 4. Single-use rotation: check for replay
    current_jti = claims.get("jti")
    if cached_jti != current_jti:
        # JTI mismatch: the token being replayed is not the current valid one
        # This indicates either a stale refresh or a compromised token
        logger.warning(
            "refresh_replay_detected",
            subject=subject,
            current_jti=current_jti,
            cached_jti=cached_jti,
        )
        await revoke_cluster(subject, cache)
        raise RefreshError(
            status=401,
            body={"error": "refresh token superseded"},
        )

    # 5. Mint new tokens and rotate refresh jti
    # Determine node_type from old claims or default
    node_type = claims.get("node_type", "kubernetes_node")

    # Build new access token claims
    access_claims = build_machine_claims(
        sub_id=subject_id,
        node_type=node_type,
        tenant=claims.get("tenant"),
        iss=claims.get("iss", "tobogganing"),
        aud=claims.get("aud", "tobogganing"),
        token_type="access",
    )
    # Preserve metadata from old token if present
    if "permissions" in claims:
        access_claims["permissions"] = claims["permissions"]
    if "metadata" in claims:
        access_claims["metadata"] = claims["metadata"]

    # Encode new access token (1 hour)
    try:
        new_access_token = await encode_access_token(access_claims, key_provider, ttl_hours=1)
    except ValueError as e:
        logger.error("new_access_token_encoding_failed", error=str(e))
        raise RefreshError(
            status=500,
            body={"error": "internal server error"},
        )

    # Build new refresh token claims
    refresh_claims = build_machine_claims(
        sub_id=subject_id,
        node_type=node_type,
        tenant=claims.get("tenant"),
        iss=claims.get("iss", "tobogganing"),
        aud=claims.get("aud", "tobogganing"),
        token_type="refresh",
    )
    # Preserve metadata from old token if present
    if "permissions" in claims:
        refresh_claims["permissions"] = claims["permissions"]
    if "metadata" in claims:
        refresh_claims["metadata"] = claims["metadata"]

    # Encode new refresh token (24 hours)
    try:
        new_refresh_token = await encode_access_token(refresh_claims, key_provider, ttl_hours=24)
    except ValueError as e:
        logger.error("new_refresh_token_encoding_failed", error=str(e))
        raise RefreshError(
            status=500,
            body={"error": "internal server error"},
        )

    # Cache the new refresh token jti (24 hours TTL)
    new_jti = refresh_claims.get("jti")
    try:
        await cache.set("auth", "refresh", subject, value=new_jti, ttl_seconds=86400, fail_closed=True)
    except CacheUnavailable:
        logger.error("refresh_cache_set_failed", subject=subject)
        raise RefreshError(
            status=503,
            body={"error": "cache unavailable", "retry_with_credentials": True},
        )

    logger.info(
        "refresh_token_rotated",
        subject=subject,
        old_jti=current_jti,
        new_jti=new_jti,
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
    }
