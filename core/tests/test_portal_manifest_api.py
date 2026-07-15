"""Test portal manifest endpoint with real database."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import bcrypt
import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

from core.auth.jwt import encode_access_token
from core.config import Config
from core.crypto import InAppKeyProvider, generate_rsa_key_pair
from core.registry import ModuleContext


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
async def manifest_app(
    real_dal: AsyncDB,
    test_config: Config,
    key_provider: InAppKeyProvider,
) -> Quart:
    """Create an app with portal manifest routes registered."""
    from core.app import create_app
    import core.db

    # Patch init_dal and get_db
    from unittest.mock import patch
    with patch("core.db.init_dal"), patch.object(core.db, "get_db", return_value=real_dal):
        app = create_app(test_config)
        app.config["KEY_PROVIDER"] = key_provider
        app.db = real_dal  # type: ignore[attr-defined]

        # Apply module registry context
        ctx = ModuleContext(config=test_config, db=real_dal, key_provider=key_provider)
        app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def valid_token(manifest_app: Quart, key_provider: InAppKeyProvider) -> str:
    """Generate a valid JWT token with tenant and role."""
    tenant_id = str(uuid4())
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": tenant_id,
        "scope": "*:read",
        "role": ["admin"],
    }
    token = await encode_access_token(claims, key_provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def viewer_token(manifest_app: Quart, key_provider: InAppKeyProvider) -> str:
    """Generate a valid JWT token with viewer role."""
    tenant_id = str(uuid4())
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": tenant_id,
        "scope": "*:read",
        "role": ["viewer"],
    }
    token = await encode_access_token(claims, key_provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_manifest_without_token(manifest_app: Quart) -> None:
    """Test manifest endpoint without token returns 403."""
    client = manifest_app.test_client()
    response = await client.get("/api/v1/portal/manifest")

    assert response.status_code == 403
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_manifest_with_token(manifest_app: Quart, valid_token: str) -> None:
    """Test manifest endpoint with valid token returns modules."""
    client = manifest_app.test_client()
    response = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "modules" in data
    assert "role" in data
    assert "meta" in data
    assert data["role"] == "admin"
    assert isinstance(data["modules"], list)


@pytest.mark.asyncio
async def test_manifest_modules_structure(manifest_app: Quart, valid_token: str) -> None:
    """Test that each module in manifest has required structure."""
    client = manifest_app.test_client()
    response = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()

    # Check structure
    assert isinstance(data["modules"], list)
    for module in data["modules"]:
        assert "name" in module
        assert "nav" in module
        assert "flags" in module
        assert isinstance(module["nav"], list)
        assert isinstance(module["flags"], dict)

        # Check nav entries
        for nav_entry in module["nav"]:
            assert "label" in nav_entry
            assert "path" in nav_entry
            assert "icon" in nav_entry


@pytest.mark.asyncio
async def test_manifest_flags_structure(manifest_app: Quart, valid_token: str) -> None:
    """Test that flags are evaluated and present in manifest."""
    client = manifest_app.test_client()
    response = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()

    # Check flags are present and boolean
    for module in data["modules"]:
        for flag_key, flag_value in module["flags"].items():
            assert isinstance(flag_key, str)
            assert isinstance(flag_value, bool)


@pytest.mark.asyncio
async def test_manifest_role_from_claims(manifest_app: Quart, viewer_token: str) -> None:
    """Test that role is extracted from JWT claims."""
    client = manifest_app.test_client()
    response = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_manifest_default_role_fallback(manifest_app: Quart, key_provider: InAppKeyProvider) -> None:
    """Test that role defaults to 'viewer' if not in claims."""
    tenant_id = str(uuid4())
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": tenant_id,
        "scope": "*:read",
        # No role claim
    }
    token = await encode_access_token(claims, key_provider, ttl_hours=1)

    client = manifest_app.test_client()
    response = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_manifest_invalid_token(manifest_app: Quart) -> None:
    """Test manifest with invalid token returns 403."""
    client = manifest_app.test_client()
    response = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": "Bearer invalid_token"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_manifest_meta_timestamp(manifest_app: Quart, valid_token: str) -> None:
    """Test that manifest includes version and timestamp metadata."""
    client = manifest_app.test_client()
    response = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["meta"]["version"] == 1
    assert "timestamp" in data["meta"]
