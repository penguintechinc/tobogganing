"""Test authentication API endpoints with real database."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import pyotp
import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

from hub_api.config import Config
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.crypto.secrets import encrypt_secret
from hub_api.registry import ModuleContext


@pytest.fixture
def key_provider() -> InAppKeyProvider:
    """Provide a test key provider."""
    private_pem, public_pem = generate_rsa_key_pair()
    return InAppKeyProvider(private_pem, public_pem)


@pytest.fixture
def test_config() -> Config:
    """Provide test configuration."""
    return Config(
        db_type="sqlite",
        db_name=":memory:",
        product_name="test-app",
        jwt_expiration_hours=1,
    )


@pytest_asyncio.fixture
async def auth_app(
    real_dal: AsyncDB, test_config: Config, key_provider: InAppKeyProvider, monkeypatch: Any
) -> Quart:
    """Create an app with auth routes registered."""
    import hub_api.api.auth_routes
    import hub_api.api.portal_routes
    import hub_api.db
    from hub_api.app import create_app

    # Monkeypatch get_db everywhere it's imported
    monkeypatch.setattr(hub_api.db, "get_db", lambda: real_dal)
    monkeypatch.setattr(hub_api.api.auth_routes, "get_db", lambda: real_dal)

    app = create_app(test_config)
    app.config["KEY_PROVIDER"] = key_provider
    app.db = real_dal  # type: ignore[attr-defined]

    # Apply module registry context
    ctx = ModuleContext(config=test_config, db=real_dal, key_provider=key_provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest.mark.asyncio
async def test_login_success(
    auth_app: Quart, real_dal: AsyncDB, key_provider: InAppKeyProvider
) -> None:
    """Test successful login returns tokens."""
    # Create user
    user_id = str(uuid4())
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    await real_dal.users.async_insert(
        id=user_id,
        email="alice@example.com",
        username="alice",
        password_hash=password_hash,
        tenant=str(uuid4()),
        role="viewer",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Login
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": password},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 3600


@pytest.mark.asyncio
async def test_login_wrong_password(auth_app: Quart, real_dal: AsyncDB) -> None:
    """Test login with wrong password returns 401 uniform message."""
    # Create user
    user_id = str(uuid4())
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    await real_dal.users.async_insert(
        id=user_id,
        email="bob@example.com",
        username="bob",
        password_hash=password_hash,
        tenant=str(uuid4()),
        role="viewer",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Login with wrong password
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "wrong_password"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_unknown_user(auth_app: Quart) -> None:
    """Test login with unknown email returns 401 with same message as wrong password."""
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "any_password"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_mfa_required_no_token(auth_app: Quart, real_dal: AsyncDB) -> None:
    """Test login with MFA enabled returns 200 {mfa_required: true} without tokens."""
    # Create user with MFA enabled
    user_id = str(uuid4())
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    secret = pyotp.random_base32()
    encrypted_secret = encrypt_secret(secret)

    await real_dal.users.async_insert(
        id=user_id,
        email="charlie@example.com",
        username="charlie",
        password_hash=password_hash,
        tenant=str(uuid4()),
        role="viewer",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=encrypted_secret,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Login without MFA token
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "charlie@example.com", "password": password},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["mfa_required"] is True
    assert "access_token" not in data
    assert "refresh_token" not in data


@pytest.mark.asyncio
async def test_login_mfa_with_valid_token(auth_app: Quart, real_dal: AsyncDB) -> None:
    """Test login with MFA enabled and valid TOTP returns tokens."""
    # Create user with MFA enabled
    user_id = str(uuid4())
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    secret = pyotp.random_base32()
    encrypted_secret = encrypt_secret(secret)

    await real_dal.users.async_insert(
        id=user_id,
        email="diana@example.com",
        username="diana",
        password_hash=password_hash,
        tenant=str(uuid4()),
        role="viewer",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=encrypted_secret,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Generate valid TOTP token
    totp = pyotp.TOTP(secret)
    mfa_token = totp.now()

    # Login with MFA token
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "diana@example.com",
            "password": password,
            "mfa_token": mfa_token,
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_missing_fields(auth_app: Quart) -> None:
    """Test login with missing fields returns 400."""
    client = auth_app.test_client()

    # Missing password
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 400

    # Missing email
    response = await client.post(
        "/api/v1/auth/login",
        json={"password": "test_password"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_refresh_success(auth_app: Quart, real_dal: AsyncDB) -> None:
    """Test refresh endpoint returns new access token."""
    # Create user and login first
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    await real_dal.users.async_insert(
        id=user_id,
        email="eve@example.com",
        username="eve",
        password_hash=password_hash,
        tenant=tenant_id,
        role="viewer",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    client = auth_app.test_client()

    # Login to get refresh token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "eve@example.com", "password": password},
    )
    login_data = await login_response.get_json()
    refresh_token = login_data["refresh_token"]

    # Refresh
    response = await client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "access_token" in data
    # Refresh tokens are single-use and rotated on every call (security-review
    # finding HIGH-A) — the response must NEVER echo back the token the
    # caller presented.
    assert data["refresh_token"] != refresh_token
    assert data["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_token_reuse_rejected(auth_app: Quart, real_dal: AsyncDB) -> None:
    """Replaying an already-rotated refresh token is rejected as compromise.

    regression: security-review finding HIGH-A. Confirms (1) reusing a
    consumed refresh token is rejected, and (2) the replay is treated as a
    compromise signal that revokes the entire session family, not just the
    stale token — the newly-rotated (still valid) refresh token must also
    stop working.
    """
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    await real_dal.users.async_insert(
        id=user_id,
        email="grace@example.com",
        username="grace",
        password_hash=password_hash,
        tenant=tenant_id,
        role="viewer",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    client = auth_app.test_client()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "grace@example.com", "password": password},
    )
    login_data = await login_response.get_json()
    refresh_token_v1 = login_data["refresh_token"]

    # First refresh rotates v1 -> v2.
    first_refresh = await client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": refresh_token_v1},
    )
    assert first_refresh.status_code == 200
    refresh_token_v2 = (await first_refresh.get_json())["refresh_token"]
    assert refresh_token_v2 != refresh_token_v1

    # Replaying the now-consumed v1 token must be rejected.
    replay_response = await client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": refresh_token_v1},
    )
    assert replay_response.status_code == 401

    # The replay is treated as compromise: v2 (otherwise still valid) must
    # also have been revoked as part of the same-family cleanup.
    v2_after_replay = await client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": refresh_token_v2},
    )
    assert v2_after_replay.status_code == 401


@pytest.mark.asyncio
async def test_refresh_invalid_token(auth_app: Quart) -> None:
    """Test refresh with invalid token returns 401."""
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": "invalid_token"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_refresh_routes_do_not_collide(auth_app: Quart) -> None:
    """User refresh and machine refresh must resolve to distinct handlers.

    Regression test for a route-shadowing bug: auth_bp's user refresh and
    headend_bp's machine refresh were both registered at
    POST /api/v1/auth/refresh. Since auth_bp is registered first in
    create_app(), it silently shadowed headend_bp's machine handler for
    every request (see headend_routes.py:502 and
    docs/architecture/headend-machine-jwt-contract.md). User refresh now
    lives at /api/v1/auth/refresh-token so both paths route independently
    with no collision.
    """
    adapter = auth_app.url_map.bind("localhost")

    user_endpoint, _ = adapter.match("/api/v1/auth/refresh-token", method="POST")
    assert user_endpoint == "auth.refresh"

    machine_endpoint, _ = adapter.match("/api/v1/auth/refresh", method="POST")
    assert machine_endpoint == "headend.refresh_auth_token"

    # Exactly one rule per path — no duplicate registrations left behind.
    for path in ("/api/v1/auth/refresh-token", "/api/v1/auth/refresh"):
        rules = [r for r in auth_app.url_map.iter_rules() if r.rule == path]
        assert len(rules) == 1, f"expected exactly one rule for {path}, got {rules}"


@pytest.mark.asyncio
async def test_logout_success(auth_app: Quart, real_dal: AsyncDB) -> None:
    """Test logout revokes refresh token."""
    # Create user and login
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    await real_dal.users.async_insert(
        id=user_id,
        email="frank@example.com",
        username="frank",
        password_hash=password_hash,
        tenant=tenant_id,
        role="viewer",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    client = auth_app.test_client()

    # Login
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "frank@example.com", "password": password},
    )
    login_data = await login_response.get_json()
    refresh_token = login_data["refresh_token"]

    # Logout
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 204

    # Try to refresh with revoked token
    response = await client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_missing_token(auth_app: Quart) -> None:
    """Test logout with missing token returns 400."""
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/logout",
        json={},
    )

    assert response.status_code == 400


def _extract_set_cookie_names(response: Any) -> dict[str, str]:
    """Map cookie name -> raw Set-Cookie header value for the given response."""
    result = {}
    for raw in response.headers.get_all("Set-Cookie"):
        name = raw.split("=", 1)[0]
        result[name] = raw
    return result


async def _create_and_login(
    client: Any, real_dal: AsyncDB, email: str, password: str = "test_password_123"
) -> Any:
    """Create an active user and log in via the real /auth/login endpoint.

    Returns:
        The raw login Response (cookies land in the client's cookie jar).
    """
    await real_dal.users.async_insert(
        id=str(uuid4()),
        email=email,
        username=email.split("@")[0],
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        tenant=str(uuid4()),
        role="viewer",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


class TestBrowserCookieAuth:
    """Login/refresh/logout set/consume/clear HttpOnly cookies (Part 2).

    Exercises the real endpoints end-to-end (real DB via real_dal, real
    routing via the Quart test client + cookie jar) — not just the middleware
    unit tests in test_middleware.py.
    """

    @pytest.mark.asyncio
    async def test_login_sets_httponly_cookies_and_still_returns_json_body(
        self, auth_app: Quart, real_dal: AsyncDB
    ) -> None:
        """Login sets access_token/refresh_token/csrf_token cookies AND keeps the JSON body.

        The JSON body is unchanged so non-browser callers (mobile, CLI) that
        never look at cookies keep working exactly as before.
        """
        client = auth_app.test_client()
        response = await _create_and_login(client, real_dal, "cookie-login@example.com")

        assert response.status_code == 200
        data = await response.get_json()
        assert "access_token" in data and "refresh_token" in data

        cookies = _extract_set_cookie_names(response)
        assert set(cookies.keys()) == {"access_token", "refresh_token", "csrf_token"}
        assert "HttpOnly" in cookies["access_token"]
        assert "HttpOnly" in cookies["refresh_token"]
        assert "HttpOnly" not in cookies["csrf_token"]
        assert data["access_token"] in cookies["access_token"]
        assert data["refresh_token"] in cookies["refresh_token"]

    @pytest.mark.asyncio
    async def test_cookie_authenticated_request_succeeds_without_bearer_header(
        self, auth_app: Quart, real_dal: AsyncDB
    ) -> None:
        """After login, a request with NO Authorization header succeeds via the access_token cookie."""
        client = auth_app.test_client()
        await _create_and_login(client, real_dal, "cookie-get@example.com")

        # Cookie jar carries the access_token cookie automatically; no
        # Authorization header is sent at all.
        response = await client.get("/api/v1/portal/manifest")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_refresh_via_cookie_only_with_csrf_header_succeeds(
        self, auth_app: Quart, real_dal: AsyncDB
    ) -> None:
        """POST /refresh-token with NO body, relying on the refresh_token cookie + CSRF header."""
        client = auth_app.test_client()
        await _create_and_login(client, real_dal, "cookie-refresh@example.com")

        csrf_token = next(c.value for c in client.cookie_jar if c.name == "csrf_token")

        response = await client.post(
            "/api/v1/auth/refresh-token",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "access_token" in data and "refresh_token" in data
        # Cookies are rotated too.
        cookies = _extract_set_cookie_names(response)
        assert set(cookies.keys()) == {"access_token", "refresh_token", "csrf_token"}

    @pytest.mark.asyncio
    async def test_refresh_via_cookie_only_without_csrf_header_rejected(
        self, auth_app: Quart, real_dal: AsyncDB
    ) -> None:
        """POST /refresh-token with NO body and NO X-CSRF-Token header is rejected 403."""
        client = auth_app.test_client()
        await _create_and_login(client, real_dal, "cookie-refresh-nocsrf@example.com")

        response = await client.post("/api/v1/auth/refresh-token")

        assert response.status_code == 403
        data = await response.get_json()
        assert "CSRF" in data["error"]

    @pytest.mark.asyncio
    async def test_refresh_via_body_token_exempt_from_csrf(
        self, auth_app: Quart, real_dal: AsyncDB
    ) -> None:
        """A body-supplied refresh_token (non-browser caller) needs no CSRF header — unchanged behavior."""
        client = auth_app.test_client()
        login_response = await _create_and_login(client, real_dal, "body-refresh@example.com")
        refresh_token = (await login_response.get_json())["refresh_token"]

        # Deliberately do NOT send X-CSRF-Token — body-sourced tokens are exempt.
        response = await client.post(
            "/api/v1/auth/refresh-token",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_via_cookie_only_clears_cookies(
        self, auth_app: Quart, real_dal: AsyncDB
    ) -> None:
        """POST /logout with NO body, relying on the refresh_token cookie + CSRF header, clears all cookies."""
        client = auth_app.test_client()
        await _create_and_login(client, real_dal, "cookie-logout@example.com")

        csrf_token = next(c.value for c in client.cookie_jar if c.name == "csrf_token")

        response = await client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 204
        cookies = _extract_set_cookie_names(response)
        assert set(cookies.keys()) == {"access_token", "refresh_token", "csrf_token"}
        for raw in cookies.values():
            assert "Max-Age=0" in raw

    @pytest.mark.asyncio
    async def test_logout_via_cookie_only_without_csrf_header_rejected(
        self, auth_app: Quart, real_dal: AsyncDB
    ) -> None:
        """POST /logout with NO body and NO X-CSRF-Token header is rejected 403."""
        client = auth_app.test_client()
        await _create_and_login(client, real_dal, "cookie-logout-nocsrf@example.com")

        response = await client.post("/api/v1/auth/logout")

        assert response.status_code == 403
