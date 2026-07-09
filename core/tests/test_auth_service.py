"""Tests for the unified authentication service."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import bcrypt
import pytest
import pyotp

from core.auth.service import AuthService
from core.config import Config
from core.crypto import InAppKeyProvider, generate_rsa_key_pair
from core.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def key_provider() -> InAppKeyProvider:
    """Provide a test key provider."""
    private_pem, public_pem = generate_rsa_key_pair()
    return InAppKeyProvider(private_pem, public_pem)


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
def mock_db_for_auth() -> MagicMock:
    """Provide a mock database configured for auth tests."""
    db = MagicMock()

    # Mock users table
    users_table = MagicMock()
    refresh_tokens_table = MagicMock()

    db.users = users_table
    db.refresh_tokens = refresh_tokens_table

    return db


class TestAuthServiceAuthenticate:
    """Test authentication functionality."""

    def test_authenticate_valid_credentials(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test successful authentication with valid credentials."""
        password = "password123"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        user = make_mock_row({
            "id": "user123",
            "email": "test@example.com",
            "username": "testuser",
            "password_hash": password_hash,
            "is_active": True,
            "mfa_enabled": False,
            "tenant": "tenant1",
            "role": "admin",
            "teams": ["team1"],
        })

        # Mock the select call
        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset

        # Mock refresh token storage
        mock_db_for_auth.refresh_tokens.insert.return_value = 1

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        result = auth_service.authenticate("test@example.com", password)

        assert result.success is True
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.mfa_required is False

    def test_authenticate_invalid_email(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test authentication with non-existent email."""
        # Mock empty result
        users_rowset = make_mock_rowset([])
        mock_db_for_auth.users.select.return_value = users_rowset

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        result = auth_service.authenticate("nonexistent@example.com", "password")

        assert result.success is False
        assert result.error is not None

    def test_authenticate_invalid_password(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test authentication with wrong password."""
        user = make_mock_row({
            "id": "user123",
            "email": "test@example.com",
            "username": "testuser",
            "password_hash": bcrypt.hashpw(b"correctpassword", bcrypt.gensalt()).decode("utf-8"),
            "is_active": True,
            "mfa_enabled": False,
            "tenant": "tenant1",
            "role": "admin",
            "teams": ["team1"],
        })

        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        result = auth_service.authenticate("test@example.com", "wrongpassword")

        assert result.success is False
        assert result.error is not None

    def test_authenticate_inactive_user(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test authentication with inactive user."""
        password = "password123"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        user = make_mock_row({
            "id": "user123",
            "email": "test@example.com",
            "username": "testuser",
            "password_hash": password_hash,
            "is_active": False,
            "mfa_enabled": False,
            "tenant": "tenant1",
            "role": "admin",
            "teams": ["team1"],
        })

        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        result = auth_service.authenticate("test@example.com", password)

        assert result.success is False
        assert result.error is not None

    def test_authenticate_mfa_enabled_without_token(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test authentication with MFA enabled but no MFA token provided."""
        password = "password123"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        user = make_mock_row({
            "id": "user123",
            "email": "test@example.com",
            "username": "testuser",
            "password_hash": password_hash,
            "is_active": True,
            "mfa_enabled": True,
            "mfa_secret": "JBSWY3DPEBLW64TMMQ======",
            "tenant": "tenant1",
            "role": "admin",
            "teams": ["team1"],
        })

        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        result = auth_service.authenticate("test@example.com", password)

        assert result.mfa_required is True
        assert result.mfa_token is not None

    def test_authenticate_mfa_enabled_with_valid_token(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test authentication with MFA enabled and valid TOTP token."""
        password = "password123"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create a valid TOTP secret
        secret = "JBSWY3DPEBLW64TMMQ======"
        totp = pyotp.TOTP(secret)
        current_token = totp.now()

        user = make_mock_row({
            "id": "user123",
            "email": "test@example.com",
            "username": "testuser",
            "password_hash": password_hash,
            "is_active": True,
            "mfa_enabled": True,
            "mfa_secret": secret,
            "tenant": "tenant1",
            "role": "admin",
            "teams": ["team1"],
        })

        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset
        mock_db_for_auth.refresh_tokens.insert.return_value = 1

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        result = auth_service.authenticate("test@example.com", password, mfa_token=current_token)

        assert result.success is True
        assert result.access_token is not None


class TestAuthServiceTokenClaims:
    """Test that tokens include correct claims."""

    def test_access_token_includes_all_claims(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test that access token includes all required claims."""
        from core.auth.jwt import decode_token

        password = "password123"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        user = make_mock_row({
            "id": "user123",
            "email": "test@example.com",
            "username": "testuser",
            "password_hash": password_hash,
            "is_active": True,
            "mfa_enabled": False,
            "tenant": "tenant1",
            "role": "maintainer",
            "teams": ["team1", "team2"],
        })

        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset
        mock_db_for_auth.refresh_tokens.insert.return_value = 1

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        result = auth_service.authenticate("test@example.com", password)

        assert result.success is True

        # Decode and verify claims
        claims = decode_token(result.access_token, key_provider)

        assert claims is not None
        assert claims["sub"] == "user123"
        assert claims["tenant"] == "tenant1"
        assert claims["iss"] == "test-app"
        assert claims["aud"] == "test-app"
        assert "*:read" in claims["scope"]
        assert "*:write" in claims["scope"]
        assert "maintainer" in claims["roles"]
        assert "team1" in claims["teams"]
        assert "team2" in claims["teams"]


class TestAuthServiceMFA:
    """Test MFA setup and verification."""

    def test_setup_mfa_returns_secret_and_codes(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test that setup_mfa returns a secret and backup codes."""
        user = make_mock_row({
            "id": "user123",
            "email": "test@example.com",
        })

        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        secret, backup_codes = auth_service.setup_mfa("user123")

        assert isinstance(secret, str)
        assert len(secret) > 0
        assert isinstance(backup_codes, list)
        assert len(backup_codes) == 10

    def test_verify_and_enable_mfa_with_valid_token(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test enabling MFA with a valid TOTP token."""
        secret = "JBSWY3DPEBLW64TMMQ======"
        totp = pyotp.TOTP(secret)
        current_token = totp.now()

        user = make_mock_row({"id": "user123"})
        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        success = auth_service.verify_and_enable_mfa("user123", secret, current_token)

        assert success is True
        mock_db_for_auth.users.update.assert_called()

    def test_verify_and_enable_mfa_with_invalid_token(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test that enabling MFA fails with invalid TOTP token."""
        secret = "JBSWY3DPEBLW64TMMQ======"

        user = make_mock_row({"id": "user123"})
        users_rowset = make_mock_rowset([user])
        mock_db_for_auth.users.select.return_value = users_rowset

        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        success = auth_service.verify_and_enable_mfa("user123", secret, "000000")

        assert success is False


class TestAuthServiceDisableMFA:
    """Test MFA disabling."""

    def test_disable_mfa(
        self,
        mock_db_for_auth: MagicMock,
        test_config: Config,
        key_provider: InAppKeyProvider,
    ) -> None:
        """Test disabling MFA for a user."""
        auth_service = AuthService(mock_db_for_auth, test_config, key_provider)

        success = auth_service.disable_mfa("user123")

        assert success is True
        mock_db_for_auth.users.update.assert_called()


def test_verify_and_enable_mfa_stores_encrypted_secret(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: Any
) -> None:
    """Test that verify_and_enable_mfa encrypts the secret before storing."""
    service = AuthService(mock_db_for_auth, test_config, key_provider)

    user_id = "test-user-123"
    secret = pyotp.random_base32()  # Generate a real TOTP secret
    totp = pyotp.TOTP(secret)
    mfa_token = totp.now()

    # Mock user lookup
    user_row = make_mock_row({"id": user_id})
    mock_db_for_auth.users.select = MagicMock(return_value=user_row)
    mock_db_for_auth.users.update = MagicMock(return_value=None)

    result = service.verify_and_enable_mfa(user_id, secret, mfa_token)

    assert result is True

    # Verify that update was called with mfa_enabled=True
    mock_db_for_auth.users.update.assert_called_once()
    call_kwargs = mock_db_for_auth.users.update.call_args[1]

    # The stored secret should be encrypted (not plaintext)
    stored_secret = call_kwargs["mfa_secret"]
    assert stored_secret != secret, "Secret should be encrypted, not plaintext"
    assert call_kwargs["mfa_enabled"] is True


def test_authenticate_with_mfa_decrypts_secret(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: Any
) -> None:
    """Test that authenticate decrypts the MFA secret for verification."""
    from core.crypto.secrets import encrypt_secret

    service = AuthService(mock_db_for_auth, test_config, key_provider)

    # Generate a real TOTP secret and encrypt it
    plaintext_secret = pyotp.random_base32()
    encrypted_secret = encrypt_secret(plaintext_secret)

    # Generate a valid MFA token
    totp = pyotp.TOTP(plaintext_secret)
    valid_mfa_token = totp.now()

    password = "test-password"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )

    # Mock user with encrypted MFA secret
    user_row = make_mock_row(
        {
            "id": "user-123",
            "email": "test@example.com",
            "password_hash": password_hash,
            "is_active": True,
            "mfa_enabled": True,
            "mfa_secret": encrypted_secret,
            "role": "admin",
            "tenant": "test-tenant",
        }
    )

    mock_db_for_auth.users.select = MagicMock(return_value=user_row)
    mock_db_for_auth.refresh_tokens = MagicMock()

    result = service.authenticate("test@example.com", password, mfa_token=valid_mfa_token)

    # Should successfully authenticate with valid MFA token
    assert result.success is True
    assert result.access_token is not None


def test_authenticate_with_mfa_rejects_invalid_token(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: Any
) -> None:
    """Test that authenticate rejects invalid MFA tokens."""
    from core.crypto.secrets import encrypt_secret

    service = AuthService(mock_db_for_auth, test_config, key_provider)

    # Encrypt a secret
    plaintext_secret = pyotp.random_base32()
    encrypted_secret = encrypt_secret(plaintext_secret)

    password = "test-password"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )

    user_row = make_mock_row(
        {
            "id": "user-123",
            "email": "test@example.com",
            "password_hash": password_hash,
            "is_active": True,
            "mfa_enabled": True,
            "mfa_secret": encrypted_secret,
            "role": "admin",
            "tenant": "test-tenant",
        }
    )

    mock_db_for_auth.users.select = MagicMock(return_value=user_row)

    # Attempt auth with invalid MFA token
    result = service.authenticate("test@example.com", password, mfa_token="000000")

    # Should fail with invalid MFA token
    assert result.success is False
    assert "Invalid MFA token" in result.error
