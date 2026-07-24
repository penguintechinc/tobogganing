"""Tests for headend policy endpoints (firewall rules, port config).

These endpoints are for headend-to-manager API communication.
The Go hub-router polls these endpoints for firewall rules and port configuration.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
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
    with patch(
        "core.api.headend_routes.get_access_control_manager"
    ) as mock_get_acm:
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

        with patch(
            "core.api.headend_routes.get_user_manager"
        ) as mock_get_um:
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

    with patch(
        "core.api.headend_routes.get_port_config_manager"
    ) as mock_get_pcm:
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

    with patch(
        "core.api.headend_routes.get_port_config_manager"
    ) as mock_get_pcm:
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
    from core.auth.jwt import encode_access_token

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
