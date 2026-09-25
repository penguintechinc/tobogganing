"""Tests for JWT refresh token rotation with replay protection."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from hub_api.auth.refresh import (
    RefreshError,
    is_jti_revoked,
    revoke_cluster,
    rotate_refresh,
)
from hub_api.auth.jwt import encode_access_token, decode_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.cache.client import CacheClient, CacheUnavailable
from hub_api.crypto import generate_rsa_key_pair, InAppKeyProvider
from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster


class TestIsJtiRevoked:
    """Tests for is_jti_revoked function (fail-open)."""

    @pytest.mark.asyncio
    async def test_revoked_jti_found_in_cache(self):
        """Test that a revoked JTI is detected."""
        cache = AsyncMock(spec=CacheClient)
        cache.exists.return_value = True

        result = await is_jti_revoked("revoked_jti", cache)
        assert result is True
        cache.exists.assert_called_once_with("auth", "revoked_jti", "revoked_jti")

    @pytest.mark.asyncio
    async def test_valid_jti_not_in_cache(self):
        """Test that a valid JTI is not marked as revoked."""
        cache = AsyncMock(spec=CacheClient)
        cache.exists.return_value = False

        result = await is_jti_revoked("valid_jti", cache)
        assert result is False
        cache.exists.assert_called_once_with("auth", "revoked_jti", "valid_jti")

    @pytest.mark.asyncio
    async def test_cache_unavailable_fails_open(self):
        """Test that cache unavailability returns False (fail-open)."""
        cache = AsyncMock(spec=CacheClient)
        cache.exists.side_effect = CacheUnavailable("cache down")

        result = await is_jti_revoked("some_jti", cache)
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_error_fails_open(self):
        """Test that any cache error returns False (fail-open)."""
        cache = AsyncMock(spec=CacheClient)
        cache.exists.side_effect = Exception("unexpected error")

        result = await is_jti_revoked("some_jti", cache)
        assert result is False


class TestRevokeCluster:
    """Tests for revoke_cluster function (best-effort)."""

    @pytest.mark.asyncio
    async def test_revoke_cluster_deletes_cache_entry(self):
        """Test that revoke_cluster deletes the refresh cache entry."""
        cache = AsyncMock(spec=CacheClient)
        subject = "cluster:test-cluster-id"

        await revoke_cluster(subject, cache)
        cache.delete.assert_called_once_with("auth", "refresh", subject)

    @pytest.mark.asyncio
    async def test_revoke_cluster_logs_error_on_cache_failure(self):
        """Test that revoke_cluster logs but doesn't raise on cache error."""
        cache = AsyncMock(spec=CacheClient)
        cache.delete.side_effect = Exception("cache error")

        # Should not raise
        await revoke_cluster("cluster:test-id", cache)


class TestRotateRefresh:
    """Tests for rotate_refresh function."""

    @pytest.fixture
    def key_provider(self):
        """Fixture for a real KeyProvider using in-app RSA keys."""
        priv, pub = generate_rsa_key_pair()
        return InAppKeyProvider(priv, pub)

    @pytest.fixture
    def mock_cache(self):
        """Fixture for a mock CacheClient."""
        cache = AsyncMock(spec=CacheClient)
        return cache

    @pytest.fixture
    def mock_cluster_manager(self):
        """Fixture for a mock ClusterManager."""
        manager = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_successful_rotation(self, key_provider, mock_cache, mock_cluster_manager):
        """Test successful refresh token rotation."""
        # Build a valid refresh token
        claims = build_machine_claims(
            sub_id="test-cluster-id",
            node_type="kubernetes_node",
            tenant="tenant-1",
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

        # Setup cache to return the same jti (valid refresh)
        mock_cache.get.return_value = claims["jti"]

        # Setup cluster manager to return active cluster
        cluster = Cluster(
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
        mock_cluster_manager.get_cluster.return_value = cluster

        # Perform rotation
        result = await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

        # Verify result contains both tokens
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["access_token"] != refresh_token
        assert result["refresh_token"] != refresh_token

        # Verify the tokens are valid
        access_claims = decode_token(result["access_token"], key_provider)
        refresh_claims = decode_token(result["refresh_token"], key_provider)
        assert access_claims is not None
        assert refresh_claims is not None
        assert refresh_claims.get("token_type") == "refresh"

        # Verify cache was called correctly
        mock_cache.get.assert_called_once_with("auth", "refresh", "cluster:test-cluster-id", fail_closed=True)
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_replay_detection_revokes_cluster(self, key_provider, mock_cache, mock_cluster_manager):
        """Test that replaying an old refresh token revokes the cluster."""
        # Build a valid refresh token
        claims = build_machine_claims(
            sub_id="test-cluster-id",
            node_type="kubernetes_node",
            tenant="tenant-1",
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

        # Setup cache to return a DIFFERENT jti (replay detected)
        mock_cache.get.return_value = "different_jti"

        # Setup cluster manager
        cluster = Cluster(
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
        mock_cluster_manager.get_cluster.return_value = cluster

        # Attempt rotation (should fail with replay error)
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

        error = exc_info.value
        assert error.status == 401
        assert "superseded" in error.body.get("error", "")

        # Verify cluster was revoked
        mock_cache.delete.assert_called_once_with("auth", "refresh", "cluster:test-cluster-id")

    @pytest.mark.asyncio
    async def test_inactive_cluster_rejected(self, key_provider, mock_cache, mock_cluster_manager):
        """Test that inactive cluster cannot rotate refresh."""
        # Build a valid refresh token
        claims = build_machine_claims(
            sub_id="test-cluster-id",
            node_type="kubernetes_node",
            tenant="tenant-1",
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

        # Setup cache to return same jti
        mock_cache.get.return_value = claims["jti"]

        # Setup cluster manager to return INACTIVE cluster
        cluster = Cluster(
            id="test-cluster-id",
            name="Test Cluster",
            region="us-east-1",
            datacenter="dc1",
            headend_url="https://headend.example.com",
            status="inactive",  # Not active!
            last_heartbeat=None,
            client_count=0,
            tenant="tenant-1",
        )
        mock_cluster_manager.get_cluster.return_value = cluster

        # Attempt rotation (should fail)
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

        error = exc_info.value
        assert error.status == 401
        assert "subject invalid" in error.body.get("error", "")

    @pytest.mark.asyncio
    async def test_absent_cluster_rejected(self, key_provider, mock_cache, mock_cluster_manager):
        """Test that absent cluster cannot rotate refresh."""
        # Build a valid refresh token
        claims = build_machine_claims(
            sub_id="nonexistent-cluster",
            node_type="kubernetes_node",
            tenant="tenant-1",
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

        # Setup cache to return same jti
        mock_cache.get.return_value = claims["jti"]

        # Setup cluster manager to return None (cluster not found)
        mock_cluster_manager.get_cluster.return_value = None

        # Attempt rotation (should fail)
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

        error = exc_info.value
        assert error.status == 401
        assert "subject invalid" in error.body.get("error", "")

    @pytest.mark.asyncio
    async def test_cache_unavailable_fails_closed(self, key_provider, mock_cache, mock_cluster_manager):
        """Test that cache unavailability fails closed with 503 and retry hint."""
        # Build a valid refresh token
        claims = build_machine_claims(
            sub_id="test-cluster-id",
            node_type="kubernetes_node",
            tenant="tenant-1",
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        refresh_token = await encode_access_token(claims, key_provider, ttl_hours=24)

        # Setup cache to raise CacheUnavailable on get (fail-closed)
        mock_cache.get.side_effect = CacheUnavailable("cache backend unreachable")

        # Attempt rotation (should fail with 503)
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh(refresh_token, mock_cache, key_provider, mock_cluster_manager)

        error = exc_info.value
        assert error.status == 503
        assert error.body.get("retry_with_credentials") is True

    @pytest.mark.asyncio
    async def test_invalid_refresh_token_rejected(self, key_provider, mock_cache, mock_cluster_manager):
        """Test that invalid refresh token is rejected."""
        # Attempt rotation with invalid token
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh("invalid_token", mock_cache, key_provider, mock_cluster_manager)

        error = exc_info.value
        assert error.status == 401

    @pytest.mark.asyncio
    async def test_wrong_token_type_rejected(self, key_provider, mock_cache, mock_cluster_manager):
        """Test that access token (wrong type) is rejected as refresh."""
        # Build an access token (not refresh)
        claims = build_machine_claims(
            sub_id="test-cluster-id",
            node_type="kubernetes_node",
            tenant="tenant-1",
            iss="tobogganing",
            aud="tobogganing",
            token_type="access",  # Wrong type!
        )
        access_token = await encode_access_token(claims, key_provider, ttl_hours=1)

        # Attempt to rotate using access token (should fail)
        with pytest.raises(RefreshError) as exc_info:
            await rotate_refresh(access_token, mock_cache, key_provider, mock_cluster_manager)

        error = exc_info.value
        assert error.status == 401
