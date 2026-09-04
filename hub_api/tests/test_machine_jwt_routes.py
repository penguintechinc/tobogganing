"""Tests for machine-JWT authentication on protected routes.

Covers dual-accept (flag ON/OFF), tenant scoping (C1/C2),
and security-review Finding 2 (C6).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest
import pytest_asyncio

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair


@pytest_asyncio.fixture
async def machine_jwt_firewall(app: Any, tenant: str = "acme") -> str:
    """Generate a valid machine-JWT with firewall:read scope.

    Args:
        app: App with key provider.
        tenant: Tenant ID (default "acme").

    Returns:
        Encoded machine-JWT token.
    """
    provider = app.config["KEY_PROVIDER"]

    claims = build_machine_claims(
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant=tenant,
        iss="tobogganing",
        aud="headend",
    )

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def machine_jwt_metrics(app: Any, tenant: str = "acme") -> str:
    """Generate a valid machine-JWT with metrics:write scope.

    Args:
        app: App with key provider.
        tenant: Tenant ID (default "acme").

    Returns:
        Encoded machine-JWT token.
    """
    provider = app.config["KEY_PROVIDER"]

    claims = build_machine_claims(
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant=tenant,
        iss="tobogganing",
        aud="headend",
    )

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_flag_off_accepts_static_token(
    app: Any, mock_db: MagicMock
) -> None:
    """Test firewall/rules accepts static token when flag is OFF (dual-accept).

    Regression: backward-compatibility during transition to machine-JWT.

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    static_token = "test-headend-static-token"
    import shared.licensing.entitlements

    with patch.dict(os.environ, {"HEADEND_API_TOKEN": static_token}):
        with patch.object(
            shared.licensing.entitlements, "_flag_on", return_value=False
        ):
            client = app.test_client()

            # Mock UserManager.list_users to return empty list
            with patch(
                "hub_api.api.headend_routes.get_user_manager"
            ) as mock_um_factory:
                mock_um = MagicMock()
                mock_um.list_users = AsyncMock(return_value=[])
                mock_um_factory.return_value = mock_um

                # Mock AccessControlManager
                with patch(
                    "hub_api.api.headend_routes.get_access_control_manager"
                ) as mock_acm_factory:
                    mock_acm = MagicMock()
                    mock_acm_factory.return_value = mock_acm

                    # Static token should be accepted when flag is OFF
                    resp = await client.get(
                        "/api/v1/firewall/rules",
                        headers={"Authorization": f"Bearer {static_token}"},
                    )
                    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dual_accept_flag_off_accepts_machine_jwt(
    app: Any, machine_jwt_firewall: str, mock_db: MagicMock
) -> None:
    """Test firewall/rules accepts machine-JWT when flag is OFF.

    Args:
        app: Test app.
        machine_jwt_firewall: Valid machine-JWT.
        mock_db: Mock database.
    """
    # Flag OFF (default)
    import shared.licensing.entitlements

    with patch.object(
        shared.licensing.entitlements, "_flag_on", return_value=False
    ):
        client = app.test_client()

        # Mock UserManager.list_users to return empty list
        with patch("hub_api.api.headend_routes.get_user_manager") as mock_um_factory:
            mock_um = MagicMock()
            mock_um.list_users = AsyncMock(return_value=[])
            mock_um_factory.return_value = mock_um

            # Mock AccessControlManager
            with patch(
                "hub_api.api.headend_routes.get_access_control_manager"
            ) as mock_acm_factory:
                mock_acm = MagicMock()
                mock_acm_factory.return_value = mock_acm

                resp = await client.get(
                    "/api/v1/firewall/rules",
                    headers={"Authorization": f"Bearer {machine_jwt_firewall}"},
                )
                assert resp.status_code == 200


@pytest.mark.asyncio
async def test_flag_on_rejects_static_token(
    app: Any, mock_db: MagicMock
) -> None:
    """Test firewall/rules rejects static token when flag is ON (enforcement).

    Regression: flag cutover must reject legacy tokens when enabled.

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    static_token = "test-headend-static-token"
    import shared.licensing.entitlements

    with patch.dict(os.environ, {"HEADEND_API_TOKEN": static_token}):
        with patch.object(
            shared.licensing.entitlements, "_flag_on", return_value=True
        ):
            client = app.test_client()

            # Static token must be rejected when flag is ON
            resp = await client.get(
                "/api/v1/firewall/rules",
                headers={"Authorization": f"Bearer {static_token}"},
            )
            assert resp.status_code == 401


@pytest.mark.asyncio
async def test_flag_on_accepts_machine_jwt(
    app: Any, machine_jwt_firewall: str, mock_db: MagicMock
) -> None:
    """Test firewall/rules accepts machine-JWT when flag is ON.

    Args:
        app: Test app.
        machine_jwt_firewall: Valid machine-JWT.
        mock_db: Mock database.
    """
    # Flag ON
    import shared.licensing.entitlements

    with patch.object(
        shared.licensing.entitlements, "_flag_on", return_value=True
    ):
        client = app.test_client()

        # Mock UserManager.list_users to return empty list
        with patch("hub_api.api.headend_routes.get_user_manager") as mock_um_factory:
            mock_um = MagicMock()
            mock_um.list_users = AsyncMock(return_value=[])
            mock_um_factory.return_value = mock_um

            # Mock AccessControlManager
            with patch(
                "hub_api.api.headend_routes.get_access_control_manager"
            ) as mock_acm_factory:
                mock_acm = MagicMock()
                mock_acm_factory.return_value = mock_acm

                # Machine-JWT must be accepted when flag is ON
                resp = await client.get(
                    "/api/v1/firewall/rules",
                    headers={"Authorization": f"Bearer {machine_jwt_firewall}"},
                )
                assert resp.status_code == 200


@pytest.mark.asyncio
async def test_finding2_bootstrap_token_rejected_flag_on(
    app: Any, mock_db: MagicMock
) -> None:
    """Test bootstrap token is rejected when flag is ON (Finding-2 enforcement).

    Regression: security-review finding-2 (C6) — metrics must require machine-JWT
    not shared bootstrap token. Test via firewall/rules endpoint which is always
    available in test app.

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    bootstrap_token = "test-bootstrap-token"
    import shared.licensing.entitlements

    # Flag ON: enforce machine-JWT requirement (bootstrap token must be rejected)
    with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": bootstrap_token}):
        with patch.object(
            shared.licensing.entitlements, "_flag_on", return_value=True
        ):
            client = app.test_client()

            # Bootstrap token must be REJECTED when flag is ON
            resp = await client.get(
                "/api/v1/firewall/rules",
                headers={"Authorization": f"Bearer {bootstrap_token}"},
            )
            assert resp.status_code == 401


@pytest.mark.asyncio
async def test_client_node_lacks_privileged_scopes(app: Any) -> None:
    """Test client node types have minimal scopes (least privilege).

    Regression: client_docker/client_native should NOT have
    firewall:read, ports:read, metrics:write, or certs:issue.

    Args:
        app: Test app.
    """
    provider = app.config["KEY_PROVIDER"]

    # Create machine-JWT for client node
    claims = build_machine_claims(
        sub_id="client-1",
        node_type="client_docker",
        tenant="acme",
        iss="tobogganing",
        aud="headend",
    )

    # Client should only have wireguard:read, NOT privileged scopes
    assert "wireguard:read" in claims["scope"]
    assert "firewall:read" not in claims["scope"]
    assert "ports:read" not in claims["scope"]
    assert "metrics:write" not in claims["scope"]
    assert "certs:issue" not in claims["scope"]


@pytest.mark.asyncio
async def test_cluster_node_has_full_scopes(app: Any) -> None:
    """Test cluster node types have full scopes.

    Regression: kubernetes_node/raw_compute should have all scopes
    including certs:issue for cert issuance operations.

    Args:
        app: Test app.
    """
    provider = app.config["KEY_PROVIDER"]

    # Create machine-JWT for cluster node
    claims = build_machine_claims(
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="acme",
        iss="tobogganing",
        aud="headend",
    )

    # Cluster should have all scopes
    assert "firewall:read" in claims["scope"]
    assert "wireguard:read" in claims["scope"]
    assert "ports:read" in claims["scope"]
    assert "metrics:write" in claims["scope"]
    assert "certs:issue" in claims["scope"]


@pytest.mark.asyncio
async def test_legacy_headend_token_insufficient_scope_for_certs(
    app: Any, mock_db: MagicMock
) -> None:
    """Test headend token cannot issue certs (scope enforcement).

    Regression: legacy headend token should NOT have certs:issue scope;
    attempting to access cert endpoint should return 403 (insufficient scope).

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    headend_token = "test-headend-token"
    import shared.licensing.entitlements

    # Flag OFF: legacy token fallback enabled
    with patch.dict(os.environ, {"HEADEND_API_TOKEN": headend_token}):
        with patch.object(
            shared.licensing.entitlements, "_flag_on", return_value=False
        ):
            # Mock feature gate for certs endpoint
            with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
                client = app.test_client()

                # Headend token attempting to access certs endpoint
                # should fail with 403 (insufficient scope), not 200
                resp = await client.post(
                    "/api/v1/certs/certificates",
                    headers={"Authorization": f"Bearer {headend_token}"},
                    json={"type": "client", "id": "node-1", "name": "test"},
                )
                assert resp.status_code == 403
                data = await resp.get_json()
                assert "insufficient scope" in data["error"].lower()


@pytest.mark.asyncio
async def test_legacy_bootstrap_token_insufficient_scope_for_firewall(
    app: Any, mock_db: MagicMock
) -> None:
    """Test bootstrap token cannot read firewall (scope enforcement).

    Regression: legacy bootstrap token should NOT have firewall:read scope;
    attempting to read firewall rules should return 403 (insufficient scope).

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    bootstrap_token = "test-bootstrap-token"
    import shared.licensing.entitlements

    # Flag OFF: legacy token fallback enabled
    with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": bootstrap_token}):
        with patch.object(
            shared.licensing.entitlements, "_flag_on", return_value=False
        ):
            client = app.test_client()

            # Bootstrap token attempting to read firewall rules
            # should fail with 403 (insufficient scope), not 200
            resp = await client.get(
                "/api/v1/firewall/rules",
                headers={"Authorization": f"Bearer {bootstrap_token}"},
            )
            assert resp.status_code == 403
            data = await resp.get_json()
            assert "insufficient scope" in data["error"].lower()


@pytest.mark.asyncio
async def test_legacy_bootstrap_token_can_issue_certs(
    app: Any, mock_db: MagicMock
) -> None:
    """Test bootstrap token CAN issue certs (within its allowlist).

    Regression: legacy bootstrap token should have certs:issue scope;
    accessing cert endpoint should succeed (or fail on validation, not auth).

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    bootstrap_token = "test-bootstrap-token"
    import shared.licensing.entitlements

    # Flag OFF: legacy token fallback enabled
    with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": bootstrap_token}):
        with patch.object(
            shared.licensing.entitlements, "_flag_on", return_value=False
        ):
            # Mock feature gate for certs endpoint
            with patch("hub_api.entitlements.gate.feature_enabled", return_value=True):
                client = app.test_client()

                # Bootstrap token should be accepted for cert issuance
                # (not rejected with 403 insufficient scope)
                resp = await client.post(
                    "/api/v1/certs/certificates",
                    headers={"Authorization": f"Bearer {bootstrap_token}"},
                    json={"type": "client", "id": "node-1", "name": "test"},
                )
                # Should NOT be 403 auth error; might be 400/500 validation error
                assert resp.status_code != 403


@pytest.mark.asyncio
async def test_tenant_scoping_firewall_rules(app: Any, mock_db: MagicMock) -> None:
    """Test firewall/rules scoped to authenticated tenant (regression C2).

    Verifies that g.machine_tenant is used instead of hardcoded "default".

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    provider = app.config["KEY_PROVIDER"]

    # Create machine-JWT for tenant "acme"
    claims = build_machine_claims(
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="acme",
        iss="tobogganing",
        aud="headend",
    )
    jwt_acme = await encode_access_token(claims, provider, ttl_hours=1)

    # Mock UserManager to verify tenant is passed
    import shared.licensing.entitlements

    with patch.object(
        shared.licensing.entitlements, "_flag_on", return_value=True
    ):
        client = app.test_client()

        with patch("hub_api.api.headend_routes.get_user_manager") as mock_um_factory:
            mock_um = MagicMock()
            mock_um.list_users = AsyncMock(return_value=[])
            mock_um_factory.return_value = mock_um

            with patch(
                "hub_api.api.headend_routes.get_access_control_manager"
            ) as mock_acm_factory:
                mock_acm = MagicMock()
                mock_acm_factory.return_value = mock_acm

                resp = await client.get(
                    "/api/v1/firewall/rules",
                    headers={"Authorization": f"Bearer {jwt_acme}"},
                )
                assert resp.status_code == 200

                # Verify UserManager was called with tenant="acme", not "default"
                mock_um.list_users.assert_called_once_with("acme")


@pytest.mark.asyncio
async def test_wireguard_peers_tenant_scoping(app: Any, mock_db: MagicMock) -> None:
    """Test wireguard/peers scoped to authenticated tenant (regression C2).

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    provider = app.config["KEY_PROVIDER"]

    # Create machine-JWT for tenant "beta"
    claims = build_machine_claims(
        sub_id="cluster-2",
        node_type="kubernetes_node",
        tenant="beta",
        iss="tobogganing",
        aud="headend",
    )
    jwt_beta = await encode_access_token(claims, provider, ttl_hours=1)

    # Mock CertificateManager
    cert_manager = MagicMock()
    app.config["CERT_MANAGER"] = cert_manager
    cert_manager.get_all_wireguard_peers = AsyncMock(return_value=[])

    import shared.licensing.entitlements

    with patch.object(
        shared.licensing.entitlements, "_flag_on", return_value=True
    ):
        client = app.test_client()

        resp = await client.get(
            "/api/v1/wireguard/peers",
            headers={"Authorization": f"Bearer {jwt_beta}"},
        )
        assert resp.status_code == 200

        # Verify CertificateManager was called with tenant_id="beta"
        cert_manager.get_all_wireguard_peers.assert_called_once_with(tenant_id="beta")


@pytest.mark.asyncio
async def test_headend_ports_tenant_scoping(app: Any, mock_db: MagicMock) -> None:
    """Test headend/ports scoped to authenticated tenant (regression C2).

    Args:
        app: Test app.
        mock_db: Mock database.
    """
    provider = app.config["KEY_PROVIDER"]

    # Create machine-JWT for tenant "prod"
    claims = build_machine_claims(
        sub_id="cluster-3",
        node_type="kubernetes_node",
        tenant="prod",
        iss="tobogganing",
        aud="headend",
    )
    jwt_prod = await encode_access_token(claims, provider, ttl_hours=1)

    import shared.licensing.entitlements

    with patch.object(
        shared.licensing.entitlements, "_flag_on", return_value=True
    ):
        client = app.test_client()

        # Mock PortConfigManager
        with patch(
            "hub_api.api.headend_routes.get_port_config_manager"
        ) as mock_pcm_factory:
            mock_pcm = MagicMock()
            mock_config = MagicMock()
            mock_config.headend_id = "headend-1"
            mock_config.cluster_id = "cluster-3"
            mock_config.tcp_ranges = []
            mock_config.udp_ranges = []
            mock_config.updated_at = None
            mock_pcm.get_headend_config = AsyncMock(return_value=mock_config)
            mock_pcm_factory.return_value = mock_pcm

            resp = await client.get(
                "/api/v1/headend/headend-1/ports",
                headers={"Authorization": f"Bearer {jwt_prod}"},
            )
            assert resp.status_code == 200

            # Verify PortConfigManager was called with tenant="prod"
            mock_pcm.get_headend_config.assert_called_once_with("headend-1", "prod")
