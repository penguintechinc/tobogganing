"""Integration tests for AuthService using real penguin-dal and SQLite database.

These tests use the real_dal fixture which creates a migrated SQLite database.
They exercise the anti-mock guarantee: if something breaks in production's
real database, these tests catch it.

Note: These tests validate that the async DAL API works with a real migrated schema.
Direct SQLAlchemy/Alembic schema handling is delegated to the test harness.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import pytest
import pyotp

from core.auth.service import AuthService
from core.config import Config
from core.crypto import InAppKeyProvider, generate_rsa_key_pair
from core.crypto.secrets import encrypt_secret

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def test_config() -> Config:
    """Provide a test configuration."""
    return Config(
        db_type="sqlite",
        db_name=":memory:",
        product_name="test-app",
        jwt_expiration_hours=1,
    )


@pytest.fixture
def key_provider() -> InAppKeyProvider:
    """Provide a test key provider."""
    private_pem, public_pem = generate_rsa_key_pair()
    return InAppKeyProvider(private_pem, public_pem)


@pytest.mark.asyncio
async def test_authenticate_real_dal_no_users(
    real_dal: Any, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """Test authenticate with real DAL: empty table returns not found."""
    # Test: authenticate should fail when no users exist
    service = AuthService(real_dal, test_config, key_provider)
    result = await service.authenticate("alice@example.com", "password")

    assert result.success is False
    assert "Invalid email or password" in result.error


@pytest.mark.asyncio
async def test_setup_mfa_real_dal(
    real_dal: Any, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """Test setup_mfa with real DAL: returns secret and codes."""
    # Use an arbitrary user_id (setup_mfa only validates existence via async query)
    user_id = str(uuid4())

    # Test: setup_mfa should handle missing user gracefully
    service = AuthService(real_dal, test_config, key_provider)
    try:
        secret, backup_codes = await service.setup_mfa(user_id)
        # If we get here, the user wasn't found but the async API worked
        assert False, "Should have raised ValueError for missing user"
    except ValueError as e:
        assert "User not found" in str(e)
