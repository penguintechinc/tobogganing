"""Tests for SASE API crypto endpoints (certificates, JWT, WireGuard)."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.auth.jwt import decode_token, encode_access_token
from hub_api.core import CertificateManager
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.entitlements.gate import require_feature
from hub_api.modules.sdwan.certs import WireGuardKeyManager
from hub_api.registry import ModuleContext


@pytest.fixture
def cert_manager() -> CertificateManager:
    """Provide a CertificateManager instance for testing.

    Returns:
        Initialized CertificateManager (PKI-only).
    """
    cm = CertificateManager()
    return cm


@pytest.fixture
def wg_manager() -> WireGuardKeyManager:
    """Provide a WireGuardKeyManager instance for testing.

    Returns:
        Initialized WireGuardKeyManager.
    """
    wgm = WireGuardKeyManager()
    return wgm


@pytest.fixture
def app_with_sase(
    app: Quart, mock_db: MagicMock, cert_manager: CertificateManager, wg_manager: WireGuardKeyManager
) -> Quart:
    """Create a test app with SASE module registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.
        cert_manager: Certificate manager fixture.

    Returns:
        Quart app with SASE module, key provider, and managers configured.
    """
    # Set up key provider for token generation
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["CERT_MANAGER"] = cert_manager
    app.config["WIREGUARD_MANAGER"] = wg_manager

    # Mock cluster and client managers
    cluster_manager = MagicMock()
    cluster_manager.authenticate_cluster = MagicMock(return_value=None)
    cluster_manager.get_cluster = MagicMock(return_value=None)
    client_registry = MagicMock()
    client_registry.authenticate_client = MagicMock(return_value=None)
    client_registry.get_client = MagicMock(return_value=None)
    app.config["CLUSTER_MANAGER"] = cluster_manager
    app.config["CLIENT_REGISTRY"] = client_registry

    # Register SASE module via registry (combines module prefix + blueprint prefix)
    from hub_api.modules.sase import module as sase_module

    sase_contract = sase_module()
    app.registry.register(sase_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def valid_tenant_token(app_with_sase: Quart) -> str:
    """Generate a valid tenant JWT token for testing.

    Args:
        app_with_sase: App with key provider.

    Returns:
        Encoded JWT token with tenant claim.
    """
    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-node",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "scope": "*:*",
        "permissions": "headend proxy wireguard",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.fixture
def enrollment_token() -> str:
    """Provide a valid enrollment token.

    Returns:
        Enrollment token matching ENROLLMENT_BOOTSTRAP_TOKEN env var.
    """
    # Set the env var for this test
    token = "test-enrollment-token-12345"
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = token
    return token


# =============================================================================
# Certificate API Tests
# =============================================================================


@pytest.mark.asyncio
async def test_certificate_generation_requires_enrollment_token(
    app_with_sase: Quart,
) -> None:
    """Test that certificate generation requires enrollment token (401).

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Request without Authorization header
        response = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "client",
                "id": "node-1",
                "name": "test-node",
            },
        )

        assert response.status_code == 401
        data = await response.get_json()
        assert "enrollment token" in data["error"].lower()


@pytest.mark.asyncio
async def test_certificate_generation_with_invalid_token(
    app_with_sase: Quart,
) -> None:
    """Test that certificate generation rejects invalid enrollment token (401).

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "client",
                "id": "node-1",
                "name": "test-node",
            },
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_certificate_generation_client_success(
    app_with_sase: Quart, enrollment_token: str
) -> None:
    """Test successful client certificate generation with enrollment token.

    Args:
        app_with_sase: Test app.
        enrollment_token: Valid enrollment token.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "client",
                "id": "client-1",
                "name": "test-client",
                "client_type": "docker",
            },
            headers={"Authorization": f"Bearer {enrollment_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["type"] == "client"
        assert "certificates" in data
        assert "key" in data["certificates"]
        assert "cert" in data["certificates"]
        assert "ca" in data["certificates"]
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_certificate_generation_headend_success(
    app_with_sase: Quart, enrollment_token: str
) -> None:
    """Test successful headend certificate generation with SANs.

    Args:
        app_with_sase: Test app.
        enrollment_token: Valid enrollment token.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "headend",
                "id": "headend-1",
                "name": "test-headend",
                "san_names": ["headend-1.example.com", "headend-1.local"],
            },
            headers={"Authorization": f"Bearer {enrollment_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["type"] == "headend"
        assert "certificates" in data


@pytest.mark.asyncio
async def test_certificate_generation_invalid_type(
    app_with_sase: Quart, enrollment_token: str
) -> None:
    """Test certificate generation with invalid type (400).

    Args:
        app_with_sase: Test app.
        enrollment_token: Valid enrollment token.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "invalid_type",
                "id": "node-1",
                "name": "test-node",
            },
            headers={"Authorization": f"Bearer {enrollment_token}"},
        )

        assert response.status_code == 400
        data = await response.get_json()
        assert "Invalid certificate type" in data["error"]


@pytest.mark.asyncio
async def test_certificate_generation_flag_off(
    app_with_sase: Quart, enrollment_token: str
) -> None:
    """Test certificate generation returns 402 when flag is off.

    Args:
        app_with_sase: Test app.
        enrollment_token: Valid enrollment token.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        response = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "client",
                "id": "node-1",
                "name": "test-node",
            },
            headers={"Authorization": f"Bearer {enrollment_token}"},
        )

        assert response.status_code == 402


# =============================================================================
# JWT API Tests
# =============================================================================


@pytest.mark.asyncio
async def test_jwt_token_generation_missing_fields(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test JWT generation with missing required fields (400).

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Valid tenant token.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/jwt/token",
            json={
                "node_id": "node-1",
                # missing node_type and api_key
            },
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
async def test_jwt_token_generation_cluster_authenticated(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test JWT generation for cluster node (authentication success).

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Valid tenant token.
    """
    client = app_with_sase.test_client()

    # Mock successful cluster authentication
    mock_cluster = MagicMock()
    mock_cluster.id = "cluster-1"
    mock_cluster.region = "us-west"
    mock_cluster.datacenter = "us-west-1a"
    mock_cluster.tenant_id = "test-tenant"

    with patch(
        "hub_api.core.api.jwt.asyncio.to_thread"
    ) as mock_to_thread:
        mock_to_thread.return_value = mock_cluster

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.post(
                "/api/v1/jwt/token",
                json={
                    "node_id": "cluster-1",
                    "node_type": "kubernetes_node",
                    "api_key": "secret-key",
                },
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["expires_in"] == 3600
            assert data["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_jwt_token_generation_cluster_authentication_fails(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test JWT generation when cluster authentication fails (401).

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Valid tenant token.
    """
    client = app_with_sase.test_client()

    with patch(
        "hub_api.core.api.jwt.asyncio.to_thread"
    ) as mock_to_thread:
        mock_to_thread.return_value = None  # Authentication failed

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.post(
                "/api/v1/jwt/token",
                json={
                    "node_id": "cluster-1",
                    "node_type": "kubernetes_node",
                    "api_key": "invalid-key",
                },
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 401
            data = await response.get_json()
            assert "Authentication failed" in data["error"]


@pytest.mark.asyncio
async def test_jwt_public_key_endpoint(app_with_sase: Quart) -> None:
    """Test public key endpoint returns key + kid + algorithm.

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get("/api/v1/jwt/public-key")

        assert response.status_code == 200
        data = await response.get_json()
        assert "public_key" in data
        assert "kid" in data
        assert data["algorithm"] == "RS256"
        assert data["use"] == "sig"
        assert "meta" in data


@pytest.mark.asyncio
async def test_jwt_validate_token_success(
    app_with_sase: Quart,
) -> None:
    """Test token validation endpoint with valid token.

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-node",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "node_type": "kubernetes_node",
        "permissions": "headend proxy",
        "metadata": {"cluster_id": "cluster-1"},
    }
    valid_token = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["valid"] is True
        assert data["node_id"] == "test-node"
        assert data["node_type"] == "kubernetes_node"
        assert data["tenant"] == "test-tenant"


@pytest.mark.asyncio
async def test_jwt_validate_token_invalid(app_with_sase: Quart) -> None:
    """Test token validation endpoint with invalid token (401).

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": "Bearer invalid-token-format"},
        )

        assert response.status_code == 401
        data = await response.get_json()
        assert "Invalid or expired token" in data["error"]


@pytest.mark.asyncio
async def test_jwt_refresh_token_success(app_with_sase: Quart) -> None:
    """Test refresh token endpoint generates new access token.

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-node",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "token_type": "refresh",
    }
    refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/jwt/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "access_token" in data
        assert data["expires_in"] == 3600
        assert data["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_jwt_refresh_token_invalid(app_with_sase: Quart) -> None:
    """Test refresh token endpoint rejects invalid token (401).

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/jwt/refresh",
            json={"refresh_token": "invalid-token"},
        )

        assert response.status_code == 401


# =============================================================================
# WireGuard API Tests
# =============================================================================


@pytest.mark.asyncio
async def test_wireguard_keys_generation_requires_tenant(
    app_with_sase: Quart,
) -> None:
    """Test WireGuard key generation requires tenant claim (403).

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Request without Authorization header (no tenant)
        response = await client.post(
            "/api/v1/sdwan/wireguard/keys",
            json={
                "node_id": "node-1",
                "node_type": "client_docker",
                "api_key": "secret-key",
            },
        )

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_wireguard_keys_generation_cluster_success(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test successful WireGuard key generation for cluster node.

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Valid tenant token.
    """
    client = app_with_sase.test_client()

    mock_cluster = MagicMock()
    mock_cluster.id = "cluster-1"
    mock_cluster.tenant_id = "test-tenant"

    with patch(
        "hub_api.modules.sdwan.api.wireguard.asyncio.to_thread"
    ) as mock_to_thread:
        mock_to_thread.return_value = mock_cluster

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.post(
                "/api/v1/sdwan/wireguard/keys",
                json={
                    "node_id": "cluster-1",
                    "node_type": "kubernetes_node",
                    "api_key": "secret-key",
                },
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert data["node_id"] == "cluster-1"
            assert "wireguard" in data
            assert "private_key" in data["wireguard"]
            assert "public_key" in data["wireguard"]
            assert "ip_address" in data["wireguard"]
            assert "certificates" in data


@pytest.mark.asyncio
async def test_wireguard_peers_list(
    app_with_sase: Quart, valid_tenant_token: str, wg_manager: WireGuardKeyManager
) -> None:
    """Test getting list of WireGuard peers.

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Valid tenant token.
        wg_manager: WireGuard key manager with test peers.
    """
    client = app_with_sase.test_client()

    # Generate some peers first (for the test-tenant)
    await wg_manager.generate_wireguard_keys(
        "node-1", "client_docker", tenant_id="test-tenant"
    )
    await wg_manager.generate_wireguard_keys(
        "node-2", "client_native", tenant_id="test-tenant"
    )

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get(
            "/api/v1/sdwan/wireguard/peers",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert isinstance(data["peers"], list)
        assert data["total"] == 2
        # Each peer should have node_id, public_key, ip_address
        for peer in data["peers"]:
            assert "node_id" in peer
            assert "public_key" in peer
            assert "ip_address" in peer


@pytest.mark.asyncio
async def test_wireguard_keys_revocation_success(
    app_with_sase: Quart, valid_tenant_token: str, wg_manager: WireGuardKeyManager
) -> None:
    """Test revoking WireGuard keys for a node.

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Valid tenant token.
        wg_manager: WireGuard key manager with test peers.
    """
    client = app_with_sase.test_client()

    # Generate keys first (for test-tenant)
    await wg_manager.generate_wireguard_keys(
        "node-1", "client_docker", tenant_id="test-tenant"
    )

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.delete(
            "/api/v1/sdwan/wireguard/keys/node-1",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["revoked"] is True
        assert data["node_id"] == "node-1"


@pytest.mark.asyncio
async def test_wireguard_keys_revocation_not_found(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test revoking non-existent node returns 404.

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Valid tenant token.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.delete(
            "/api/v1/sdwan/wireguard/keys/nonexistent-node",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 404
        data = await response.get_json()
        assert "Node not found" in data["error"]


# =============================================================================
# Security Regression Tests
# =============================================================================


@pytest_asyncio.fixture
async def cross_tenant_token(app_with_sase: Quart) -> str:
    """Generate a JWT token for a different tenant.

    Args:
        app_with_sase: App with key provider.

    Returns:
        Encoded JWT token for 'other-tenant'.
    """
    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = {
        "sub": "other-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "other-tenant",
        "scope": "*:*",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def revoke_scope_token(app_with_sase: Quart) -> str:
    """Generate a token with jwt:revoke scope.

    Args:
        app_with_sase: App with key provider.

    Returns:
        Encoded JWT token with jwt:revoke scope.
    """
    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "scope": "jwt:revoke",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_wireguard_peers_tenant_isolation(
    app_with_sase: Quart,
    valid_tenant_token: str,
    cross_tenant_token: str,
    wg_manager: WireGuardKeyManager,
) -> None:
    """Test that peer list only returns caller's tenant peers.

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Token for test-tenant.
        cross_tenant_token: Token for other-tenant.
        wg_manager: WireGuard key manager with test peers.
    """
    client = app_with_sase.test_client()

    # Generate peers for both tenants
    await wg_manager.generate_wireguard_keys(
        "node-1", "client_docker", tenant_id="test-tenant"
    )
    await wg_manager.generate_wireguard_keys(
        "node-2", "client_native", tenant_id="other-tenant"
    )

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Test tenant sees only their peer
        response = await client.get(
            "/api/v1/sdwan/wireguard/peers",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["total"] == 1
        assert data["peers"][0]["node_id"] == "node-1"

        # Other tenant sees only their peer
        response = await client.get(
            "/api/v1/sdwan/wireguard/peers",
            headers={"Authorization": f"Bearer {cross_tenant_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["total"] == 1
        assert data["peers"][0]["node_id"] == "node-2"


@pytest.mark.asyncio
async def test_wireguard_revoke_cross_tenant_isolation(
    app_with_sase: Quart,
    valid_tenant_token: str,
    cross_tenant_token: str,
    wg_manager: WireGuardKeyManager,
) -> None:
    """Test that cross-tenant WireGuard revoke returns 404 (not found).

    Args:
        app_with_sase: Test app.
        valid_tenant_token: Token for test-tenant.
        cross_tenant_token: Token for other-tenant.
        wg_manager: WireGuard key manager with test peers.
    """
    client = app_with_sase.test_client()

    # Generate peer for test-tenant
    await wg_manager.generate_wireguard_keys(
        "node-1", "client_docker", tenant_id="test-tenant"
    )

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Cross-tenant revoke attempt → 404 (node not found from caller's view)
        response = await client.delete(
            "/api/v1/sdwan/wireguard/keys/node-1",
            headers={"Authorization": f"Bearer {cross_tenant_token}"},
        )
        assert response.status_code == 404

        # Verify peer still exists for original tenant
        response = await client.get(
            "/api/v1/sdwan/wireguard/peers",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["total"] == 1


@pytest.mark.asyncio
async def test_jwt_revoke_requires_tenant(app_with_sase: Quart) -> None:
    """Test JWT revoke without tenant claim returns 403.

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "some-node"},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_jwt_revoke_requires_scope(app_with_sase: Quart) -> None:
    """Test JWT revoke without jwt:revoke scope returns 403.

    Args:
        app_with_sase: Test app.
    """
    client = app_with_sase.test_client()

    # Create a token with only read scope (no jwt:revoke)
    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "test-tenant",
        "scope": "sase:read",  # No jwt:revoke scope
    }
    token_without_scope = await encode_access_token(claims, provider, ttl_hours=1)

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "some-node"},
            headers={"Authorization": f"Bearer {token_without_scope}"},
        )

        assert response.status_code == 403
