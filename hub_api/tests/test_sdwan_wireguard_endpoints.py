"""Additional coverage for the SDWAN WireGuard API blueprint.

Covers /wireguard/keys error/edge paths, /wireguard/peers, and
/wireguard/keys/<node_id> (revoke) which have no dedicated tests elsewhere,
plus the standalone _extract_bearer_token helper (currently unused by any
route but kept as a public utility).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from quart import Quart

from hub_api.modules.sdwan.api import wireguard as wireguard_module
from hub_api.modules.sdwan.api.wireguard import _extract_bearer_token


def test_extract_bearer_token_valid() -> None:
    """Valid 'Bearer <token>' header returns the token."""
    assert _extract_bearer_token("Bearer abc123") == "abc123"


def test_extract_bearer_token_none() -> None:
    """None header returns None."""
    assert _extract_bearer_token(None) is None


def test_extract_bearer_token_missing_prefix() -> None:
    """Header without 'Bearer ' prefix returns None."""
    assert _extract_bearer_token("Basic abc123") is None


def test_extract_bearer_token_empty_after_prefix() -> None:
    """'Bearer ' with only whitespace after it returns None."""
    assert _extract_bearer_token("Bearer    ") is None


@pytest.fixture
def app_wg(app_with_sase: Quart, monkeypatch: Any) -> Quart:
    """App with SASE registered and sase.wireguard feature flag enabled.

    Args:
        app_with_sase: Base SASE app fixture.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        App with wireguard feature flag forced on.
    """
    import shared.licensing.entitlements

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.sase."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)
    return app_with_sase


@pytest.fixture
def managers(app_wg: Quart) -> dict[str, MagicMock]:
    """Wire mock cluster/client/wg/cert managers into app config.

    Args:
        app_wg: App with wireguard flag enabled.

    Returns:
        Dict of the mocks that were installed, keyed by config name.
    """
    cluster_manager = MagicMock()
    cluster_manager.authenticate_cluster = MagicMock(return_value=None)

    client_registry = MagicMock()
    client_registry.authenticate_client = MagicMock(return_value=None)

    wg_manager = MagicMock()
    wg_manager.generate_wireguard_keys = AsyncMock(
        return_value={
            "private_key": "priv",
            "public_key": "pub",
            "ip_address": "10.200.0.5",
        }
    )
    wg_manager.get_all_wireguard_peers = AsyncMock(return_value=[])
    wg_manager.revoke_wireguard_keys = AsyncMock(return_value=True)

    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(return_value=("key", "cert", "ca"))
    cert_manager.generate_client_certificate = AsyncMock(return_value=("key", "cert", "ca"))

    app_wg.config["CLUSTER_MANAGER"] = cluster_manager
    app_wg.config["CLIENT_REGISTRY"] = client_registry
    app_wg.config["WIREGUARD_MANAGER"] = wg_manager
    app_wg.config["CERT_MANAGER"] = cert_manager

    return {
        "cluster_manager": cluster_manager,
        "client_registry": client_registry,
        "wg_manager": wg_manager,
        "cert_manager": cert_manager,
    }


# --- POST /wireguard/keys -------------------------------------------------


@pytest.mark.asyncio
async def test_generate_keys_missing_fields(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Missing required fields returns 400."""
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={"node_id": "node-1"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Missing required fields" in data["error"]


@pytest.mark.asyncio
async def test_generate_keys_managers_not_configured(
    app_wg: Quart, valid_tenant_token: str
) -> None:
    """Missing wg_manager/pki_manager returns 500."""
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "headend",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Internal server error"


@pytest.mark.asyncio
async def test_generate_keys_cluster_manager_not_configured(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Cluster-type node with CLUSTER_MANAGER unset stays unauthenticated -> 401."""
    app_wg.config["CLUSTER_MANAGER"] = None
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "headend",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_keys_client_registry_not_configured(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Client-type node with CLIENT_REGISTRY unset stays unauthenticated -> 401."""
    app_wg.config["CLIENT_REGISTRY"] = None
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "client_docker",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_keys_cluster_auth_raises(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Exception during cluster authentication is caught -> 401 (fail closed)."""
    managers["cluster_manager"].authenticate_cluster = MagicMock(side_effect=RuntimeError("boom"))
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "kubernetes_node",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_keys_client_auth_raises(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Exception during client authentication is caught -> 401 (fail closed)."""
    managers["client_registry"].authenticate_client = MagicMock(side_effect=RuntimeError("boom"))
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "client_native",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_keys_wg_manager_raises(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Exception from wg_manager.generate_wireguard_keys returns 500."""
    managers["cluster_manager"].authenticate_cluster = MagicMock(
        return_value=MagicMock(id="node-1", tenant="test-tenant")
    )
    managers["wg_manager"].generate_wireguard_keys = AsyncMock(
        side_effect=RuntimeError("keygen failed")
    )
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "headend",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Failed to generate WireGuard keys"


@pytest.mark.asyncio
async def test_generate_keys_cert_generation_raises(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Exception from certificate generation returns 500."""
    managers["cluster_manager"].authenticate_cluster = MagicMock(
        return_value=MagicMock(id="node-1", tenant="test-tenant")
    )
    managers["cert_manager"].generate_headend_certificate = AsyncMock(
        side_effect=RuntimeError("cert failed")
    )
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "headend",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Failed to generate certificate"


@pytest.mark.asyncio
async def test_generate_keys_value_error_returns_400(
    app_wg: Quart,
    valid_tenant_token: str,
    managers: dict[str, MagicMock],
    monkeypatch: Any,
) -> None:
    """A ValueError raised anywhere in the handler maps to 400."""
    monkeypatch.setattr(
        wireguard_module,
        "current_claims",
        MagicMock(side_effect=ValueError("bad claims")),
    )
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "headend",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Invalid request" in data["error"]


@pytest.mark.asyncio
async def test_generate_keys_generic_exception_returns_500(
    app_wg: Quart,
    valid_tenant_token: str,
    managers: dict[str, MagicMock],
    monkeypatch: Any,
) -> None:
    """A generic Exception raised anywhere in the handler maps to 500."""
    monkeypatch.setattr(
        wireguard_module,
        "current_claims",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    client = app_wg.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "node-1",
            "node_type": "headend",
            "api_key": "some-key",
        },
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Internal server error"


# --- GET /wireguard/peers ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_peers_success(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Successful peer listing returns 200 with peers/total."""
    managers["wg_manager"].get_all_wireguard_peers = AsyncMock(
        return_value=[{"node_id": "n1", "public_key": "pk", "ip_address": "10.200.0.1"}]
    )
    client = app_wg.test_client()

    response = await client.get(
        "/api/v1/sdwan/wireguard/peers",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["total"] == 1
    assert data["peers"][0]["node_id"] == "n1"


@pytest.mark.asyncio
async def test_get_peers_manager_not_configured(app_wg: Quart, valid_tenant_token: str) -> None:
    """No WIREGUARD_MANAGER configured returns 500."""
    client = app_wg.test_client()

    response = await client.get(
        "/api/v1/sdwan/wireguard/peers",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_peers_fetch_raises(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Exception while fetching peers returns 500."""
    managers["wg_manager"].get_all_wireguard_peers = AsyncMock(side_effect=RuntimeError("boom"))
    client = app_wg.test_client()

    response = await client.get(
        "/api/v1/sdwan/wireguard/peers",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Failed to fetch peers"


@pytest.mark.asyncio
async def test_get_peers_generic_exception(
    app_wg: Quart,
    valid_tenant_token: str,
    managers: dict[str, MagicMock],
    monkeypatch: Any,
) -> None:
    """Unexpected exception in get_wireguard_peers maps to 500."""
    monkeypatch.setattr(
        wireguard_module,
        "current_claims",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    client = app_wg.test_client()

    response = await client.get(
        "/api/v1/sdwan/wireguard/peers",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Internal server error"


# --- DELETE /wireguard/keys/<node_id> (revoke) ------------------------------


@pytest.mark.asyncio
async def test_revoke_keys_success(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Successful revocation returns 200."""
    client = app_wg.test_client()

    response = await client.delete(
        "/api/v1/sdwan/wireguard/keys/node-1",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["revoked"] is True
    assert data["node_id"] == "node-1"


@pytest.mark.asyncio
async def test_revoke_keys_not_found(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Revocation of unknown node returns 404."""
    managers["wg_manager"].revoke_wireguard_keys = AsyncMock(return_value=False)
    client = app_wg.test_client()

    response = await client.delete(
        "/api/v1/sdwan/wireguard/keys/unknown-node",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 404
    data = await response.get_json()
    assert data["error"] == "Node not found"


@pytest.mark.asyncio
async def test_revoke_keys_manager_not_configured(app_wg: Quart, valid_tenant_token: str) -> None:
    """No WIREGUARD_MANAGER configured returns 500."""
    client = app_wg.test_client()

    response = await client.delete(
        "/api/v1/sdwan/wireguard/keys/node-1",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_revoke_keys_raises(
    app_wg: Quart, valid_tenant_token: str, managers: dict[str, MagicMock]
) -> None:
    """Exception during revocation returns 500."""
    managers["wg_manager"].revoke_wireguard_keys = AsyncMock(side_effect=RuntimeError("boom"))
    client = app_wg.test_client()

    response = await client.delete(
        "/api/v1/sdwan/wireguard/keys/node-1",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Failed to revoke keys"


@pytest.mark.asyncio
async def test_revoke_keys_generic_exception(
    app_wg: Quart,
    valid_tenant_token: str,
    managers: dict[str, MagicMock],
    monkeypatch: Any,
) -> None:
    """Unexpected exception in revoke_wireguard_keys maps to 500."""
    monkeypatch.setattr(
        wireguard_module,
        "current_claims",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    client = app_wg.test_client()

    response = await client.delete(
        "/api/v1/sdwan/wireguard/keys/node-1",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
    )

    assert response.status_code == 500
    data = await response.get_json()
    assert data["error"] == "Internal server error"
