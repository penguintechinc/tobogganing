"""Additional coverage for api/auth_routes.py: missing-body and error branches.

test_portal_auth_api.py exercises the main login/refresh/logout success and
validation-error paths against a real DB; this file fills in the "missing
request body" branches, _mask_email edge cases, the logout-token-not-found
path, and the top-level exception handlers via a mocked AuthService.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.api.auth_routes import _mask_email


class TestMaskEmail:
    """Tests for the _mask_email() helper."""

    def test_empty_email_returns_stars(self) -> None:
        """Empty string returns '***'."""
        assert _mask_email("") == "***"

    def test_no_at_sign_returns_stars(self) -> None:
        """A value without '@' returns '***'."""
        assert _mask_email("not-an-email") == "***"

    def test_valid_email_masked(self) -> None:
        """Valid email is masked to first-char + stars + domain."""
        assert _mask_email("alice@example.com") == "a***@example.com"


@pytest.fixture
def auth_client(app: Quart) -> Quart:
    """Base test app fixture usable as a Quart test client for auth routes."""
    return app


@pytest.mark.asyncio
async def test_login_missing_body_returns_400(auth_client: Quart) -> None:
    """POST /auth/login with no JSON body returns 400."""
    client = auth_client.test_client()
    resp = await client.post("/api/v1/auth/login", data="not json")
    assert resp.status_code == 400
    data = await resp.get_json()
    assert data["error"] == "Missing request body"


@pytest.mark.asyncio
async def test_login_unexpected_exception_returns_401(auth_client: Quart) -> None:
    """POST /auth/login returns 401 when AuthService construction/call raises unexpectedly."""
    client = auth_client.test_client()
    with patch("hub_api.api.auth_routes.AuthService", side_effect=RuntimeError("boom")):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "a@example.com", "password": "pw"},
        )
    assert resp.status_code == 401
    data = await resp.get_json()
    assert data["error"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_refresh_missing_body_returns_400(auth_client: Quart) -> None:
    """POST /auth/refresh-token with no JSON body and no refresh_token cookie returns 400.

    Since the browser-cookie fallback was added (auth/middleware.py cookie
    auth), a missing/malformed body no longer short-circuits to a generic
    "Missing request body" — the handler also checks the refresh_token
    cookie, so the accurate error once both sources are empty is
    "Missing refresh_token".
    """
    client = auth_client.test_client()
    resp = await client.post("/api/v1/auth/refresh-token", data="not json")
    assert resp.status_code == 400
    data = await resp.get_json()
    assert data["error"] == "Missing refresh_token"


@pytest.mark.asyncio
async def test_refresh_unexpected_exception_returns_401(auth_client: Quart) -> None:
    """POST /auth/refresh-token returns 401 when AuthService raises unexpectedly."""
    client = auth_client.test_client()
    with patch("hub_api.api.auth_routes.AuthService", side_effect=RuntimeError("boom")):
        resp = await client.post("/api/v1/auth/refresh-token", json={"refresh_token": "sometoken"})
    assert resp.status_code == 401
    data = await resp.get_json()
    assert data["error"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_logout_missing_body_returns_400(auth_client: Quart) -> None:
    """POST /auth/logout with no JSON body and no refresh_token cookie returns 400.

    See test_refresh_missing_body_returns_400 for why the error message
    changed from "Missing request body" to "Missing refresh_token".
    """
    client = auth_client.test_client()
    resp = await client.post("/api/v1/auth/logout", data="not json")
    assert resp.status_code == 400
    data = await resp.get_json()
    assert data["error"] == "Missing refresh_token"


@pytest.mark.asyncio
async def test_logout_token_not_found_returns_204(auth_client: Quart, mock_db: MagicMock) -> None:
    """POST /auth/logout with a well-formed but unknown refresh_token is idempotent (204)."""
    from hub_api.tests.conftest import make_mock_rowset

    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
    mock_db.__call__ = MagicMock(return_value=query_proxy)

    with patch("hub_api.api.auth_routes.get_db", return_value=mock_db):
        client = auth_client.test_client()
        resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "unknown-token"})
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_logout_revoke_failure_still_returns_204(
    auth_client: Quart, mock_db: MagicMock
) -> None:
    """POST /auth/logout still returns 204 even if revoke_tokens() reports failure."""
    from hub_api.tests.conftest import make_mock_row, make_mock_rowset

    rt_row = make_mock_row({"user_id": "u1"})
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([rt_row]))
    mock_db.__call__ = MagicMock(return_value=query_proxy)

    with patch("hub_api.api.auth_routes.get_db", return_value=mock_db):
        with patch("hub_api.api.auth_routes.AuthService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.revoke_tokens = AsyncMock(return_value=False)
            mock_service_cls.return_value = mock_service

            client = auth_client.test_client()
            resp = await client.post(
                "/api/v1/auth/logout", json={"refresh_token": "valid-format-token"}
            )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_logout_unexpected_exception_still_returns_204(auth_client: Quart) -> None:
    """POST /auth/logout is idempotent even on unexpected internal errors (204)."""
    client = auth_client.test_client()
    with patch("hub_api.api.auth_routes.get_db", side_effect=RuntimeError("boom")):
        resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "sometoken"})
    assert resp.status_code == 204
