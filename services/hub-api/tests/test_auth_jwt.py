"""
Tests for auth/jwt_manager.py — JWT generation, validation, refresh, revocation.

Key API notes:
- JWTManager.initialize() must be called to set redis_client (async)
- generate_token() returns Dict{"access_token", "refresh_token", "expires_at", "token_type"}
- validate_token() checks Redis cache (active flag) then verifies signature
- revoke_token(jti) marks a JTI inactive in Redis
- revoke_all_tokens(node_id) revokes by node ID pattern
- get_public_key() is async, returns str (PEM)
"""
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
import pytest_asyncio

from auth.jwt_manager import JWTManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_redis_mock():
    """Build an AsyncMock that emulates aioredis client."""
    redis_mock = AsyncMock()
    # Default: tokens are active
    redis_mock.hgetall = AsyncMock(return_value={"active": "True", "node_id": "node-001"})
    redis_mock.hset = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.scan = AsyncMock(return_value=(0, []))
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.pipeline = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=AsyncMock(
            hset=AsyncMock(return_value=None),
            ttl=AsyncMock(return_value=None),
            execute=AsyncMock(return_value=[]),
        )),
        __aexit__=AsyncMock(return_value=False),
        execute=AsyncMock(return_value=[]),
        hset=AsyncMock(return_value=None),
    ))
    redis_mock.close = AsyncMock()
    return redis_mock


@pytest.fixture
def mgr():
    """Fresh JWTManager with mocked Redis client (initialize() bypassed)."""
    m = JWTManager(redis_url="redis://localhost:6379/0", token_expiry_hours=1)
    m.redis_client = _make_redis_mock()
    return m


@pytest.fixture
def mgr_no_cache():
    """JWTManager where Redis cache returns empty (simulates no cache hit)."""
    m = JWTManager(redis_url="redis://localhost:6379/0", token_expiry_hours=1)
    rc = _make_redis_mock()
    rc.hgetall = AsyncMock(return_value={})  # empty = not active
    m.redis_client = rc
    return m


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestJWTManagerInit:
    def test_rsa_keys_generated(self, mgr):
        assert hasattr(mgr, "private_key")
        assert hasattr(mgr, "public_key")
        assert hasattr(mgr, "private_pem")
        assert hasattr(mgr, "public_pem")

    def test_token_expiry_set(self, mgr):
        assert mgr.token_expiry == timedelta(hours=1)

    def test_refresh_expiry_default(self):
        m = JWTManager(redis_url="redis://localhost:6379/0")
        assert m.refresh_expiry == timedelta(days=7)

    @pytest.mark.asyncio
    async def test_initialize_sets_redis_client(self):
        """Test that initialize() sets redis_client from pool."""
        m = JWTManager(redis_url="redis://localhost:6379/0")
        with patch("redis.asyncio.ConnectionPool.from_url") as mock_pool, \
             patch("redis.asyncio.Redis") as mock_redis_cls:
            mock_redis_cls.return_value = _make_redis_mock()
            await m.initialize()
            assert m.redis_client is not None


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

class TestGenerateToken:
    @pytest.mark.asyncio
    async def test_generate_returns_dict(self, mgr):
        result = await mgr.generate_token("node-001", "headend", ["connect"])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_generate_returns_access_token(self, mgr):
        result = await mgr.generate_token("node-001", "headend", ["connect"])
        assert "access_token" in result
        assert len(result["access_token"]) > 0

    @pytest.mark.asyncio
    async def test_generate_returns_refresh_token(self, mgr):
        result = await mgr.generate_token("node-001", "headend", ["connect"])
        assert "refresh_token" in result
        assert len(result["refresh_token"]) > 0

    @pytest.mark.asyncio
    async def test_generate_returns_expires_at(self, mgr):
        result = await mgr.generate_token("node-001", "headend", ["connect"])
        assert "expires_at" in result

    @pytest.mark.asyncio
    async def test_access_token_decodable(self, mgr):
        result = await mgr.generate_token("node-002", "client", ["read"])
        token = result["access_token"]
        payload = pyjwt.decode(token, mgr.public_pem, algorithms=["RS256"])
        assert payload["sub"] == "node-002"
        assert payload["node_type"] == "client"

    @pytest.mark.asyncio
    async def test_token_contains_permissions(self, mgr):
        result = await mgr.generate_token("node-003", "client", ["read", "write"])
        token = result["access_token"]
        payload = pyjwt.decode(token, mgr.public_pem, algorithms=["RS256"])
        assert "read" in payload["permissions"]
        assert "write" in payload["permissions"]

    @pytest.mark.asyncio
    async def test_token_contains_jti(self, mgr):
        result = await mgr.generate_token("node-004", "client", [])
        token = result["access_token"]
        payload = pyjwt.decode(token, mgr.public_pem, algorithms=["RS256"])
        assert "jti" in payload

    @pytest.mark.asyncio
    async def test_token_type_access(self, mgr):
        result = await mgr.generate_token("node-005", "client", [])
        token = result["access_token"]
        payload = pyjwt.decode(token, mgr.public_pem, algorithms=["RS256"])
        assert payload.get("type") == "access"

    @pytest.mark.asyncio
    async def test_token_has_future_expiry(self, mgr):
        result = await mgr.generate_token("node-006", "client", [])
        token = result["access_token"]
        payload = pyjwt.decode(token, mgr.public_pem, algorithms=["RS256"])
        assert payload["exp"] > time.time()

    @pytest.mark.asyncio
    async def test_generate_caches_in_redis(self, mgr):
        await mgr.generate_token("node-007", "client", [])
        assert mgr.redis_client.hset.called

    @pytest.mark.asyncio
    async def test_generate_with_metadata(self, mgr):
        result = await mgr.generate_token(
            "node-008", "client", ["connect"],
            metadata={"version": "0.2.0", "os": "linux"}
        )
        assert "access_token" in result


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

class TestValidateToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self, mgr):
        """Token is valid when Redis cache says active=True."""
        result = await mgr.generate_token("node-010", "client", ["connect"])
        token = result["access_token"]
        # Redis mock returns {"active": "True"} by default
        payload = await mgr.validate_token(token)
        assert payload is not None
        assert payload["sub"] == "node-010"

    @pytest.mark.asyncio
    async def test_expired_token_fails(self, mgr):
        """Manually craft an expired token."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "node-011",
            "node_type": "client",
            "permissions": [],
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
            "jti": str(uuid.uuid4()),
            "type": "access",
        }
        expired_token = pyjwt.encode(payload, mgr.private_pem, algorithm="RS256")
        result = await mgr.validate_token(expired_token)
        assert result is None

    @pytest.mark.asyncio
    async def test_token_not_in_cache_fails(self, mgr_no_cache):
        """Token with empty Redis cache (no 'active' key) is rejected."""
        result = await mgr_no_cache.generate_token("node-012", "client", [])
        # Now set cache to empty for validation
        mgr_no_cache.redis_client.hgetall = AsyncMock(return_value={})
        payload = await mgr_no_cache.validate_token(result["access_token"])
        assert payload is None

    @pytest.mark.asyncio
    async def test_invalid_signature_fails(self, mgr):
        """Token signed with a different key should fail."""
        other_mgr = JWTManager(redis_url="redis://localhost:6379/0")
        other_mgr.redis_client = _make_redis_mock()
        other_result = await other_mgr.generate_token("node-013", "client", [])
        # Validate with original mgr's public key — will fail signature check
        result = await mgr.validate_token(other_result["access_token"])
        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_token_fails(self, mgr):
        result = await mgr.validate_token("not.a.real.token")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_token_fails(self, mgr):
        result = await mgr.validate_token("")
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_cache_returns_none(self, mgr):
        """Token with no cache entry (empty dict) is rejected as inactive."""
        result = await mgr.generate_token("node-014", "client", [])
        # hgetall returns empty dict — no 'active' key → rejected
        mgr.redis_client.hgetall = AsyncMock(return_value={})
        payload = await mgr.validate_token(result["access_token"])
        assert payload is None


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refresh_with_valid_refresh_token(self, mgr):
        result = await mgr.generate_token("node-020", "client", ["connect"])
        refresh_token = result["refresh_token"]
        # Refresh validates the token via Redis — set cache to active
        mgr.redis_client.hgetall = AsyncMock(
            return_value={"active": "True", "type": "refresh"}
        )
        new_result = await mgr.refresh_token(refresh_token)
        assert new_result is not None
        assert "access_token" in new_result

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_returns_none(self, mgr):
        """Cannot use an access token to refresh."""
        result = await mgr.generate_token("node-021", "client", [])
        access_token = result["access_token"]
        # Access tokens have type=access, refresh should reject them
        mgr.redis_client.hgetall = AsyncMock(
            return_value={"active": "True", "type": "access"}
        )
        new_result = await mgr.refresh_token(access_token)
        assert new_result is None

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_returns_none(self, mgr):
        result = await mgr.refresh_token("invalid.token.here")
        assert result is None


# ---------------------------------------------------------------------------
# Token revocation
# ---------------------------------------------------------------------------

class TestRevokeToken:
    @pytest.mark.asyncio
    async def test_revoke_jti_sets_redis(self, mgr):
        result = await mgr.generate_token("node-030", "client", ["connect"])
        token = result["access_token"]
        payload = pyjwt.decode(token, mgr.public_pem, algorithms=["RS256"])
        jti = payload["jti"]
        await mgr.revoke_token(jti)
        # hset should have been called with active=false
        assert mgr.redis_client.hset.called

    @pytest.mark.asyncio
    async def test_revoke_all_tokens_for_node(self, mgr):
        mgr.redis_client.keys = AsyncMock(return_value=[b"token:node-040:jti1"])
        count = await mgr.revoke_all_tokens("node-040")
        assert isinstance(count, int)


# ---------------------------------------------------------------------------
# Public key
# ---------------------------------------------------------------------------

class TestPublicKey:
    @pytest.mark.asyncio
    async def test_get_public_key_returns_string(self, mgr):
        pk = await mgr.get_public_key()
        assert isinstance(pk, str)

    @pytest.mark.asyncio
    async def test_get_public_key_is_pem(self, mgr):
        pk = await mgr.get_public_key()
        assert "PUBLIC KEY" in pk

    @pytest.mark.asyncio
    async def test_public_key_validates_tokens(self, mgr):
        result = await mgr.generate_token("node-050", "client", [])
        token = result["access_token"]
        pk = await mgr.get_public_key()
        payload = pyjwt.decode(token, pk.encode(), algorithms=["RS256"])
        assert payload["sub"] == "node-050"


# ---------------------------------------------------------------------------
# Cleanup / close
# ---------------------------------------------------------------------------

class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_expired_does_not_raise(self, mgr):
        mgr.redis_client.scan = AsyncMock(return_value=(0, []))
        try:
            await mgr.cleanup_expired_tokens()
        except Exception as exc:
            pytest.fail(f"cleanup_expired_tokens raised: {exc}")

    @pytest.mark.asyncio
    async def test_close_does_not_raise(self, mgr):
        mgr.redis_pool = AsyncMock()
        mgr.redis_pool.disconnect = AsyncMock()
        try:
            await mgr.close()
        except Exception as exc:
            pytest.fail(f"close raised: {exc}")


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

class TestCacheHelpers:
    @pytest.mark.asyncio
    async def test_cache_token_metadata_calls_hset(self, mgr):
        await mgr._cache_token_metadata("test-jti-123", {
            "node_id": "node-001",
            "active": True,
            "type": "access",
        })
        assert mgr.redis_client.hset.called

    @pytest.mark.asyncio
    async def test_get_cached_token_metadata(self, mgr):
        mgr.redis_client.hgetall = AsyncMock(return_value={"active": "True"})
        result = await mgr._get_cached_token_metadata("some-jti")
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalidate_token_calls_hset(self, mgr):
        await mgr._invalidate_token("jti-to-revoke")
        assert mgr.redis_client.hset.called
