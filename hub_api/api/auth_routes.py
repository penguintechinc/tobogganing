"""Authentication routes: login, refresh, logout.

Browser (portal) auth: login/refresh set the access/refresh/CSRF tokens as
HttpOnly cookies (see auth/middleware.py::set_auth_cookies) IN ADDITION TO
returning them in the JSON body — this is purely additive, so non-browser
callers that only read the JSON body (mobile apps, CLI, service-to-service)
are unaffected. refresh-token/logout additionally accept the refresh token
from the `refresh_token` cookie when the request body omits it, since a
browser client can no longer read that HttpOnly cookie's value in JS. When
the refresh token is sourced from the cookie, the request must also carry a
matching X-CSRF-Token header (double-submit CSRF) — a body-supplied refresh
token (non-browser callers) is exempt, mirroring the bearer-header exemption
in auth/middleware.py.

All three routes are rate limited (security-audit 2026-09-21, Dim 3
A04/A07 -- none of these credential endpoints had brute-force protection).
login also rate-limits per submitted account, independent of the IP bucket,
so a distributed spray against one account is still caught; the 429
response shape is identical regardless of which bucket tripped so it never
leaks account existence.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import structlog
from quart import Blueprint, Response, current_app, jsonify, request

from hub_api.auth.middleware import REFRESH_TOKEN_COOKIE as _REFRESH_TOKEN_COOKIE
from hub_api.auth.middleware import (
    clear_auth_cookies,
    csrf_token_valid,
    revoke_current_access_token,
    set_auth_cookies,
)
from hub_api.auth.service import AuthService
from hub_api.db import get_db
from hub_api.security.rate_limit import (
    SlidingWindowRateLimiter,
    hash_identifier,
    ip_key,
    rate_limited,
)

logger = structlog.get_logger()

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

# Env-configurable, always-on (never PostHog-gated -- this is a baseline
# security control, not a product feature). Conservative defaults: login is
# the highest-value brute-force target, refresh/logout are lighter since
# they require an already-issued (opaque) refresh token to attempt.
_LOGIN_MAX = int(os.getenv("RATE_LIMIT_LOGIN_MAX", "10"))
_LOGIN_WINDOW_SECS = int(os.getenv("RATE_LIMIT_LOGIN_WINDOW_SECS", "60"))
_REFRESH_MAX = int(os.getenv("RATE_LIMIT_REFRESH_MAX", "30"))
_REFRESH_WINDOW_SECS = int(os.getenv("RATE_LIMIT_REFRESH_WINDOW_SECS", "60"))
_LOGOUT_MAX = int(os.getenv("RATE_LIMIT_LOGOUT_MAX", "60"))
_LOGOUT_WINDOW_SECS = int(os.getenv("RATE_LIMIT_LOGOUT_WINDOW_SECS", "60"))

_login_ip_limiter = SlidingWindowRateLimiter(_LOGIN_MAX, _LOGIN_WINDOW_SECS, "auth_login_ip")
_login_acct_limiter = SlidingWindowRateLimiter(_LOGIN_MAX, _LOGIN_WINDOW_SECS, "auth_login_acct")
_refresh_ip_limiter = SlidingWindowRateLimiter(
    _REFRESH_MAX, _REFRESH_WINDOW_SECS, "auth_refresh_ip"
)
_logout_ip_limiter = SlidingWindowRateLimiter(_LOGOUT_MAX, _LOGOUT_WINDOW_SECS, "auth_logout_ip")


async def _login_account_key() -> Optional[str]:
    """Per-account rate-limit bucket key for login: SHA-256(lowercased email).

    Independent of whether the account exists, so checking this bucket
    never itself reveals account existence -- only the ip bucket key_func
    (hub_api.security.rate_limit.ip_key) is skip-able (returns None) when
    absent; this one only skips on a missing/malformed body, which the
    route handler's own validation also rejects (400) uniformly.
    """
    data = await request.get_json(silent=True)
    if not data:
        return None
    email = (data.get("email") or "").strip().lower()
    return hash_identifier(email) if email else None


def _refresh_token_from_request(data: dict[str, Any]) -> tuple[str, bool]:
    """Extract the refresh token from the request body, falling back to cookie.

    Args:
        data: Parsed JSON request body (may be empty).

    Returns:
        Tuple of (refresh_token, from_cookie). from_cookie is True only when
        the body did not supply one and it was read from the refresh_token
        cookie instead — used to decide whether CSRF must be enforced.
    """
    body_token = (data.get("refresh_token") or "").strip()
    if body_token:
        return body_token, False
    return request.cookies.get(_REFRESH_TOKEN_COOKIE, "").strip(), True


def _mask_email(email: str) -> str:
    """Mask email for safe logging (e.g., alice@example.com → alice***@example.com)."""
    if not email or "@" not in email:
        return "***"
    parts = email.split("@")
    return f"{parts[0][0]}***@{parts[1]}"


@auth_bp.route("/login", methods=["POST"])
@rate_limited(
    (_login_ip_limiter, ip_key),
    (_login_acct_limiter, _login_account_key),
    event="auth_login",
)
async def login() -> tuple[Response, int]:
    """Authenticate user by email and password.

    Request body: {email, password, mfa_token?}
    Returns:
    - 200 {access_token, refresh_token, expires_in: 3600, token_type: "Bearer"}
      Also sets access_token/refresh_token/csrf_token as HttpOnly (except
      csrf_token) cookies for the browser/portal flow — additive, the JSON
      body is unchanged for non-browser callers.
    - 200 {mfa_required: true} (no tokens, no cookies) when MFA needed
    - 401 {error: "Invalid credentials"} on failure
    - 400 on missing fields

    Login is never CSRF-checked: it authenticates via credentials (email/
    password), not an ambient cookie — it's the origin of the auth cookies,
    not a consumer of them.
    """
    try:
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400

        email = data.get("email", "").strip()
        password = data.get("password", "")
        mfa_token = data.get("mfa_token")

        if not email or not password:
            return jsonify({"error": "Missing email or password"}), 400

        # Log with masked email, never log password
        logger.info("login_attempt", email=_mask_email(email))

        # Get AuthService
        db = get_db()
        key_provider = current_app.config.get("KEY_PROVIDER")
        config = current_app.config_obj
        service = AuthService(db, config, key_provider)

        # Authenticate
        result = await service.authenticate(email, password, mfa_token)

        if not result.success:
            if result.mfa_required:
                logger.info("login_mfa_required", email=_mask_email(email))
                return jsonify({"mfa_required": True}), 200
            # Uniform 401 for any failure (unknown user or bad password)
            logger.warning("login_failed", email=_mask_email(email))
            return jsonify({"error": "Invalid credentials"}), 401

        # Success
        logger.info("login_success", email=_mask_email(email))
        if result.access_token is None or result.refresh_token is None:
            # AuthResult.success=True must always carry both tokens; treat a
            # violation of that contract as a hard failure rather than an
            # `assert` (stripped under `python -O`, unlike this check).
            logger.error("login_success_missing_tokens", email=_mask_email(email))
            return jsonify({"error": "Invalid credentials"}), 401
        response = jsonify(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        )
        set_auth_cookies(response, result.access_token, result.refresh_token)
        return response, 200
    except Exception as e:
        logger.error("login_error", error=str(e))
        return jsonify({"error": "Invalid credentials"}), 401


@auth_bp.route("/refresh-token", methods=["POST"])
@rate_limited((_refresh_ip_limiter, ip_key), event="auth_refresh_token")
async def refresh() -> tuple[Response, int]:
    """Refresh an access token using a refresh token.

    Request body: {refresh_token} — optional for browser callers, which may
    omit the body entirely and rely on the refresh_token cookie instead (the
    cookie is HttpOnly, so portal JS cannot read its value to put it in the
    body). A body-supplied token always takes precedence (non-browser callers:
    mobile apps, CLI). When the token is sourced from the cookie, the request
    must also carry a matching X-CSRF-Token header (double-submit CSRF) —
    body-supplied tokens are exempt, mirroring the bearer-header exemption on
    the general resource API.

    Returns:
    - 200 {access_token, refresh_token, expires_in: 3600, token_type: "Bearer"}
      Also rotates the access_token/refresh_token/csrf_token cookies for
      browser callers.
    - 401 on invalid/expired refresh token
    - 400 on missing fields
    - 403 on missing/invalid CSRF token (cookie-sourced refresh token only)

    Route-shadowing regression (fixed): this used to be registered at
    POST /api/v1/auth/refresh, which collided with headend_bp's machine
    refresh route at the exact same path (headend_routes.py:502). Because
    auth_bp is registered first in create_app(), it silently shadowed the
    machine handler for every request. Moved to /refresh-token so both
    user and machine refresh flows are independently reachable. The
    machine path is documented in docs/architecture/headend-machine-jwt-contract.md
    and consumed by live machine clients (services/hub-router (Go),
    agents/node-agent (Rust)), so it keeps its original path instead.
    """
    try:
        data = await request.get_json(silent=True) or {}

        refresh_token, from_cookie = _refresh_token_from_request(data)
        if not refresh_token:
            return jsonify({"error": "Missing refresh_token"}), 400

        if from_cookie and not csrf_token_valid():
            logger.warning("refresh_csrf_invalid")
            return jsonify({"error": "Forbidden: CSRF token missing or invalid"}), 403

        # Get AuthService
        db = get_db()
        key_provider = current_app.config.get("KEY_PROVIDER")
        config = current_app.config_obj
        service = AuthService(db, config, key_provider)

        # Refresh
        result = await service.refresh_access_token(refresh_token)

        if not result.success:
            logger.warning("refresh_failed", error=result.error)
            return jsonify({"error": "Invalid credentials"}), 401

        # Success — refresh tokens are single-use and rotated on every call
        # (security-review finding HIGH-A), so the NEW refresh token minted
        # by AuthService is returned, never the one the caller presented.
        logger.info("refresh_success")
        if result.access_token is None or result.refresh_token is None:
            # AuthResult.success=True must always carry both tokens; treat a
            # violation of that contract as a hard failure rather than an
            # `assert` (stripped under `python -O`, unlike this check).
            logger.error("refresh_success_missing_tokens")
            return jsonify({"error": "Invalid credentials"}), 401
        response = jsonify(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        )
        set_auth_cookies(response, result.access_token, result.refresh_token)
        return response, 200
    except Exception as e:
        logger.error("refresh_error", error=str(e))
        return jsonify({"error": "Invalid credentials"}), 401


@auth_bp.route("/logout", methods=["POST"])
@rate_limited((_logout_ip_limiter, ip_key), event="auth_logout")
async def logout() -> tuple[Response, int]:
    """Logout user by revoking refresh token.

    Request body: {refresh_token} — optional for browser callers, which may
    omit the body and rely on the refresh_token cookie instead (see
    _refresh_token_from_request). Always clears the access_token/
    refresh_token/csrf_token cookies, regardless of whether a valid token was
    found (idempotent, matching the existing 204-even-on-unknown-token
    behavior).

    Returns:
    - 204 No Content on success
    - 400 on missing fields
    - 403 on missing/invalid CSRF token (cookie-sourced refresh token only)
    """
    try:
        data = await request.get_json(silent=True) or {}

        refresh_token, from_cookie = _refresh_token_from_request(data)
        if not refresh_token:
            response = jsonify({"error": "Missing refresh_token"})
            clear_auth_cookies(response)
            return response, 400

        if from_cookie and not csrf_token_valid():
            logger.warning("logout_csrf_invalid")
            response = jsonify({"error": "Forbidden: CSRF token missing or invalid"})
            return response, 403

        # Best-effort: denylist the presented access JWT (bearer header or
        # cookie) so it stops authenticating immediately rather than
        # remaining valid until its natural 1h expiry -- never raises, so
        # a decode/cache failure here can't block logout.
        await revoke_current_access_token()

        # Get AuthService to extract user_id from refresh_tokens table
        db = get_db()
        key_provider = current_app.config.get("KEY_PROVIDER")
        config = current_app.config_obj
        service = AuthService(db, config, key_provider)

        # Query refresh token to get user_id
        rowset = await db(db.refresh_tokens.token == refresh_token).select()
        rt_record = rowset.first()
        if not rt_record:
            logger.warning("logout_invalid_token")
            response = jsonify({})
            clear_auth_cookies(response)
            return response, 204  # 204 even if token not found (idempotent)

        user_id = rt_record.user_id

        # Revoke all tokens for user
        success = await service.revoke_tokens(user_id)
        if success:
            logger.info("logout_success", user_id=user_id)
        else:
            logger.warning("logout_revoke_failed", user_id=user_id)

        response = jsonify({})
        clear_auth_cookies(response)
        return response, 204
    except Exception as e:
        logger.error("logout_error", error=str(e))
        response = jsonify({})
        clear_auth_cookies(response)
        return response, 204  # 204 even on error (idempotent)
