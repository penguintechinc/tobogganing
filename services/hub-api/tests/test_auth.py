"""
Basic unit tests for Manager Service authentication components
"""
import pytest
import asyncio
import jwt as pyjwt
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from auth.jwt_manager import JWTManager
from auth.keys import InAppKeyProvider


class TestJWTManager:
    """Test JWT token management functionality"""

    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager instance for testing with mocked Redis"""
        # Use InAppKeyProvider to get real PEM keys
        key_provider = InAppKeyProvider()
        manager = JWTManager(
            redis_url="redis://localhost:6379",
            token_expiry_hours=24,
            refresh_expiry_days=7,
            key_provider=key_provider
        )

        # Mock Redis connection pool and client
        manager.redis_pool = MagicMock()
        manager.redis_client = AsyncMock()
        manager.redis_client.hset = AsyncMock(return_value=1)
        manager.redis_client.expire = AsyncMock(return_value=1)
        manager.redis_client.hgetall = AsyncMock(return_value={"active": "true"})
        manager.redis_client.keys = AsyncMock(return_value=[])
        manager.redis_client.pipeline = MagicMock(return_value=AsyncMock())
        manager.redis_client.close = AsyncMock()

        return manager

    def test_jwt_manager_initialization(self, jwt_manager):
        """Test JWT manager initializes correctly"""
        assert jwt_manager is not None
        assert hasattr(jwt_manager, 'private_pem')
        assert hasattr(jwt_manager, 'public_pem')
        assert isinstance(jwt_manager.private_pem, bytes)
        assert isinstance(jwt_manager.public_pem, bytes)
        assert jwt_manager.private_pem.startswith(b'-----BEGIN PRIVATE KEY-----')
        assert jwt_manager.public_pem.startswith(b'-----BEGIN PUBLIC KEY-----')

    @pytest.mark.asyncio
    async def test_generate_token_basic(self, jwt_manager):
        """Test basic token generation"""
        result = await jwt_manager.generate_token(
            node_id="test-client-1",
            node_type="client",
            permissions=["connect", "proxy"]
        )

        assert "access_token" in result
        assert "refresh_token" in result
        assert "expires_at" in result
        assert result["token_type"] == "Bearer"

        # Basic token structure validation
        token = result["access_token"]
        parts = token.split('.')
        assert len(parts) == 3  # JWT has 3 parts: header.payload.signature

    @pytest.mark.asyncio
    async def test_validate_token_valid(self, jwt_manager):
        """Test validation of a valid token"""
        # Generate a token first
        result = await jwt_manager.generate_token(
            node_id="test-client-2",
            node_type="client",
            permissions=["connect"]
        )

        token = result["access_token"]

        # Mock Redis to return active token metadata
        jwt_manager.redis_client.hgetall = AsyncMock(
            return_value={"active": "true", "node_id": "test-client-2"}
        )

        # Validate the token
        validation_result = await jwt_manager.validate_token(token)

        # validate_token returns the decoded payload or None
        assert validation_result is not None
        assert validation_result["sub"] == "test-client-2"
        assert validation_result["node_type"] == "client"
        assert "connect" in validation_result["permissions"]
        assert validation_result["type"] == "access"

    @pytest.mark.asyncio
    async def test_validate_token_invalid(self, jwt_manager):
        """Test validation of an invalid token"""
        invalid_token = "invalid.token.here"

        validation_result = await jwt_manager.validate_token(invalid_token)

        # validate_token returns None for invalid tokens
        assert validation_result is None

    @pytest.mark.asyncio
    async def test_refresh_token(self, jwt_manager):
        """Test token refresh functionality"""
        # Generate initial token
        result = await jwt_manager.generate_token(
            node_id="test-client-3",
            node_type="client",
            permissions=["connect", "proxy"]
        )

        refresh_token = result["refresh_token"]

        # Mock Redis to validate the refresh token metadata
        jwt_manager.redis_client.hgetall = AsyncMock(
            return_value={"active": "true", "type": "refresh", "node_id": "test-client-3"}
        )

        # Refresh the token
        new_result = await jwt_manager.refresh_token(refresh_token)

        assert new_result is not None
        assert "access_token" in new_result
        assert "refresh_token" in new_result
        assert new_result["access_token"] != result["access_token"]  # Should be different

    @pytest.mark.asyncio
    async def test_token_expiry_calculation(self, jwt_manager):
        """Test token expiry time calculation via token claims"""
        # Generate a token and verify its exp claim
        now = datetime.now(timezone.utc)
        result = await jwt_manager.generate_token(
            node_id="test-expiry-client",
            node_type="client",
            permissions=["read"]
        )

        token = result["access_token"]

        # Decode token without verification to check exp claim
        decoded = pyjwt.decode(token, options={"verify_signature": False})

        # Token expiry should be approximately token_expiry_hours from now (24 hours default)
        exp_timestamp = decoded["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

        # Should be ~24 hours from now (within 2 minute tolerance for test execution)
        expected_exp = now + timedelta(hours=24)
        time_diff = abs((exp_datetime - expected_exp).total_seconds())
        assert time_diff < 120  # Within 2 minutes
        assert decoded["type"] == "access"
        assert decoded["sub"] == "test-expiry-client"