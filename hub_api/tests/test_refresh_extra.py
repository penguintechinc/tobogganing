"""Additional coverage for hub_api.auth.refresh rotate_refresh() edge branches.

test_refresh_rotation.py covers the main success/replay/inactive/absent-cluster
paths; this file fills in missing-subject, malformed-subject, claim-preservation
(permissions/metadata), encode failures, and cache-set-unavailable branches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.auth.refresh import RefreshError, rotate_refresh
from hub_api.cache.client import CacheClient, CacheUnavailable
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster


@pytest.fixture
def key_provider() -> InAppKeyProvider:
    """Real in-app RSA key provider for signing test tokens."""
    priv, pub = generate_rsa_key_pair()
    return InAppKeyProvider(priv, pub)


@pytest.fixture
def mock_cache() -> AsyncMock:
    """Mock CacheClient."""
    return AsyncMock(spec=CacheClient)


@pytest.fixture
def mock_cluster_manager() -> AsyncMock:
    """Mock ClusterManager."""
    return AsyncMock()


@pytest.fixture
def active_cluster() -> Cluster:
    """An active cluster stub matching the token's subject."""
    return Cluster(
        id="test-cluster-id",
        name="Test Cluster",
        region="us-east-1",
        datacenter="dc1",
        headend_url="https://headend.example.com",
        status="active",
        last_heartbeat=None,
        client_count=0,
        tenant="tenant-1",
    )


@pytest.mark.asyncio
async def test_missing_subject_rejected(key_provider, mock_cache, mock_cluster_manager) -> None:
    """rotate_refresh() rejects a token with no 'sub' claim."""
    # encode_access_token requires the 'sub' key to be present (but not truthy);
    # rotate_refresh's `if not subject` check is what we're exercising here.
    claims = {
        "sub": "",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-1",
        "token_type": "refresh",
    }
    refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)
    mock_cache.get.return_value = None

    with pytest.raises(RefreshError) as exc_info:
        await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_malformed_subject_rejected(key_provider, mock_cache, mock_cluster_manager) -> None:
    """rotate_refresh() rejects a subject without a ':' separator."""
    claims = {
        "sub": "no-colon-subject",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-1",
        "token_type": "refresh",
    }
    refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)
    mock_cache.get.return_value = None

    with pytest.raises(RefreshError) as exc_info:
        await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

    assert exc_info.value.status == 401
    assert "subject invalid" in exc_info.value.body.get("error", "")


@pytest.mark.asyncio
async def test_preserves_permissions_and_metadata(
    key_provider, mock_cache, mock_cluster_manager, active_cluster
) -> None:
    """rotate_refresh() copies permissions/metadata from the old claims to new tokens."""
    from hub_api.auth.jwt import decode_token

    claims = build_machine_claims(
        sub_id="test-cluster-id",
        node_type="kubernetes_node",
        tenant="tenant-1",
        iss="tobogganing",
        aud="tobogganing",
        token_type="refresh",
    )
    claims["permissions"] = "headend proxy"
    claims["metadata"] = {"region": "us-east-1"}
    refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

    mock_cache.get.return_value = claims["jti"]
    mock_cluster_manager.get_cluster.return_value = active_cluster

    result = await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

    new_access_claims = decode_token(result["access_token"], key_provider)
    new_refresh_claims = decode_token(result["refresh_token"], key_provider)

    assert new_access_claims["permissions"] == "headend proxy"
    assert new_access_claims["metadata"] == {"region": "us-east-1"}
    assert new_refresh_claims["permissions"] == "headend proxy"
    assert new_refresh_claims["metadata"] == {"region": "us-east-1"}


@pytest.mark.asyncio
async def test_access_token_encode_failure_returns_500(
    key_provider, mock_cache, mock_cluster_manager, active_cluster
) -> None:
    """rotate_refresh() surfaces a 500 when encoding the new access token fails."""
    claims = build_machine_claims(
        sub_id="test-cluster-id",
        node_type="kubernetes_node",
        tenant="tenant-1",
        iss="tobogganing",
        aud="tobogganing",
        token_type="refresh",
    )
    refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

    mock_cache.get.return_value = claims["jti"]
    mock_cluster_manager.get_cluster.return_value = active_cluster

    with patch(
        "hub_api.auth.refresh.encode_access_token",
        side_effect=ValueError("signing failed"),
    ):
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

    assert exc_info.value.status == 500


@pytest.mark.asyncio
async def test_refresh_token_encode_failure_returns_500(
    key_provider, mock_cache, mock_cluster_manager, active_cluster
) -> None:
    """rotate_refresh() surfaces a 500 when encoding the new refresh token fails."""
    claims = build_machine_claims(
        sub_id="test-cluster-id",
        node_type="kubernetes_node",
        tenant="tenant-1",
        iss="tobogganing",
        aud="tobogganing",
        token_type="refresh",
    )
    refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

    mock_cache.get.return_value = claims["jti"]
    mock_cluster_manager.get_cluster.return_value = active_cluster

    real_encode = encode_access_token
    call_count = {"n": 0}

    async def fake_encode(*args: object, **kwargs: object) -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return await real_encode(*args, **kwargs)  # type: ignore[arg-type]
        raise ValueError("signing failed on refresh token")

    with patch("hub_api.auth.refresh.encode_access_token", side_effect=fake_encode):
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

    assert exc_info.value.status == 500


@pytest.mark.asyncio
async def test_cache_set_unavailable_returns_503(
    key_provider, mock_cache, mock_cluster_manager, active_cluster
) -> None:
    """rotate_refresh() returns 503 when caching the new refresh jti fails."""
    claims = build_machine_claims(
        sub_id="test-cluster-id",
        node_type="kubernetes_node",
        tenant="tenant-1",
        iss="tobogganing",
        aud="tobogganing",
        token_type="refresh",
    )
    refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

    mock_cache.get.return_value = claims["jti"]
    mock_cache.set.side_effect = CacheUnavailable("cache down")
    mock_cluster_manager.get_cluster.return_value = active_cluster

    with pytest.raises(RefreshError) as exc_info:
        await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

    assert exc_info.value.status == 503
    assert exc_info.value.body.get("retry_with_credentials") is True
