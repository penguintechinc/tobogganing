"""Additional coverage for hub_api.auth.middleware remaining branches.

test_middleware.py and test_session_auth.py cover the JWT/session happy and
common-error paths; this file fills in: invalid scope format, missing
key_provider, DAL-not-configured session validation, require_admin's JWT
fallback path, and _extract_machine_identity's individual failure branches.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart, g, jsonify

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.middleware import (
    _extract_machine_identity,
    _scope_satisfied,
    _validate_and_store_session,
    _validate_and_store_token,
    require_admin,
    require_machine_jwt,
)
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair


def test_scope_satisfied_invalid_format_no_colon() -> None:
    """_scope_satisfied() returns False for a required scope with no ':' separator."""
    assert _scope_satisfied("malformedscope", {"*:*"} - {"*:*"}) is False
    assert _scope_satisfied("malformedscope", {"malformedscope"}) is True  # exact match still ok
    assert _scope_satisfied("malformedscope", set()) is False


@pytest.fixture
def app_with_auth() -> Quart:
    """Quart app with a real key provider, no DAL/CACHE configured."""
    app = Quart(__name__)
    app.config["TESTING"] = True
    # Matches the "iss"/"aud" used by this file's *user*-JWT token fixtures
    # (iss="test"/aud="test"), so _validate_and_store_token's aud/iss
    # enforcement accepts them. Machine-JWT fixtures below intentionally use
    # aud="headend"/"wrong-audience" and are unaffected — they go through
    # _extract_machine_identity, which checks aud=="headend" itself.
    app.config["PRODUCT_NAME"] = "test"
    private_pem, public_pem = generate_rsa_key_pair()
    app.config["KEY_PROVIDER"] = InAppKeyProvider(private_pem, public_pem)
    return app


@pytest.mark.asyncio
async def test_validate_and_store_token_no_key_provider(app_with_auth: Quart) -> None:
    """_validate_and_store_token() returns False when KEY_PROVIDER is missing."""
    async with app_with_auth.app_context():
        async with app_with_auth.test_request_context(
            "/test", headers={"Authorization": "Bearer sometoken"}
        ):
            app_with_auth.config["KEY_PROVIDER"] = None
            result = await _validate_and_store_token()
    assert result is False


@pytest.mark.asyncio
async def test_validate_and_store_session_no_dal(app_with_auth: Quart) -> None:
    """_validate_and_store_session() returns (None, None) when DAL isn't configured."""
    async with app_with_auth.app_context():
        async with app_with_auth.test_request_context("/test"):
            user, tenant = await _validate_and_store_session("some-token")
    assert user is None
    assert tenant is None


@pytest.mark.asyncio
async def test_validate_and_store_session_query_error(app_with_auth: Quart) -> None:
    """_validate_and_store_session() returns (None, None) when the DAL query raises."""
    mock_dal = MagicMock()
    mock_dal.side_effect = RuntimeError("db down")
    app_with_auth.config["DAL"] = mock_dal

    async with app_with_auth.app_context():
        async with app_with_auth.test_request_context("/test"):
            user, tenant = await _validate_and_store_session("some-token")
    assert user is None
    assert tenant is None


class TestRequireAdminJwtPath:
    """Tests for require_admin()'s Bearer-JWT fallback (no session present)."""

    @pytest.mark.asyncio
    async def test_admin_scope_via_jwt_grants_access(self, app_with_auth: Quart) -> None:
        """A Bearer token with *:admin scope grants access when no session is present."""
        provider = app_with_auth.config["KEY_PROVIDER"]
        claims = {
            "sub": "user-1",
            "iss": "test",
            "aud": "test",
            "tenant": "t1",
            "scope": "*:admin",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_admin
        async def handler() -> Any:
            return jsonify({"ok": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test", headers={"Authorization": f"Bearer {token}"}
            ):
                response = await handler()
        assert response[1] == 200

    @pytest.mark.asyncio
    async def test_insufficient_jwt_scope_denied(self, app_with_auth: Quart) -> None:
        """A Bearer token without admin scope is denied (403)."""
        provider = app_with_auth.config["KEY_PROVIDER"]
        claims = {
            "sub": "user-1",
            "iss": "test",
            "aud": "test",
            "tenant": "t1",
            "scope": "clusters:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_admin
        async def handler() -> Any:
            return jsonify({"ok": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test", headers={"Authorization": f"Bearer {token}"}
            ):
                response = await handler()
        assert response[1] == 403


class TestExtractMachineIdentity:
    """Direct tests for _extract_machine_identity() branches."""

    @pytest.mark.asyncio
    async def test_no_key_provider(self, app_with_auth: Quart) -> None:
        """Returns (None, error) when KEY_PROVIDER is not configured."""
        app_with_auth.config["KEY_PROVIDER"] = None
        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test"):
                claims, error = await _extract_machine_identity("sometoken", "firewall:read")
        assert claims is None
        assert error == "key_provider_not_configured"

    @pytest.mark.asyncio
    async def test_invalid_token(self, app_with_auth: Quart) -> None:
        """Returns (None, error) for an undecodable token."""
        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test"):
                claims, error = await _extract_machine_identity("garbage", "firewall:read")
        assert claims is None
        assert error == "invalid_or_expired_token"

    @pytest.mark.asyncio
    async def test_wrong_audience(self, app_with_auth: Quart) -> None:
        """Returns (None, error) when aud != 'headend'."""
        provider = app_with_auth.config["KEY_PROVIDER"]
        claims_in = {
            "sub": "cluster:c1",
            "iss": "test",
            "aud": "wrong-audience",
            "tenant": "t1",
            "scope": "firewall:read",
        }
        token = await encode_access_token(claims_in, provider, ttl_hours=1)

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test"):
                claims, error = await _extract_machine_identity(token, "firewall:read")
        assert claims is None
        assert error == "invalid_audience"

    @pytest.mark.asyncio
    async def test_missing_scopes_claim(self, app_with_auth: Quart) -> None:
        """Returns (None, error) when the token has no scope claim."""
        provider = app_with_auth.config["KEY_PROVIDER"]
        claims_in = {
            "sub": "cluster:c1",
            "iss": "test",
            "aud": "headend",
            "tenant": "t1",
        }
        token = await encode_access_token(claims_in, provider, ttl_hours=1)

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test"):
                claims, error = await _extract_machine_identity(token, "firewall:read")
        assert claims is None
        assert error == "missing_scopes"

    @pytest.mark.asyncio
    async def test_insufficient_scope(self, app_with_auth: Quart) -> None:
        """Returns (None, error) when required scope isn't satisfied."""
        provider = app_with_auth.config["KEY_PROVIDER"]
        claims_in = {
            "sub": "cluster:c1",
            "iss": "test",
            "aud": "headend",
            "tenant": "t1",
            "scope": "wireguard:read",
        }
        token = await encode_access_token(claims_in, provider, ttl_hours=1)

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test"):
                claims, error = await _extract_machine_identity(token, "firewall:read")
        assert claims is None
        assert error == "insufficient_scope:firewall:read"

    @pytest.mark.asyncio
    async def test_revoked_jti_denied(self, app_with_auth: Quart) -> None:
        """Returns (None, 'revoked') when the jti is present in the cache denylist."""
        provider = app_with_auth.config["KEY_PROVIDER"]
        claims_in = {
            "sub": "cluster:c1",
            "iss": "test",
            "aud": "headend",
            "tenant": "t1",
            "scope": "firewall:read",
            "jti": "revoked-jti",
        }
        token = await encode_access_token(claims_in, provider, ttl_hours=1)

        mock_cache = MagicMock()
        app_with_auth.config["CACHE"] = mock_cache

        with patch("hub_api.auth.refresh.is_jti_revoked", new=AsyncMock(return_value=True)):
            async with app_with_auth.app_context():
                async with app_with_auth.test_request_context("/test"):
                    claims, error = await _extract_machine_identity(token, "firewall:read")
        assert claims is None
        assert error == "revoked"


@pytest.mark.asyncio
async def test_require_machine_jwt_empty_token_after_bearer_prefix(
    app_with_auth: Quart,
) -> None:
    """require_machine_jwt() rejects an Authorization header of exactly 'Bearer '."""

    @require_machine_jwt("firewall:read")
    async def handler() -> Any:
        return jsonify({"ok": True}), 200

    async with app_with_auth.app_context():
        async with app_with_auth.test_request_context(
            "/test", headers={"Authorization": "Bearer "}
        ):
            response = await handler()
    assert response[1] == 401
