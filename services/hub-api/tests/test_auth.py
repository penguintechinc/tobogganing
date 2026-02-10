"""
Basic unit tests for Manager Service authentication components
"""
import pytest
import asyncio
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from manager.auth.jwt_manager import JWTManager


class TestJWTManager:
    """Test JWT token management functionality"""
    
    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager instance for testing"""
        return JWTManager()
    
    def test_jwt_manager_initialization(self, jwt_manager):
        """Test JWT manager initializes correctly"""
        assert jwt_manager is not None
        assert hasattr(jwt_manager, 'private_key')
        assert hasattr(jwt_manager, 'public_key')
    
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
        
        # Validate the token
        validation_result = await jwt_manager.validate_token(token)
        
        assert validation_result["valid"] is True
        assert validation_result["claims"]["node_id"] == "test-client-2"
        assert validation_result["claims"]["node_type"] == "client"
        assert "connect" in validation_result["claims"]["permissions"]
    
    @pytest.mark.asyncio
    async def test_validate_token_invalid(self, jwt_manager):
        """Test validation of an invalid token"""
        invalid_token = "invalid.token.here"
        
        validation_result = await jwt_manager.validate_token(invalid_token)
        
        assert validation_result["valid"] is False
        assert "error" in validation_result
    
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
        
        # Refresh the token
        new_result = await jwt_manager.refresh_token(refresh_token)
        
        assert "access_token" in new_result
        assert "refresh_token" in new_result
        assert new_result["access_token"] != result["access_token"]  # Should be different
    
    def test_token_expiry_calculation(self, jwt_manager):
        """Test token expiry time calculation"""
        now = datetime.utcnow()
        expires_in = 3600  # 1 hour
        
        expiry = jwt_manager._calculate_expiry(expires_in)
        
        # Should be approximately 1 hour from now
        expected = now + timedelta(seconds=expires_in)
        difference = abs((expiry - expected).total_seconds())
        assert difference < 60  # Within 1 minute tolerance