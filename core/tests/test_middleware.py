"""Tests for authentication middleware."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest
import jwt as pyjwt
from quart import Quart, jsonify

from core.auth.jwt import encode_access_token
from core.auth.middleware import current_claims, require_scope, require_tenant
from core.crypto import InAppKeyProvider, generate_rsa_key_pair


@pytest.fixture
def app_with_auth() -> Quart:
    """Create a test app with auth middleware configured."""
    from quart import Quart

    app = Quart(__name__)
    app.config["TESTING"] = True

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
        from core.auth.middleware import _validate_and_store_token

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
