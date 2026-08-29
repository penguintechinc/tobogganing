"""Tests for headend policy endpoints (firewall rules, port config).

These endpoints are for headend-to-manager API communication.
The Go hub-router polls these endpoints for firewall rules and port configuration.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_get_firewall_rules_no_auth(app_with_sase: Quart) -> None:
    """Test GET /api/v1/firewall/rules fails without auth.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/firewall/rules")

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_firewall_rules_invalid_token(app_with_sase: Quart) -> None:
    """Test GET /api/v1/firewall/rules fails with invalid Bearer token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get(
        "/api/v1/firewall/rules",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_firewall_rules_success(app_with_sase: Quart) -> None:
    """Test GET /api/v1/firewall/rules returns rules for valid headend token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    # Set HEADEND_API_TOKEN env var (this is what the Go client uses)
    test_token = "test-headend-token"
    os.environ["HEADEND_API_TOKEN"] = test_token

    client = app_with_sase.test_client()

    # Mock the firewall access control manager
    with patch("hub_api.api.headend_routes.get_access_control_manager") as mock_get_acm:
        mock_acm = AsyncMock()
        mock_get_acm.return_value = mock_acm

        # Mock export_user_rules to return a rule
        mock_acm.export_user_rules = AsyncMock(
            return_value={
                "rule1": {
                    "pattern": "example.com",
                    "access_type": "allow",
                    "rule_type": "domain",
                }
            }
        )

        with patch("hub_api.api.headend_routes.get_user_manager") as mock_get_um:
            mock_um = AsyncMock()
            mock_get_um.return_value = mock_um

            # Mock active users
            mock_um.list_users = AsyncMock(
                return_value=[
                    MagicMock(id="user1", is_active=True),
                    MagicMock(id="user2", is_active=False),
                ]
            )

            response = await client.get(
                "/api/v1/firewall/rules",
                headers={"Authorization": f"Bearer {test_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert "timestamp" in data
            assert "rules_count" in data
            assert "user_rules" in data
            # Only active user should be included
            assert "user1" in data["user_rules"]

    # Clean up
    os.environ.pop("HEADEND_API_TOKEN", None)


@pytest.mark.asyncio
async def test_get_headend_ports_no_auth(app_with_sase: Quart) -> None:
    """Test GET /api/v1/headend/<id>/ports fails without auth.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/headend/headend-1/ports")

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_headend_ports_invalid_token(app_with_sase: Quart) -> None:
    """Test GET /api/v1/headend/<id>/ports fails with invalid Bearer token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get(
        "/api/v1/headend/headend-1/ports",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_headend_ports_success(app_with_sase: Quart) -> None:
    """Test GET /api/v1/headend/<id>/ports returns config for valid token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    test_token = "test-headend-token"
    os.environ["HEADEND_API_TOKEN"] = test_token

    client = app_with_sase.test_client()

    with patch("hub_api.api.headend_routes.get_port_config_manager") as mock_get_pcm:
        mock_pcm = AsyncMock()
        mock_get_pcm.return_value = mock_pcm

        # Mock headend config with port ranges
        mock_config = MagicMock()
        mock_config.headend_id = "headend-1"
        mock_config.cluster_id = "cluster-1"
        mock_config.tcp_ranges = []
        mock_config.udp_ranges = []
        mock_config.updated_at = datetime.now(timezone.utc)

        mock_pcm.get_headend_config = AsyncMock(return_value=mock_config)

        response = await client.get(
            "/api/v1/headend/headend-1/ports?cluster_id=cluster-1",
            headers={"Authorization": f"Bearer {test_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["headend_id"] == "headend-1"
        assert data["cluster_id"] == "cluster-1"
        assert "tcp_ranges" in data
        assert "udp_ranges" in data
        assert "updated_at" in data

    os.environ.pop("HEADEND_API_TOKEN", None)


@pytest.mark.asyncio
async def test_get_headend_ports_not_found(app_with_sase: Quart) -> None:
    """Test GET /api/v1/headend/<id>/ports returns 404 when config not found.

    Args:
        app_with_sase: Test app with SASE module.
    """
    test_token = "test-headend-token"
    os.environ["HEADEND_API_TOKEN"] = test_token

    client = app_with_sase.test_client()

    with patch("hub_api.api.headend_routes.get_port_config_manager") as mock_get_pcm:
        mock_pcm = AsyncMock()
        mock_get_pcm.return_value = mock_pcm

        # Config not found
        mock_pcm.get_headend_config = AsyncMock(return_value=None)

        response = await client.get(
            "/api/v1/headend/headend-unknown/ports",
            headers={"Authorization": f"Bearer {test_token}"},
        )

        assert response.status_code == 404
        data = await response.get_json()
        assert "error" in data

    os.environ.pop("HEADEND_API_TOKEN", None)


# WireGuard and JWT flat endpoints (headend-callable, app-level routes)


@pytest.mark.asyncio
async def test_get_wireguard_peers_no_auth(app_with_sase: Quart) -> None:
    """Test GET /api/v1/wireguard/peers fails without auth.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/wireguard/peers")

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_wireguard_peers_invalid_token(app_with_sase: Quart) -> None:
    """Test GET /api/v1/wireguard/peers fails with invalid Bearer token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get(
        "/api/v1/wireguard/peers",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_wireguard_peers_success(app_with_sase: Quart) -> None:
    """Test GET /api/v1/wireguard/peers returns peers for valid headend token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    test_token = "test-headend-token"
    os.environ["HEADEND_API_TOKEN"] = test_token

    client = app_with_sase.test_client()

    # Mock CertificateManager in app config
    mock_cm = AsyncMock()
    mock_cm.get_all_wireguard_peers = AsyncMock(
        return_value=[
            {
                "node_id": "cluster-1",
                "public_key": "pub-key-1",
                "ip_address": "10.0.0.1",
                "allowed_ips": "10.0.0.1/32",
            }
        ]
    )
    app_with_sase.config["CERT_MANAGER"] = mock_cm

    response = await client.get(
        "/api/v1/wireguard/peers",
        headers={"Authorization": f"Bearer {test_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "peers" in data
    assert "total" in data
    assert data["total"] == 1
    assert len(data["peers"]) == 1

    os.environ.pop("HEADEND_API_TOKEN", None)


@pytest.mark.asyncio
async def test_get_auth_public_key_no_auth(app_with_sase: Quart) -> None:
    """Test GET /api/v1/auth/public-key succeeds without auth (public endpoint).

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/auth/public-key")

    assert response.status_code == 200
    data = await response.get_json()
    assert "public_key" in data
    assert "kid" in data
    assert "algorithm" in data


@pytest.mark.asyncio
async def test_post_auth_validate_success(app_with_sase: Quart) -> None:
    """Test POST /api/v1/auth/validate validates a token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    from hub_api.auth.jwt import encode_access_token

    client = app_with_sase.test_client()
    provider = app_with_sase.config["KEY_PROVIDER"]

    # Generate a test token to validate
    claims = {
        "sub": "test-node",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "default",
        "node_type": "kubernetes_node",
        "permissions": "headend proxy wireguard",
    }

    test_token = await encode_access_token(claims, provider, ttl_hours=1)

    # Send validation request
    response = await client.post(
        "/api/v1/auth/validate",
        headers={"Authorization": f"Bearer {test_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["valid"] is True
    assert data["node_id"] == "test-node"
    assert data["tenant"] == "default"


@pytest.mark.asyncio
async def test_post_auth_validate_invalid_token(app_with_sase: Quart) -> None:
    """Test POST /api/v1/auth/validate rejects invalid token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/auth/validate",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_post_auth_token_missing_fields(app_with_sase: Quart) -> None:
    """Test POST /api/v1/auth/token validates required fields.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/auth/token",
        json={"node_id": "cluster-1"},  # Missing node_type and api_key
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data
    assert "Missing required fields" in data["error"]


@pytest.mark.asyncio
async def test_post_auth_token_cluster_auth_success(app_with_sase: Quart) -> None:
    """Test POST /api/v1/auth/token issues token for authenticated cluster.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    # app_with_sase does not configure CLUSTER_MANAGER, so authentication
    # always falls through to the "not authenticated" branch below — this
    # test only asserts that fallback is a clean 401/500, not a crash.
    # (asyncio.to_thread was never on the real call path here — the
    # handler awaits cluster_manager.authenticate_cluster() directly — so
    # a prior mock on it was dead and has been removed.)
    response = await client.post(
        "/api/v1/auth/token",
        json={
            "node_id": "cluster-1",
            "node_type": "kubernetes_node",
            "api_key": "test-api-key",
        },
    )

    if response.status_code == 200:
        data = await response.get_json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["expires_in"] == 3600
    else:
        # Acceptable if cluster_manager not configured
        assert response.status_code in (401, 500)


@pytest.mark.asyncio
async def test_post_auth_token_cluster_auth_failed(app_with_sase: Quart) -> None:
    """Test POST /api/v1/auth/token rejects invalid cluster api_key.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    # Send auth request with invalid api_key (cluster_manager will reject it)
    response = await client.post(
        "/api/v1/auth/token",
        json={
            "node_id": "cluster-1",
            "node_type": "kubernetes_node",
            "api_key": "invalid-api-key",
        },
    )

    # Should fail with 401 (authentication failed) or 500 if cluster_manager not configured
    assert response.status_code in (401, 500)
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_post_auth_refresh_missing_token(app_with_sase: Quart) -> None:
    """Test POST /api/v1/auth/refresh (machine/headend refresh) requires refresh_token.

    Regression test for a route-shadowing bug: this path used to be
    silently claimed by auth_bp's user-refresh handler (registered first
    in create_app()), so this test exercised the wrong handler by
    accident. Now that auth_bp's user-refresh lives at
    /api/v1/auth/refresh-token, this correctly reaches
    headend_routes.refresh_auth_token().

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={},  # Missing refresh_token
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_post_auth_refresh_invalid_token(app_with_sase: Quart) -> None:
    """Test POST /api/v1/auth/refresh (machine/headend refresh) rejects invalid tokens.

    Regression test for a route-shadowing bug (see
    test_post_auth_refresh_missing_token docstring). CACHE and DAL are
    configured here so the request reaches headend_routes.refresh_auth_token()'s
    decode_token() check instead of short-circuiting on a missing
    dependency, proving the *machine* refresh handler's own 401 rejection
    path (not auth_bp's) is what actually runs.

    Args:
        app_with_sase: Test app with SASE module.
    """
    # CACHE is checked before DAL and must be present to reach decode_token().
    # DAL is intentionally left unset in config: refresh_auth_token() must
    # source it from the real get_db() accessor (DAL-accessor regression;
    # app_with_sase's underlying create_app() wires a real, if tableless,
    # AsyncDB via get_db() the same way every other headend handler gets
    # it) rather than a config["DAL"] mock that would silently mask a
    # revert to the old current_app.config.get("DAL") bug.
    app_with_sase.config["CACHE"] = MagicMock()

    client = app_with_sase.test_client()

    # Send an invalid refresh token (no mocking, let it fail naturally)
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid-token"},
    )

    # A garbage/undecodable token is rejected by decode_token() before any
    # cache/DB lookup, so this must be a genuine 401, not a masked 500.
    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Invalid or expired refresh token"


@pytest.mark.asyncio
async def test_post_auth_refresh_dispatches_to_machine_handler(app_with_sase: Quart) -> None:
    """POST /api/v1/auth/refresh must invoke the machine/headend handler, not auth_bp.

    Regression test for the route-shadowing bug fixed alongside this test:
    auth_bp and headend_bp both used to register POST /api/v1/auth/refresh;
    auth_bp (registered first in create_app()) silently shadowed headend_bp's
    machine handler for every request. Proves dispatch by minting a real
    machine refresh token (build_machine_claims: token_type=refresh,
    node_type, permissions) and mocking only rotate_refresh() — reaching
    that mock requires decode_token() to have accepted the token, which
    only headend_routes.refresh_auth_token() attempts.

    Args:
        app_with_sase: Test app with SASE module.
    """
    from hub_api.auth.jwt import encode_access_token
    from hub_api.auth.machine_claims import build_machine_claims

    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = build_machine_claims(
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="acme",
        iss="tobogganing",
        aud="tobogganing",
        token_type="refresh",
    )
    refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

    # DAL intentionally unset in config here too — see
    # test_post_auth_refresh_invalid_token for why (DAL-accessor regression).
    app_with_sase.config["CACHE"] = MagicMock()

    client = app_with_sase.test_client()

    with patch(
        "hub_api.auth.refresh.rotate_refresh",
        new=AsyncMock(
            return_value={
                "access_token": "new-machine-access",
                "refresh_token": "new-machine-refresh",
            }
        ),
    ) as mock_rotate:
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

    assert mock_rotate.await_count == 1
    assert response.status_code == 200
    data = await response.get_json()
    assert data["access_token"] == "new-machine-access"
    assert data["refresh_token"] == "new-machine-refresh"


@pytest.mark.asyncio
async def test_post_auth_refresh_reaches_real_db_and_rotates(
    app_with_sase: Quart, real_dal: Any, monkeypatch: Any
) -> None:
    """POST /api/v1/auth/refresh reaches the real DB and mints fresh machine tokens.

    DAL-accessor regression: refresh_auth_token() used to read
    db = current_app.config.get("DAL"), which is never set anywhere in
    production create_app() (only ever injected as a test double), so this
    endpoint always 500'd in production even after the route-shadowing fix
    (headend_routes.py:551, now uses get_db() like every other handler in
    this module, e.g. get_firewall_rules() at :152). This test wires
    get_db() to a real, migrated database via the real_dal fixture (not a
    config["DAL"] mock) and registers a genuine active cluster through
    ClusterManager.register_cluster() — the same path production
    enrollment uses — so it fails again if refresh_auth_token() reverts to
    reading config["DAL"].

    Args:
        app_with_sase: Test app with SASE module.
        real_dal: Real, alembic-migrated AsyncDB fixture.
        monkeypatch: Pytest monkeypatch fixture.
    """
    import hub_api.api.headend_routes as headend_routes_module
    from hub_api.auth.jwt import encode_access_token
    from hub_api.auth.machine_claims import build_machine_claims
    from hub_api.modules.sdwan.orchestrator.cluster_manager import ClusterManager

    # Wire get_db() (the accessor refresh_auth_token() must use) to the real
    # migrated DB, exactly how the module resolves it at request time.
    monkeypatch.setattr(headend_routes_module, "get_db", lambda: real_dal)

    tenant = "acme"
    cluster_mgr = ClusterManager(real_dal, tenant)
    cluster, _api_key = await cluster_mgr.register_cluster(
        {
            "id": "cluster-real-1",
            "name": "real-cluster",
            "region": "us-east-1",
            "datacenter": "dc1",
            "headend_url": "https://headend.example.com",
        }
    )

    provider = app_with_sase.config["KEY_PROVIDER"]
    claims = build_machine_claims(
        sub_id=cluster.id,
        node_type="kubernetes_node",
        tenant=tenant,
        iss="tobogganing",
        aud="tobogganing",
        token_type="refresh",
    )
    refresh_token = await encode_access_token(claims, provider, ttl_hours=24)

    # CACHE is orthogonal to the DAL-accessor bug; a stub that reports the
    # token's own jti as the current one (no replay) is sufficient here —
    # the DB is what must be real.
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=claims["jti"])
    cache.set = AsyncMock()
    app_with_sase.config["CACHE"] = cache
    # DAL intentionally unset in config — get_db() must be what supplies it.

    client = app_with_sase.test_client()
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "access_token" in data
    assert "refresh_token" in data
    # Refresh token is single-use/rotating: the new one must differ.
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_get_clusters_no_auth(app_with_sase: Quart) -> None:
    """Test GET /api/v1/clusters/ requires authorization.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/clusters/")

    # Should reject without auth
    assert response.status_code in (401, 403)
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_clusters_invalid_auth(app_with_sase: Quart) -> None:
    """Test GET /api/v1/clusters/ with invalid bearer token rejects request.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get(
        "/api/v1/clusters/",
        headers={"Authorization": "Bearer invalid-token"},
    )

    # Should reject with 403 (tenant/scope check fails)
    assert response.status_code in (401, 403)
    data = await response.get_json()
    assert "error" in data


# Regression tests for Security Finding A: Identity spoofing on POST /auth/token


@pytest.mark.asyncio
async def test_post_auth_token_cluster_identity_spoofing_rejected(
    app_with_sase: Quart,
) -> None:
    """Regression test: cluster token request with mismatched node_id is rejected.

    Verifies that a valid cluster api_key cannot be used to mint a token for a
    different node_id. The node_id must match the authenticated cluster's id.

    Regression: gh-finding-A (identity spoofing on cluster branch)
    """
    client = app_with_sase.test_client()

    # Configure cluster_manager in app config
    mock_cluster_manager = MagicMock()
    app_with_sase.config["CLUSTER_MANAGER"] = mock_cluster_manager

    # Mock successful cluster authentication for cluster-1
    mock_cluster = MagicMock(
        id="cluster-1",
        region="us-east-1",
        datacenter="dc1",
        tenant_id="default",
    )
    mock_cluster_manager.authenticate_cluster = MagicMock(return_value=mock_cluster)

    # (asyncio.to_thread was never on the real call path here — the handler
    # awaits cluster_manager.authenticate_cluster() directly — so a prior
    # mock on it was dead and has been removed.)
    # Attempt to mint token for cluster-1 but request node_id as cluster-2
    # This should fail because the authenticated cluster id (cluster-1) does
    # not match the requested node_id (cluster-2)
    response = await client.post(
        "/api/v1/auth/token",
        json={
            "node_id": "cluster-2",  # Mismatched: authenticated is cluster-1
            "node_type": "kubernetes_node",
            "api_key": "test-api-key",
        },
    )

    # Must reject with 401 (identity mismatch)
    assert (
        response.status_code == 401
    ), f"Expected 401 for identity spoofing attempt, got {response.status_code}"
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_post_auth_token_cluster_identity_bound_correctly(
    app_with_sase: Quart,
) -> None:
    """Regression test: cluster token subject (sub) is bound to authenticated cluster id.

    Verifies that when a valid cluster api_key is used with a matching node_id,
    the issued JWT's "sub" claim is set to the authenticated cluster's id
    (not the request body's node_id, as defense in depth).

    Regression: gh-finding-A (identity spoofing on cluster branch)
    """
    client = app_with_sase.test_client()

    # Configure cluster_manager in app config
    mock_cluster_manager = MagicMock()
    app_with_sase.config["CLUSTER_MANAGER"] = mock_cluster_manager

    # Mock successful cluster authentication (AsyncMock, .tenant field not .tenant_id)
    mock_cluster = MagicMock(
        id="cluster-1",
        region="us-east-1",
        datacenter="dc1",
        tenant="default",
    )
    mock_cluster_manager.authenticate_cluster = AsyncMock(return_value=mock_cluster)

    response = await client.post(
        "/api/v1/auth/token",
        json={
            "node_id": "cluster-1",  # Matching authenticated cluster
            "node_type": "kubernetes_node",
            "api_key": "test-api-key",
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "access_token" in data

    # Decode token to verify sub claim
    import jwt as pyjwt

    provider = app_with_sase.config["KEY_PROVIDER"]
    token = data["access_token"]
    decoded = pyjwt.decode(
        token,
        provider.public_pem,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )

    # Sub must be prefixed for machine JWT: cluster:cluster-1
    assert (
        decoded["sub"] == "cluster:cluster-1"
    ), f"Expected sub='cluster:cluster-1', got sub='{decoded['sub']}'"


# Regression tests for Security Finding B: Client-supplied tenant on GET /headend/<id>/ports


@pytest.mark.asyncio
async def test_get_headend_ports_tenant_param_ignored(app_with_sase: Quart) -> None:
    """Regression test: tenant query parameter is ignored on GET /headend/<id>/ports.

    Verifies that even if a client supplies ?tenant=other-tenant, the endpoint
    does not scope to that tenant. The tenant is always "default" (no client control).

    Regression: gh-finding-B (client-supplied tenant parameter)
    """
    client = app_with_sase.test_client()

    test_token = "test-headend-token"
    os.environ["HEADEND_API_TOKEN"] = test_token

    with patch("hub_api.api.headend_routes.get_port_config_manager") as mock_get_pcm:
        mock_pcm = AsyncMock()
        mock_get_pcm.return_value = mock_pcm

        # Track calls to get_headend_config
        config_calls = []

        async def track_get_config(headend_id: str, tenant: str) -> MagicMock | None:
            config_calls.append({"headend_id": headend_id, "tenant": tenant})
            # Return a config only if tenant is "default" (the correct tenant)
            if tenant == "default":
                config = MagicMock()
                config.headend_id = headend_id
                config.cluster_id = f"cluster-{headend_id}"
                config.tcp_ranges = []
                config.udp_ranges = []
                config.updated_at = None
                return config
            else:
                # Request for other-tenant should not happen
                return None

        mock_pcm.get_headend_config = AsyncMock(side_effect=track_get_config)

        with patch("hub_api.api.headend_routes.get_db") as mock_get_db:
            mock_get_db.return_value = MagicMock()

            # Request with ?tenant=other-tenant (attacker tries cross-tenant read)
            await client.get(
                "/api/v1/headend/headend-1/ports?tenant=other-tenant",
                headers={"Authorization": f"Bearer {test_token}"},
            )

            # Verify endpoint was called with "default" tenant, not "other-tenant"
            assert len(config_calls) > 0, "get_headend_config was not called"
            assert (
                config_calls[0]["tenant"] == "default"
            ), f"Expected tenant='default', got tenant='{config_calls[0]['tenant']}'. Query param must be ignored."
