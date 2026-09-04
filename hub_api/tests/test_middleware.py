"""Tests for authentication middleware."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import jwt as pyjwt
import pytest
from quart import Quart, jsonify

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.middleware import (
    clear_auth_cookies,
    current_claims,
    require_scope,
    require_tenant,
    set_auth_cookies,
)
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair


@pytest.fixture
def app_with_auth() -> Quart:
    """Create a test app with auth middleware configured."""
    from quart import Quart

    app = Quart(__name__)
    app.config["TESTING"] = True
    # Matches the "iss"/"aud" used by every token minted in this file's tests,
    # so _validate_and_store_token's aud/iss enforcement (auth/middleware.py)
    # accepts them exactly as it would accept a real app's PRODUCT_NAME tokens.
    app.config["PRODUCT_NAME"] = "test-app"

    # Set up key provider
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    return app


class TestRequireTenant:
    """Test the require_tenant decorator."""

    @pytest.mark.asyncio
    async def test_require_tenant_missing_token(self, app_with_auth: Quart) -> None:
        """Test that require_tenant returns 403 when token is missing."""

        @require_tenant
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_tenant_invalid_token(self, app_with_auth: Quart) -> None:
        """Test that require_tenant returns 403 when token is invalid."""

        @require_tenant
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": "Bearer invalid.token.here"},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_tenant_missing_tenant_claim(self, app_with_auth: Quart) -> None:
        """Test that require_tenant returns 403 when tenant claim is missing."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        # Create a token without tenant claim
        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            # Intentionally missing 'tenant' claim
        }

        # Encode without tenant (we'll manually create it)
        now = int(time.time())
        payload = {
            **claims,
            "iat": now,
            "exp": now + 3600,
        }

        token = pyjwt.encode(
            payload,
            provider._private_key_pem,
            algorithm="RS256",
            headers={"kid": provider.kid},
        )

        @require_tenant
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_tenant_valid_token(self, app_with_auth: Quart) -> None:
        """Test that require_tenant allows access with valid token."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read",
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_tenant
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200


class TestRequireScope:
    """Test the require_scope decorator."""

    @pytest.mark.asyncio
    async def test_require_scope_missing_token(self, app_with_auth: Quart) -> None:
        """Test that require_scope returns 403 when token is missing."""

        @require_scope("clusters:read")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_scope_insufficient_scope(self, app_with_auth: Quart) -> None:
        """Test that require_scope returns 403 when required scope is not present."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read",  # Only read access
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("*:write")  # Requires write access
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_scope_sufficient_scope(self, app_with_auth: Quart) -> None:
        """Test that require_scope allows access when scope is present."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read *:write",
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("*:read")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_scope_multiple_scopes(self, app_with_auth: Quart) -> None:
        """Test that require_scope checks all required scopes."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read *:write *:admin",
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        # Require multiple scopes
        @require_scope("*:read", "*:write")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_scope_missing_required_scope(self, app_with_auth: Quart) -> None:
        """Test that require_scope fails when one of multiple required scopes is missing."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read *:write",  # Missing *:admin
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        # Require multiple scopes
        @require_scope("*:read", "*:admin")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_scope_tenant_missing_returns_403(self, app_with_auth: Quart) -> None:
        """Test that require_scope still checks tenant first (tenant-first rule)."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        # Create a token without tenant claim
        now = int(time.time())
        payload = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "scope": "*:read *:write *:admin",
            # Intentionally missing 'tenant' claim
            "iat": now,
            "exp": now + 3600,
        }

        token = pyjwt.encode(
            payload,
            provider._private_key_pem,
            algorithm="RS256",
            headers={"kid": provider.kid},
        )

        @require_scope("*:read")
        async def handler() -> Any:
            # If we get here, tenant check was skipped (bad!)
            return jsonify({"error": "tenant check was skipped"}), 500

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                # Should return 403 for missing tenant, not 500
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_scope_wildcard_action_satisfies(self, app_with_auth: Quart) -> None:
        """Test that wildcard action scope (*:action) satisfies specific resource:action."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read",  # Wildcard action
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("clusters:read")  # Specific resource:action
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_scope_wildcard_action_does_not_satisfy_different_action(
        self, app_with_auth: Quart
    ) -> None:
        """Test that wildcard action (*:read) does NOT satisfy different action (*:write)."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read",  # Only read action
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("clusters:write")  # Requires write action
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_scope_wildcard_resource_satisfies(self, app_with_auth: Quart) -> None:
        """Test that wildcard resource scope (resource:*) satisfies specific resource:action."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "clusters:*",  # Wildcard resource
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("clusters:read", "clusters:write")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_scope_wildcard_all_satisfies_everything(
        self, app_with_auth: Quart
    ) -> None:
        """Test that wildcard all scope (*:*) satisfies any required scope."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:*",  # Wildcard all
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("clusters:read", "pods:write", "nodes:admin")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_scope_exact_match_still_works(self, app_with_auth: Quart) -> None:
        """Test that exact scope match still works (backward compatibility)."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "clusters:read clusters:write",  # Exact scopes
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("clusters:read")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_scope_exact_match_missing_fails(self, app_with_auth: Quart) -> None:
        """Test that missing exact scope match fails."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "clusters:read",  # Missing clusters:delete
        }

        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("clusters:delete")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 403


class TestCurrentClaims:
    """Test the current_claims helper."""

    @pytest.mark.asyncio
    async def test_current_claims_no_token(self, app_with_auth: Quart) -> None:
        """Test that current_claims returns None when no token is set."""
        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test"):
                claims = current_claims()
                assert claims is None

    @pytest.mark.asyncio
    async def test_current_claims_after_validation(self, app_with_auth: Quart) -> None:
        """Test that current_claims returns claims after token validation."""
        from hub_api.auth.middleware import _validate_and_store_token

        provider = app_with_auth.config["KEY_PROVIDER"]

        claims_dict = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read",
        }

        token = await encode_access_token(claims_dict, provider, ttl_hours=1)

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                # Validate the token
                valid = await _validate_and_store_token()
                assert valid is True

                # Get claims
                claims = current_claims()
                assert claims is not None
                assert claims["sub"] == "user123"
                assert claims["tenant"] == "tenant1"


class TestAudIssEnforcement:
    """Regression tests: _validate_and_store_token enforces aud/iss.

    The shared decoder (auth/jwt.py::decode_token) intentionally skips aud/iss
    verification by default because it backs multiple token types with
    different audiences (user/node tokens use PRODUCT_NAME; headend machine-JWTs
    use aud=="headend"). auth/middleware.py::_validate_and_store_token is the
    general user-JWT path behind @require_tenant/@require_scope/@require_admin,
    so it must reject a token minted for a different issuer/audience even
    though it verifies with the same signing key.
    """

    @pytest.mark.asyncio
    async def test_wrong_aud_rejected(self, app_with_auth: Quart) -> None:
        """A token whose aud != PRODUCT_NAME must be rejected by require_scope."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "headend",  # machine-JWT audience, not this app's PRODUCT_NAME
            "tenant": "tenant1",
            "scope": "*:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("*:read")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_wrong_iss_rejected(self, app_with_auth: Quart) -> None:
        """A token whose iss != PRODUCT_NAME must be rejected by require_tenant."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "some-other-issuer",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_tenant
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_correct_aud_iss_accepted(self, app_with_auth: Quart) -> None:
        """A token whose iss/aud both match PRODUCT_NAME is accepted."""
        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": "*:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        @require_scope("*:read")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context(
                "/test",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_machine_jwt_aud_headend_still_works_via_extract_machine_identity(
        self, app_with_auth: Quart
    ) -> None:
        """Machine-JWT path (_extract_machine_identity, aud='headend') is unaffected.

        This exercises the same shared decode_token() function through the
        machine-JWT extraction helper, confirming the new aud/iss enforcement
        in _validate_and_store_token did not change decode_token's default
        (opt-in) behavior used elsewhere.
        """
        from hub_api.auth.middleware import _extract_machine_identity

        provider = app_with_auth.config["KEY_PROVIDER"]

        claims = {
            "sub": "cluster:c1",
            "iss": "tobogganing",
            "aud": "headend",
            "tenant": "tenant1",
            "scope": "firewall:read",
        }
        token = await encode_access_token(claims, provider, ttl_hours=1)

        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test", method="GET"):
                decoded, error = await _extract_machine_identity(token, "firewall:read")
                assert error is None
                assert decoded is not None
                assert decoded["aud"] == "headend"


class TestSetClearAuthCookies:
    """Unit tests for set_auth_cookies/clear_auth_cookies (auth/middleware.py).

    Verifies the exact cookie names and flags the browser/portal flow relies
    on: access_token/refresh_token are HttpOnly, csrf_token is not (double-
    submit requires JS to read it), all three are SameSite=Strict.
    """

    @pytest.mark.asyncio
    async def test_set_auth_cookies_sets_all_three_with_expected_flags(
        self, app_with_auth: Quart
    ) -> None:
        """set_auth_cookies sets access_token/refresh_token (HttpOnly) + csrf_token (not)."""
        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test", method="POST"):
                response = jsonify({"ok": True})
                set_auth_cookies(response, "access-jwt-value", "refresh-opaque-value")

        set_cookie_headers = response.headers.get_all("Set-Cookie")
        by_name = {}
        for raw in set_cookie_headers:
            name = raw.split("=", 1)[0]
            by_name[name] = raw

        assert set(by_name.keys()) == {"access_token", "refresh_token", "csrf_token"}

        assert "access-jwt-value" in by_name["access_token"]
        assert "HttpOnly" in by_name["access_token"]
        assert "SameSite=Strict" in by_name["access_token"]
        assert "Path=/api/v1" in by_name["access_token"]

        assert "refresh-opaque-value" in by_name["refresh_token"]
        assert "HttpOnly" in by_name["refresh_token"]
        assert "SameSite=Strict" in by_name["refresh_token"]
        assert "Path=/api/v1/auth" in by_name["refresh_token"]

        # CSRF cookie must NOT be HttpOnly — portal JS reads it to echo back
        # in the X-CSRF-Token header (double-submit pattern).
        assert "HttpOnly" not in by_name["csrf_token"]
        assert "SameSite=Strict" in by_name["csrf_token"]

    @pytest.mark.asyncio
    async def test_clear_auth_cookies_expires_all_three(self, app_with_auth: Quart) -> None:
        """clear_auth_cookies sets Max-Age=0 on all three cookies (logout)."""
        async with app_with_auth.app_context():
            async with app_with_auth.test_request_context("/test", method="POST"):
                response = jsonify({})
                clear_auth_cookies(response)

        set_cookie_headers = response.headers.get_all("Set-Cookie")
        by_name = {}
        for raw in set_cookie_headers:
            name = raw.split("=", 1)[0]
            by_name[name] = raw

        assert set(by_name.keys()) == {"access_token", "refresh_token", "csrf_token"}
        for raw in by_name.values():
            assert "Max-Age=0" in raw


class TestCookieAuthAndCsrf:
    """Integration tests: cookie-based bearer fallback + double-submit CSRF.

    Registers real routes on app_with_auth and drives them through the Quart
    test client so cookies flow exactly as they would for a browser request
    (Cookie header in, Set-Cookie header out) — not just unit-level calls.
    """

    @staticmethod
    async def _make_access_token(app: Quart, scope: str = "*:read *:write") -> str:
        provider = app.config["KEY_PROVIDER"]
        claims = {
            "sub": "user123",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant1",
            "scope": scope,
        }
        token: str = await encode_access_token(claims, provider, ttl_hours=1)
        return token

    @pytest.mark.asyncio
    async def test_cookie_auth_get_succeeds_without_csrf(self, app_with_auth: Quart) -> None:
        """GET authenticated via cookie succeeds with no CSRF token at all.

        CSRF only guards state-changing methods (POST/PUT/PATCH/DELETE).
        """
        token = await self._make_access_token(app_with_auth)

        @app_with_auth.route("/cookie-get", methods=["GET"])
        @require_scope("*:read")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        client = app_with_auth.test_client()
        client.set_cookie("localhost", "access_token", token)

        resp = await client.get("/cookie-get")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cookie_auth_post_without_csrf_rejected(self, app_with_auth: Quart) -> None:
        """POST authenticated via cookie, with NO csrf_token cookie/header, is rejected 403."""
        token = await self._make_access_token(app_with_auth)

        @app_with_auth.route("/cookie-post", methods=["POST"])
        @require_scope("*:write")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        client = app_with_auth.test_client()
        client.set_cookie("localhost", "access_token", token)

        resp = await client.post("/cookie-post")
        assert resp.status_code == 403
        data = await resp.get_json()
        assert "CSRF" in data["error"]

    @pytest.mark.asyncio
    async def test_cookie_auth_post_with_mismatched_csrf_rejected(
        self, app_with_auth: Quart
    ) -> None:
        """POST authenticated via cookie with a header that doesn't match the CSRF cookie is rejected 403."""
        token = await self._make_access_token(app_with_auth)

        @app_with_auth.route("/cookie-post-mismatch", methods=["POST"])
        @require_scope("*:write")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        client = app_with_auth.test_client()
        client.set_cookie("localhost", "access_token", token)
        client.set_cookie("localhost", "csrf_token", "correct-csrf-value")

        resp = await client.post(
            "/cookie-post-mismatch",
            headers={"X-CSRF-Token": "wrong-csrf-value"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cookie_auth_post_with_valid_csrf_succeeds(self, app_with_auth: Quart) -> None:
        """POST authenticated via cookie with a matching X-CSRF-Token header succeeds 200."""
        token = await self._make_access_token(app_with_auth)

        @app_with_auth.route("/cookie-post-ok", methods=["POST"])
        @require_scope("*:write")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        client = app_with_auth.test_client()
        client.set_cookie("localhost", "access_token", token)
        client.set_cookie("localhost", "csrf_token", "matching-csrf-value")

        resp = await client.post(
            "/cookie-post-ok",
            headers={"X-CSRF-Token": "matching-csrf-value"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bearer_post_exempt_from_csrf(self, app_with_auth: Quart) -> None:
        """POST authenticated via Authorization: Bearer header needs no CSRF token at all.

        Confirms the machine-agent/CLI/service-to-service bearer path is
        completely unaffected by the new CSRF requirement, which only
        applies to cookie-sourced auth.
        """
        token = await self._make_access_token(app_with_auth)

        @app_with_auth.route("/bearer-post", methods=["POST"])
        @require_scope("*:write")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        client = app_with_auth.test_client()
        # No cookies at all — pure bearer-header auth.
        resp = await client.post(
            "/bearer-post",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bearer_header_takes_precedence_over_cookie(self, app_with_auth: Quart) -> None:
        """When both a bearer header and a cookie are present, the header wins (unchanged bearer path).

        A request carrying both is treated as bearer-authenticated (CSRF-exempt),
        matching _extract_token_from_header's header-first precedence.
        """
        token = await self._make_access_token(app_with_auth)

        @app_with_auth.route("/both-present", methods=["POST"])
        @require_scope("*:write")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        client = app_with_auth.test_client()
        # Cookie present but no matching csrf_token — if the cookie path were
        # used, this would 403. The bearer header must take priority instead.
        client.set_cookie("localhost", "access_token", token)
        resp = await client.post(
            "/both-present",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
