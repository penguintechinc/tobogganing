"""Test authentication API endpoints with real database."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import pytest
import pytest_asyncio
import pyotp
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
async def auth_app(real_dal: AsyncDB, test_config: Config, key_provider: InAppKeyProvider, monkeypatch: Any) -> Quart:
    """Create an app with auth routes registered."""
    from hub_api.app import create_app
    import hub_api.db
    import hub_api.api.auth_routes
    import hub_api.api.portal_routes

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
async def test_login_success(auth_app: Quart, real_dal: AsyncDB, key_provider: InAppKeyProvider) -> None:
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
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "access_token" in data
    assert data["refresh_token"] == refresh_token


@pytest.mark.asyncio
async def test_refresh_invalid_token(auth_app: Quart) -> None:
    """Test refresh with invalid token returns 401."""
    client = auth_app.test_client()
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid_token"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Invalid credentials"


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
        "/api/v1/auth/refresh",
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
