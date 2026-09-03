"""Regression tests for the 5 Medium hub_api security findings (fix/med-hub-jwt).

Covers:
1. aud/iss validation on core/api/jwt.py's /jwt/validate and /jwt/refresh.
2. /jwt/refresh rotation + cache-backed (not in-process) revocation.
3. MAX_CONTENT_LENGTH cap on the Quart app.
4. Security response headers (nosniff, frame-options, CSP, HSTS, referrer).
5. Constant-time login (bcrypt runs even for an unknown email).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import pytest
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.service import _DUMMY_PASSWORD_HASH, AuthService
from hub_api.cache.client import CacheClient, CacheUnavailable
from hub_api.config import Config
from hub_api.core.api.jwt import _is_revoked, _revoke_jti, _revoke_subject
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.tests.conftest import make_mock_row, make_mock_rowset


def _flag_on() -> Any:
    """Context manager patching the feature gate to always allow."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=True)


@pytest.fixture
def app_with_jwt(app: Quart) -> Quart:
    """App with KEY_PROVIDER and cluster/client managers wired for jwt routes.

    Args:
        app: Base test app fixture (from conftest; also carries app.config["CACHE"]).

    Returns:
        Quart app configured for core/api/jwt.py blueprint tests.
    """
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    cluster_manager = MagicMock()
    cluster_manager.authenticate_cluster = AsyncMock()
    cluster_manager.get_cluster = AsyncMock(return_value=None)
    client_registry = MagicMock()
    client_registry.authenticate_client = AsyncMock()
    client_registry.get_client = AsyncMock(return_value=None)
    app.config["CLUSTER_MANAGER"] = cluster_manager
    app.config["CLIENT_REGISTRY"] = client_registry

    return app


def _valid_refresh_claims() -> dict[str, Any]:
    """Base claims matching what generate_jwt_token issues (iss=aud=tobogganing)."""
    return {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "jti": "orig-jti-1",
        "token_type": "refresh",
    }


# ---------------------------------------------------------------------------
# Finding 1: aud/iss validation on core/api/jwt.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_rejects_wrong_audience(app_with_jwt: Quart) -> None:
    """POST /jwt/validate rejects a token with a mismatched aud claim."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "some-other-audience",
        "tenant": "acme",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 401
    data = await resp.get_json()
    assert data["error"] == "Invalid or expired token"


@pytest.mark.asyncio
async def test_validate_rejects_wrong_issuer(app_with_jwt: Quart) -> None:
    """POST /jwt/validate rejects a token with a mismatched iss claim."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "some-other-issuer",
        "aud": "tobogganing",
        "tenant": "acme",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_validate_rejects_missing_aud_iss(app_with_jwt: Quart) -> None:
    """POST /jwt/validate rejects a token missing aud/iss entirely."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    # encode_access_token requires aud/iss to be present to encode at all,
    # so build a token with empty-string aud/iss to simulate a forged/odd token.
    claims = {"sub": "cluster:c1", "iss": "", "aud": "", "tenant": "acme"}
    token = await encode_access_token(claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_wrong_audience(app_with_jwt: Quart) -> None:
    """POST /jwt/refresh rejects a refresh token with a mismatched aud claim."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {**_valid_refresh_claims(), "aud": "headend"}
    refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401
    data = await resp.get_json()
    assert data["error"] == "Invalid or expired refresh token"


@pytest.mark.asyncio
async def test_validate_accepts_matching_aud_iss(app_with_jwt: Quart) -> None:
    """POST /jwt/validate still accepts a correctly-issued token (no regression)."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Finding 2: /jwt/refresh rotation + cache-backed revocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token(app_with_jwt: Quart) -> None:
    """POST /jwt/refresh returns a brand-new refresh_token, not the one presented."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    refresh_token = await encode_access_token(_valid_refresh_claims(), provider, ttl_hours=24)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = await resp.get_json()
    assert "refresh_token" in data
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_token_replay_rejected(app_with_jwt: Quart) -> None:
    """A refresh token that was already used once is rejected on replay.

    This is the durable, cache-backed revocation replacing the old in-process
    ``_REVOKED_TOKENS`` set (useless across pods/restarts).
    """
    provider = app_with_jwt.config["KEY_PROVIDER"]
    refresh_token = await encode_access_token(_valid_refresh_claims(), provider, ttl_hours=24)

    client = app_with_jwt.test_client()
    with _flag_on():
        first = await client.post("/api/v1/jwt/refresh", json={"refresh_token": refresh_token})
        assert first.status_code == 200

        replay = await client.post("/api/v1/jwt/refresh", json={"refresh_token": refresh_token})
    assert replay.status_code == 401
    data = await replay.get_json()
    assert data["error"] == "Invalid or expired refresh token"


@pytest.mark.asyncio
async def test_revoke_persists_to_cache_and_blocks_validate(app_with_jwt: Quart) -> None:
    """POST /jwt/revoke durably marks a node revoked; a token issued before it fails /jwt/validate."""
    provider = app_with_jwt.config["KEY_PROVIDER"]

    # Access token for the node being revoked (issued "now").
    node_claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
    }
    node_token = await encode_access_token(node_claims, provider, ttl_hours=1)

    # Caller token with jwt:revoke scope, different tenant claim doesn't matter
    # here since CLUSTER_MANAGER.get_cluster/CLIENT_REGISTRY.get_client both
    # resolve to None in app_with_jwt (no tenant mismatch possible).
    caller_claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "scope": "jwt:revoke",
    }
    caller_token = await encode_access_token(caller_claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        revoke_resp = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "c1"},
            headers={"Authorization": f"Bearer {caller_token}"},
        )
        assert revoke_resp.status_code == 200

        # The cache entry must actually be persisted (durable, not in-process).
        cache = app_with_jwt.config["CACHE"]
        revoked_at = await cache.get("auth", "revoked_subject", "c1")
        assert revoked_at is not None

        validate_resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": f"Bearer {node_token}"},
        )
    assert validate_resp.status_code == 401
    data = await validate_resp.get_json()
    assert data["error"] == "Token has been revoked"


@pytest.mark.asyncio
async def test_is_revoked_no_cache_fails_open() -> None:
    """_is_revoked with no cache configured returns False (fail open)."""
    assert await _is_revoked({"sub": "cluster:c1", "jti": "x"}, None) is False


@pytest.mark.asyncio
async def test_is_revoked_empty_subject_returns_false() -> None:
    """_is_revoked with no jti and an empty/unparseable sub returns False."""
    cache = AsyncMock(spec=CacheClient)
    assert await _is_revoked({"sub": ""}, cache) is False
    cache.get.assert_not_called()


@pytest.mark.asyncio
async def test_is_revoked_subject_cache_get_error_fails_open() -> None:
    """_is_revoked swallows a cache.get error and fails open (returns False)."""
    cache = AsyncMock(spec=CacheClient)
    cache.get.side_effect = Exception("cache boom")
    result = await _is_revoked({"sub": "cluster:c1", "iat": 100}, cache)
    assert result is False


@pytest.mark.asyncio
async def test_is_revoked_unparseable_revoked_at_fails_open() -> None:
    """_is_revoked treats a corrupt revoked_subject cache value as not-revoked."""
    cache = AsyncMock(spec=CacheClient)
    cache.get.return_value = "not-an-int"
    result = await _is_revoked({"sub": "cluster:c1", "iat": 100}, cache)
    assert result is False


@pytest.mark.asyncio
async def test_revoke_jti_cache_unavailable_does_not_raise() -> None:
    """_revoke_jti swallows CacheUnavailable (best-effort, never blocks rotation)."""
    cache = AsyncMock(spec=CacheClient)
    cache.set.side_effect = CacheUnavailable("cache down")
    await _revoke_jti("some-jti", cache, exp=None)  # must not raise


@pytest.mark.asyncio
async def test_revoke_jti_noop_without_cache_or_jti() -> None:
    """_revoke_jti is a no-op when cache or jti is missing."""
    await _revoke_jti(None, AsyncMock(spec=CacheClient))
    await _revoke_jti("jti", None)


@pytest.mark.asyncio
async def test_revoke_subject_without_cache_logs_and_does_not_raise() -> None:
    """_revoke_subject logs the revocation-store limitation when CACHE is unset."""
    with patch("hub_api.core.api.jwt.logger.warning") as mock_warning:
        await _revoke_subject("node-1", None)  # must not raise
    mock_warning.assert_called_once()


@pytest.mark.asyncio
async def test_revoke_subject_cache_unavailable_does_not_raise() -> None:
    """_revoke_subject swallows CacheUnavailable (best-effort revoke)."""
    cache = AsyncMock(spec=CacheClient)
    cache.set.side_effect = CacheUnavailable("cache down")
    await _revoke_subject("node-1", cache)  # must not raise


# ---------------------------------------------------------------------------
# Finding 3: MAX_CONTENT_LENGTH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_content_length_configured(app: Quart) -> None:
    """The app sets a sane (well below Quart's 16 MiB default) request body cap."""
    assert app.config["MAX_CONTENT_LENGTH"] == 1 * 1024 * 1024


@pytest.mark.asyncio
async def test_oversized_request_body_rejected(app: Quart) -> None:
    """A body over MAX_CONTENT_LENGTH is rejected by Quart before full parsing.

    The route's own broad ``except Exception`` still maps this to its
    generic error response (401 for /auth/login), but the underlying error
    confirms Quart's RequestEntityTooLarge fired instead of the body being
    fully buffered/parsed.
    """
    big_body = b"a" * (app.config["MAX_CONTENT_LENGTH"] + 1024)
    client = app.test_client()

    with patch("hub_api.api.auth_routes.logger.error") as mock_log_error:
        resp = await client.post(
            "/api/v1/auth/login",
            data=big_body,
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 401
    mock_log_error.assert_called_once()
    _, kwargs = mock_log_error.call_args
    assert "413" in kwargs.get("error", "") or "Too Large" in kwargs.get("error", "")


# ---------------------------------------------------------------------------
# Finding 4: security headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_present(app: Quart) -> None:
    """Every response carries the baseline security header set."""
    client = app.test_client()
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Content-Security-Policy"] == ("default-src 'none'; frame-ancestors 'none'")
    assert resp.headers["Strict-Transport-Security"] == (
        "max-age=63072000; includeSubDomains; preload"
    )
    assert resp.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_security_headers_present_on_error_response(app: Quart) -> None:
    """Security headers are also attached to error responses (404)."""
    client = app.test_client()
    resp = await client.get("/no-such-route")

    assert resp.status_code == 404
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


# ---------------------------------------------------------------------------
# Finding 5: constant-time login (no user-enumeration via timing)
# ---------------------------------------------------------------------------


@pytest.fixture
def key_provider() -> InAppKeyProvider:
    """Provide a test key provider."""
    private_pem, public_pem = generate_rsa_key_pair()
    return InAppKeyProvider(private_pem, public_pem)


@pytest.fixture
def test_config() -> Config:
    """Provide a test configuration."""
    return Config(db_type="sqlite", db_name=":memory:", product_name="test-app")


@pytest.fixture
def mock_db_for_auth() -> MagicMock:
    """Mock DB configured for AuthService.authenticate() calls."""
    db = MagicMock()

    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
    db.return_value = query_proxy
    db.users = MagicMock()
    return db


@pytest.mark.asyncio
async def test_authenticate_unknown_user_still_calls_bcrypt_checkpw(
    mock_db_for_auth: MagicMock,
    test_config: Config,
    key_provider: InAppKeyProvider,
) -> None:
    """Regression: unknown-email login must still run bcrypt.checkpw.

    Prior behavior returned immediately on ``user is None``, skipping the
    bcrypt comparison entirely — a fast-fail that leaked, via response time,
    whether an email exists (security-review Medium finding #5).
    """
    service = AuthService(mock_db_for_auth, test_config, key_provider)

    with patch("hub_api.auth.service.bcrypt.checkpw", wraps=bcrypt.checkpw) as spy:
        result = await service.authenticate("ghost@example.com", "irrelevant")

    assert result.success is False
    spy.assert_called_once()
    compared_hash = spy.call_args[0][1]
    assert compared_hash == _DUMMY_PASSWORD_HASH.encode("utf-8")


@pytest.mark.asyncio
async def test_authenticate_known_user_wrong_password_calls_bcrypt_checkpw(
    mock_db_for_auth: MagicMock,
    test_config: Config,
    key_provider: InAppKeyProvider,
) -> None:
    """A known user with a wrong password also goes through bcrypt.checkpw once.

    Together with the unknown-user test above, this confirms both branches
    take the same code path (one bcrypt.checkpw call) rather than the
    unknown-user branch short-circuiting before it.
    """
    real_hash = bcrypt.hashpw(b"correct-password", bcrypt.gensalt()).decode("utf-8")
    user = make_mock_row(
        {
            "id": "user-1",
            "email": "alice@example.com",
            "password_hash": real_hash,
            "is_active": True,
            "mfa_enabled": False,
            "tenant": "acme",
            "role": "viewer",
            "teams": [],
        }
    )
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([user]))
    mock_db_for_auth.return_value = query_proxy

    service = AuthService(mock_db_for_auth, test_config, key_provider)

    with patch("hub_api.auth.service.bcrypt.checkpw", wraps=bcrypt.checkpw) as spy:
        result = await service.authenticate("alice@example.com", "wrong-password")

    assert result.success is False
    spy.assert_called_once()
    compared_hash = spy.call_args[0][1]
    assert compared_hash == real_hash.encode("utf-8")
