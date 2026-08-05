"""Tests for SASE blocklist read-only API endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.modules.sase.security.blocklist.models import Verdict
from hub_api.modules.sase.security.blocklist.store import BlocklistStore
from hub_api.registry import ModuleContext


@pytest.fixture
def app_with_blocklist(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with SASE module and blocklist API registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with SASE module and blocklist blueprint registered.
    """
    # Set up key provider for token generation
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Set up in-memory cache for blocklist tests
    from hub_api.cache.client import CacheClient

    app.config["CACHE"] = CacheClient(host="127.0.0.1", port=6399)  # Unreachable; uses in-memory

    # Register SASE module
    from hub_api.modules.sase import module as sase_module

    sase_contract = sase_module()
    app.registry.register(sase_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def sase_read_token(app_with_blocklist: Quart) -> str:
    """Generate a valid JWT token with sase:read scope.

    Args:
        app_with_blocklist: App with key provider.

    Returns:
        Encoded JWT token with sase:read scope.
    """
    provider = app_with_blocklist.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "scope": "sase:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_check_ioc_flag_on_found(
    app_with_blocklist: Quart, sase_read_token: str
) -> None:
    """Test check endpoint returns verdict DTO when IOC found and flag ON.

    Args:
        app_with_blocklist: Test app.
        sase_read_token: Valid token with sase:read scope.
    """
    client = app_with_blocklist.test_client()

    # Seed a verdict into the store
    cache = app_with_blocklist.config["CACHE"]
    store = BlocklistStore(cache)
    verdict = Verdict(
        ioc_type="ip",
        value="1.2.3.4",
        severity="high",
        source="spamhaus",
        stix_id="indicator--test",
        first_seen=1000,
        expiry=None,
    )
    await store.put(verdict)

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get(
            "/api/v1/sase/blocklist/check?type=ip&value=1.2.3.4",
            headers={"Authorization": f"Bearer {sase_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()

        # Verify exact DTO field set (output-validation rule)
        assert set(data.keys()) == {"ioc_type", "value", "severity", "source", "stix_id", "first_seen", "expiry"}
        assert data["ioc_type"] == "ip"
        assert data["value"] == "1.2.3.4"
        assert data["severity"] == "high"
        assert data["source"] == "spamhaus"
        assert data["stix_id"] == "indicator--test"
        assert data["first_seen"] == 1000
        assert data["expiry"] is None


@pytest.mark.asyncio
async def test_check_ioc_not_found(
    app_with_blocklist: Quart, sase_read_token: str
) -> None:
    """Test check endpoint returns 404 when IOC not found.

    Args:
        app_with_blocklist: Test app.
        sase_read_token: Valid token with sase:read scope.
    """
    client = app_with_blocklist.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get(
            "/api/v1/sase/blocklist/check?type=ip&value=9.9.9.9",
            headers={"Authorization": f"Bearer {sase_read_token}"},
        )

        assert response.status_code == 404
        data = await response.get_json()
        assert "not found" in data["error"].lower()


@pytest.mark.asyncio
async def test_check_ioc_flag_off(app_with_blocklist: Quart, sase_read_token: str) -> None:
    """Test check endpoint returns 402 (payment required) when flag OFF.

    Args:
        app_with_blocklist: Test app.
        sase_read_token: Valid token with sase:read scope.
    """
    client = app_with_blocklist.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        response = await client.get(
            "/api/v1/sase/blocklist/check?type=ip&value=1.2.3.4",
            headers={"Authorization": f"Bearer {sase_read_token}"},
        )

        # require_feature returns 402 when flag is off
        assert response.status_code == 402


@pytest.mark.asyncio
async def test_check_ioc_invalid_type(
    app_with_blocklist: Quart, sase_read_token: str
) -> None:
    """Test check endpoint returns 400 for invalid IOC type.

    Args:
        app_with_blocklist: Test app.
        sase_read_token: Valid token with sase:read scope.
    """
    client = app_with_blocklist.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get(
            "/api/v1/sase/blocklist/check?type=invalid&value=1.2.3.4",
            headers={"Authorization": f"Bearer {sase_read_token}"},
        )

        assert response.status_code == 400
        data = await response.get_json()
        assert "invalid ioc type" in data["error"].lower()


@pytest.mark.asyncio
async def test_check_ioc_missing_params(
    app_with_blocklist: Quart, sase_read_token: str
) -> None:
    """Test check endpoint returns 400 for missing query parameters.

    Args:
        app_with_blocklist: Test app.
        sase_read_token: Valid token with sase:read scope.
    """
    client = app_with_blocklist.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Missing both type and value
        response = await client.get(
            "/api/v1/sase/blocklist/check",
            headers={"Authorization": f"Bearer {sase_read_token}"},
        )

        assert response.status_code == 400
        data = await response.get_json()
        assert "required query parameters" in data["error"].lower()

        # Missing value
        response = await client.get(
            "/api/v1/sase/blocklist/check?type=ip",
            headers={"Authorization": f"Bearer {sase_read_token}"},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
async def test_check_ioc_requires_auth(app_with_blocklist: Quart) -> None:
    """Test check endpoint requires authentication (403 without tenant).

    Args:
        app_with_blocklist: Test app.
    """
    client = app_with_blocklist.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Request without Authorization header
        response = await client.get(
            "/api/v1/sase/blocklist/check?type=ip&value=1.2.3.4",
        )

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_check_ioc_requires_scope(app_with_blocklist: Quart) -> None:
    """Test check endpoint requires sase:read scope.

    Args:
        app_with_blocklist: Test app.
    """
    client = app_with_blocklist.test_client()

    # Token without sase:read scope
    provider = app_with_blocklist.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "scope": "other:read",  # No sase:read scope
    }
    token_without_scope = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get(
            "/api/v1/sase/blocklist/check?type=ip&value=1.2.3.4",
            headers={"Authorization": f"Bearer {token_without_scope}"},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_check_ioc_all_types(
    app_with_blocklist: Quart, sase_read_token: str
) -> None:
    """Test check endpoint supports all IOC types.

    Args:
        app_with_blocklist: Test app.
        sase_read_token: Valid token with sase:read scope.
    """
    client = app_with_blocklist.test_client()
    cache = app_with_blocklist.config["CACHE"]
    store = BlocklistStore(cache)

    # Seed verdicts for all IOC types
    verdicts = [
        Verdict("ip", "1.2.3.4", "high", "test", "id1", 1000, None),
        Verdict("domain", "bad.com", "medium", "test", "id2", 1000, None),
        Verdict("url", "http://bad.com/path", "critical", "test", "id3", 1000, None),
        Verdict("hash", "a" * 64, "low", "test", "id4", 1000, None),
    ]

    for verdict in verdicts:
        await store.put(verdict)

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Test each type
        for verdict in verdicts:
            response = await client.get(
                f"/api/v1/sase/blocklist/check?type={verdict.ioc_type}&value={verdict.value}",
                headers={"Authorization": f"Bearer {sase_read_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert data["ioc_type"] == verdict.ioc_type
            assert data["value"] == verdict.value
            assert data["severity"] == verdict.severity
