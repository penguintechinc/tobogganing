"""Tests for core/api/jwt.py blueprint routes: /token, /refresh, /validate, /public-key.

The /revoke route is covered separately in test_machine_jwt_issuance.py; this file
fills the coverage gap on the remaining core_jwt blueprint routes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair


@pytest.fixture
def app_with_jwt(app: Quart) -> Quart:
    """App with KEY_PROVIDER and cluster/client managers configured for jwt routes.

    Args:
        app: Base test app fixture.

    Returns:
        Quart app with managers wired up as AsyncMocks.
    """
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    cluster_manager = MagicMock()
    cluster_manager.authenticate_cluster = AsyncMock()
    client_registry = MagicMock()
    client_registry.authenticate_client = AsyncMock()
    app.config["CLUSTER_MANAGER"] = cluster_manager
    app.config["CLIENT_REGISTRY"] = client_registry

    return app


def _flag_on() -> Any:
    """Context manager patching the feature gate to always allow."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=True)


@pytest.mark.asyncio
async def test_token_missing_fields(app_with_jwt: Quart) -> None:
    """POST /jwt/token with missing fields returns 400."""
    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/token", json={"node_id": "x"})
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "Missing required fields" in data["error"]


@pytest.mark.asyncio
async def test_token_cluster_auth_success(app_with_jwt: Quart) -> None:
    """POST /jwt/token authenticates a cluster node and returns tokens."""
    from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster

    cluster = Cluster(
        id="c1",
        name="test",
        region="us",
        datacenter="dc1",
        headend_url="https://h.example.com",
        status="active",
        last_heartbeat=None,
        client_count=0,
        tenant="acme",
    )
    app_with_jwt.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = cluster

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "key"},
        )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_token_client_auth_success(app_with_jwt: Quart) -> None:
    """POST /jwt/token authenticates a client_docker node."""
    client_obj = MagicMock(id="cl1", tenant="acme", type="docker", cluster_id="c1")
    app_with_jwt.config["CLIENT_REGISTRY"].authenticate_client.return_value = client_obj

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "cl1", "node_type": "client_docker", "api_key": "key"},
        )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_token_no_manager_configured_unauthorized(app: Quart) -> None:
    """POST /jwt/token without CLUSTER_MANAGER/CLIENT_REGISTRY returns 401."""
    private_pem, public_pem = generate_rsa_key_pair()
    app.config["KEY_PROVIDER"] = InAppKeyProvider(private_pem, public_pem)

    client = app.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "key"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_authentication_failed(app_with_jwt: Quart) -> None:
    """POST /jwt/token with cluster auth returning None returns 401."""
    app_with_jwt.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = None

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "key"},
        )
    assert resp.status_code == 401
    data = await resp.get_json()
    assert data["error"] == "Authentication failed"


@pytest.mark.asyncio
async def test_token_cluster_auth_exception_logged_and_unauthorized(
    app_with_jwt: Quart,
) -> None:
    """POST /jwt/token with cluster_manager raising is caught and returns 401."""
    app_with_jwt.config["CLUSTER_MANAGER"].authenticate_cluster.side_effect = RuntimeError("boom")

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "key"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_no_key_provider(app: Quart) -> None:
    """POST /jwt/token with no KEY_PROVIDER configured returns 500."""
    client = app.test_client()
    with _flag_on():
        with patch.dict(app.config, {"KEY_PROVIDER": None}):
            resp = await client.post(
                "/api/v1/jwt/token",
                json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "key"},
            )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_token_cluster_id_mismatch(app_with_jwt: Quart) -> None:
    """POST /jwt/token with cluster.id not matching node_id returns 401."""
    from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster

    cluster = Cluster(
        id="different-id",
        name="test",
        region="us",
        datacenter="dc1",
        headend_url="https://h.example.com",
        status="active",
        last_heartbeat=None,
        client_count=0,
        tenant="acme",
    )
    app_with_jwt.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = cluster

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "key"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_client_auth_exception_caught(app_with_jwt: Quart) -> None:
    """POST /jwt/token with client_registry raising is caught and returns 401."""
    app_with_jwt.config["CLIENT_REGISTRY"].authenticate_client.side_effect = RuntimeError("boom")

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "cl1", "node_type": "client_docker", "api_key": "key"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_validate_no_key_provider(app: Quart) -> None:
    """POST /jwt/validate without KEY_PROVIDER configured returns 500."""
    client = app.test_client()
    with _flag_on():
        with patch.dict(app.config, {"KEY_PROVIDER": None}):
            resp = await client.post(
                "/api/v1/jwt/validate",
                headers={"Authorization": "Bearer sometoken"},
            )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_refresh_missing_token(app_with_jwt: Quart) -> None:
    """POST /jwt/refresh with missing refresh_token returns 400."""
    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/refresh", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_refresh_invalid_token(app_with_jwt: Quart) -> None:
    """POST /jwt/refresh with an undecodable token returns 401."""
    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/refresh", json={"refresh_token": "not-a-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_wrong_token_type(app_with_jwt: Quart) -> None:
    """POST /jwt/refresh with an access token (not refresh) returns 401."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
    }
    access_token = await encode_access_token(claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
    data = await resp.get_json()
    assert data["error"] == "Invalid token type"


@pytest.mark.asyncio
async def test_refresh_success(app_with_jwt: Quart) -> None:
    """POST /jwt/refresh with a valid refresh token returns new access token."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "token_type": "refresh",
    }
    refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = await resp.get_json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_validate_missing_auth_header(app_with_jwt: Quart) -> None:
    """POST /jwt/validate with no Authorization header returns 401."""
    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post("/api/v1/jwt/validate")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_validate_invalid_token(app_with_jwt: Quart) -> None:
    """POST /jwt/validate with an invalid token returns 401."""
    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": "Bearer garbage"},
        )
    assert resp.status_code == 401
    data = await resp.get_json()
    assert data["error"] == "Invalid or expired token"


@pytest.mark.asyncio
async def test_validate_success(app_with_jwt: Quart) -> None:
    """POST /jwt/validate with a valid token returns claims."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "node_type": "kubernetes_node",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["valid"] is True
    assert data["node_id"] == "cluster:c1"


@pytest.mark.asyncio
async def test_validate_revoked_token(app_with_jwt: Quart) -> None:
    """POST /jwt/validate with a jti present in the in-memory revocation set returns 401."""
    import hub_api.core.api.jwt as jwt_module

    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "jti": "revoked-jti-1",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    jwt_module._REVOKED_TOKENS.add("revoked-jti-1")
    try:
        client = app_with_jwt.test_client()
        with _flag_on():
            resp = await client.post(
                "/api/v1/jwt/validate",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 401
        data = await resp.get_json()
        assert data["error"] == "Token has been revoked"
    finally:
        jwt_module._REVOKED_TOKENS.discard("revoked-jti-1")


@pytest.mark.asyncio
async def test_refresh_no_key_provider(app: Quart) -> None:
    """POST /jwt/refresh without KEY_PROVIDER configured returns 500."""
    client = app.test_client()
    with _flag_on():
        with patch.dict(app.config, {"KEY_PROVIDER": None}):
            resp = await client.post("/api/v1/jwt/refresh", json={"refresh_token": "sometoken"})
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_validate_non_bearer_auth_header(app_with_jwt: Quart) -> None:
    """POST /jwt/validate with a non-Bearer Authorization header returns 401."""
    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": "Basic abc123"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_token_unexpected_exception_returns_500(
    app_with_jwt: Quart,
) -> None:
    """POST /jwt/token returns 500 when an unexpected exception escapes the try block."""
    with (
        _flag_on(),
        patch("hub_api.core.api.jwt.build_machine_claims", side_effect=RuntimeError("boom")),
    ):
        from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster

        cluster = Cluster(
            id="c1",
            name="test",
            region="us",
            datacenter="dc1",
            headend_url="https://h.example.com",
            status="active",
            last_heartbeat=None,
            client_count=0,
            tenant="acme",
        )
        app_with_jwt.config["CLUSTER_MANAGER"].authenticate_cluster.return_value = cluster

        client = app_with_jwt.test_client()
        resp = await client.post(
            "/api/v1/jwt/token",
            json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "key"},
        )
    assert resp.status_code == 500
    data = await resp.get_json()
    assert data["error"] == "Internal server error"


@pytest.mark.asyncio
async def test_refresh_unexpected_exception_returns_500(app_with_jwt: Quart) -> None:
    """POST /jwt/refresh returns 500 when decode_token raises unexpectedly."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "cluster:c1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "token_type": "refresh",
    }
    refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

    with _flag_on(), patch("hub_api.core.api.jwt.decode_token", side_effect=RuntimeError("boom")):
        client = app_with_jwt.test_client()
        resp = await client.post("/api/v1/jwt/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_validate_unexpected_exception_returns_500(app_with_jwt: Quart) -> None:
    """POST /jwt/validate returns 500 when decode_token raises unexpectedly."""
    with _flag_on(), patch("hub_api.core.api.jwt.decode_token", side_effect=RuntimeError("boom")):
        client = app_with_jwt.test_client()
        resp = await client.post(
            "/api/v1/jwt/validate",
            headers={"Authorization": "Bearer sometoken"},
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_revoke_cluster_manager_exception_swallowed(app_with_jwt: Quart) -> None:
    """POST /jwt/revoke swallows cluster_manager.get_cluster exceptions and still succeeds."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "scope": "jwt:revoke",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    app_with_jwt.config["CLUSTER_MANAGER"].get_cluster = AsyncMock(side_effect=RuntimeError("boom"))
    app_with_jwt.config["CLIENT_REGISTRY"].get_client = AsyncMock(side_effect=RuntimeError("boom"))

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "c1"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["revoked"] is True


@pytest.mark.asyncio
async def test_revoke_unexpected_exception_returns_500(app_with_jwt: Quart) -> None:
    """POST /jwt/revoke returns 500 when current_claims raises unexpectedly."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "scope": "jwt:revoke",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    with _flag_on(), patch("hub_api.core.api.jwt.current_claims", side_effect=RuntimeError("boom")):
        client = app_with_jwt.test_client()
        resp = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "c1"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_public_key_unexpected_exception_returns_500(app_with_jwt: Quart) -> None:
    """GET /jwt/public-key returns 500 when reading the provider's public_pem raises."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    with (
        _flag_on(),
        patch.object(
            type(provider),
            "public_pem",
            new_callable=lambda: property(lambda self: (_ for _ in ()).throw(RuntimeError("boom"))),
        ),
    ):
        client = app_with_jwt.test_client()
        resp = await client.get("/api/v1/jwt/public-key")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_public_key_success(app_with_jwt: Quart) -> None:
    """GET /jwt/public-key returns the configured provider's public PEM."""
    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.get("/api/v1/jwt/public-key")
    assert resp.status_code == 200
    data = await resp.get_json()
    assert "public_key" in data
    assert data["algorithm"] == "RS256"
    assert data["kid"] == app_with_jwt.config["KEY_PROVIDER"].kid


@pytest.mark.asyncio
async def test_public_key_no_provider(app: Quart) -> None:
    """GET /jwt/public-key without KEY_PROVIDER returns 500."""
    client = app.test_client()
    with _flag_on():
        with patch.dict(app.config, {"KEY_PROVIDER": None}):
            resp = await client.get("/api/v1/jwt/public-key")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_revoke_missing_node_id(app_with_jwt: Quart) -> None:
    """POST /jwt/revoke with missing node_id returns 400."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "scope": "jwt:revoke",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/revoke",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_revoke_no_node_tenant_found_allows(app_with_jwt: Quart) -> None:
    """POST /jwt/revoke succeeds when neither manager resolves the node's tenant."""
    provider = app_with_jwt.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "scope": "jwt:revoke",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    app_with_jwt.config["CLUSTER_MANAGER"].get_cluster = AsyncMock(return_value=None)
    app_with_jwt.config["CLIENT_REGISTRY"].get_client = AsyncMock(return_value=None)

    client = app_with_jwt.test_client()
    with _flag_on():
        resp = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "unknown-node"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["revoked"] is True
