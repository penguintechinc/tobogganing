"""Authentication routes: login, refresh, logout."""
from __future__ import annotations

import structlog
from quart import Blueprint, current_app, jsonify, request

from core.auth.service import AuthService
from core.db import get_db

logger = structlog.get_logger()

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _mask_email(email: str) -> str:
    """Mask email for safe logging (e.g., alice@example.com → alice***@example.com)."""
    if not email or "@" not in email:
        return "***"
    parts = email.split("@")
    return f"{parts[0][0]}***@{parts[1]}"


@auth_bp.route("/login", methods=["POST"])
async def login() -> tuple[dict, int]:
    """Authenticate user by email and password.

    Request body: {email, password, mfa_token?}
    Returns:
    - 200 {access_token, refresh_token, expires_in: 3600, token_type: "Bearer"}
    - 200 {mfa_required: true} (no tokens) when MFA needed
    - 401 {error: "Invalid credentials"} on failure
    - 400 on missing fields
    """
    try:
        data = await request.get_json()
        if not data:
            return {"error": "Missing request body"}, 400

        email = data.get("email", "").strip()
        password = data.get("password", "")
        mfa_token = data.get("mfa_token")

        if not email or not password:
            return {"error": "Missing email or password"}, 400

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
                return {"mfa_required": True}, 200
            # Uniform 401 for any failure (unknown user or bad password)
            logger.warning("login_failed", email=_mask_email(email))
            return {"error": "Invalid credentials"}, 401

        # Success
        logger.info("login_success", email=_mask_email(email))
        return {
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "expires_in": 3600,
            "token_type": "Bearer",
        }, 200
    except Exception as e:
        logger.error("login_error", error=str(e))
        return {"error": "Invalid credentials"}, 401


@auth_bp.route("/refresh", methods=["POST"])
async def refresh() -> tuple[dict, int]:
    """Refresh an access token using a refresh token.

    Request body: {refresh_token}
    Returns:
    - 200 {access_token, refresh_token, expires_in: 3600, token_type: "Bearer"}
    - 401 on invalid/expired refresh token
    - 400 on missing fields
    """
    try:
        data = await request.get_json()
        if not data:
            return {"error": "Missing request body"}, 400

        refresh_token = data.get("refresh_token", "").strip()
        if not refresh_token:
            return {"error": "Missing refresh_token"}, 400

        # Get AuthService
        db = get_db()
        key_provider = current_app.config.get("KEY_PROVIDER")
        config = current_app.config_obj
        service = AuthService(db, config, key_provider)

        # Refresh
        result = await service.refresh_access_token(refresh_token)

        if not result.success:
            logger.warning("refresh_failed", error=result.error)
            return {"error": "Invalid credentials"}, 401

        # Success
        logger.info("refresh_success")
        return {
            "access_token": result.access_token,
            "refresh_token": refresh_token,  # Return original refresh token
            "expires_in": 3600,
            "token_type": "Bearer",
        }, 200
    except Exception as e:
        logger.error("refresh_error", error=str(e))
        return {"error": "Invalid credentials"}, 401


@auth_bp.route("/logout", methods=["POST"])
async def logout() -> tuple[dict, int]:
    """Logout user by revoking refresh token.

    Request body: {refresh_token}
    Returns:
    - 204 No Content on success
    - 400 on missing fields
    """
    try:
        data = await request.get_json()
        if not data:
            return {"error": "Missing request body"}, 400

        refresh_token = data.get("refresh_token", "").strip()
        if not refresh_token:
            return {"error": "Missing refresh_token"}, 400

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
            return {}, 204  # 204 even if token not found (idempotent)

        user_id = rt_record.user_id

        # Revoke all tokens for user
        success = await service.revoke_tokens(user_id)
        if success:
            logger.info("logout_success", user_id=user_id)
        else:
            logger.warning("logout_revoke_failed", user_id=user_id)

        return {}, 204
    except Exception as e:
        logger.error("logout_error", error=str(e))
        return {}, 204  # 204 even on error (idempotent)
