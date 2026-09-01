"""Additional coverage for hub_api.auth.service error/edge branches.

test_auth_service.py covers the main authenticate/MFA happy+basic-error paths;
this file fills in refresh_access_token, revoke_tokens, verify_and_enable_mfa,
disable_mfa, get_user_by_id error branches, and the teams-as-string claim path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import bcrypt
import pyotp
import pytest

from hub_api.auth.service import AuthService
from hub_api.config import Config
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.tests.conftest import make_mock_row, make_mock_rowset


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
    """Mock DB configured for auth tests (async penguin-dal API)."""
    db = MagicMock()

    def make_query_proxy() -> MagicMock:
        query_proxy = MagicMock()
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
        query_proxy.update = AsyncMock(return_value=0)
        query_proxy.delete = AsyncMock(return_value=0)
        query_proxy.__and__ = MagicMock(return_value=query_proxy)
        query_proxy.__or__ = MagicMock(return_value=query_proxy)
        return query_proxy

    def make_field_mock() -> MagicMock:
        field = MagicMock()
        field.__eq__ = MagicMock(return_value=make_query_proxy())
        return field

    users_table = MagicMock()
    users_table.id = make_field_mock()
    users_table.email = make_field_mock()
    users_table.async_insert = AsyncMock(return_value=1)

    refresh_tokens_table = MagicMock()
    refresh_tokens_table.user_id = make_field_mock()
    refresh_tokens_table.token = make_field_mock()
    refresh_tokens_table.async_insert = AsyncMock(return_value=1)

    db.users = users_table
    db.refresh_tokens = refresh_tokens_table
    default_query_proxy = make_query_proxy()
    db.__call__ = MagicMock(return_value=default_query_proxy)
    db.return_value = default_query_proxy

    return db


@pytest.mark.asyncio
async def test_authenticate_mfa_decrypt_failure_returns_error(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """authenticate() returns an MFA verification error when decrypt_secret raises."""
    password = "password123"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = make_mock_row(
        {
            "id": "user123",
            "email": "test@example.com",
            "password_hash": password_hash,
            "is_active": True,
            "mfa_enabled": True,
            "mfa_secret": "not-valid-ciphertext",
            "tenant": "tenant1",
            "role": "admin",
        }
    )
    users_rowset = make_mock_rowset([user])
    query_proxy = mock_db_for_auth(mock_db_for_auth.users.email == "test@example.com")
    query_proxy.select = AsyncMock(return_value=users_rowset)
    mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

    service = AuthService(mock_db_for_auth, test_config, key_provider)
    result = await service.authenticate("test@example.com", password, mfa_token="123456")

    assert result.success is False
    assert "MFA verification error" in result.error


@pytest.mark.asyncio
async def test_authenticate_swallows_unexpected_exception(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """authenticate() catches unexpected exceptions and returns a failure AuthResult."""
    query_proxy = mock_db_for_auth(mock_db_for_auth.users.email == "x")
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db down"))
    mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

    service = AuthService(mock_db_for_auth, test_config, key_provider)
    result = await service.authenticate("x@example.com", "pw")

    assert result.success is False
    assert "Authentication failed" in result.error


class TestRefreshAccessToken:
    """Tests for AuthService.refresh_access_token()."""

    @pytest.mark.asyncio
    async def test_invalid_token_not_found(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns error when the refresh token row doesn't exist."""
        query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.token == "x")
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.refresh_access_token("nonexistent")

        assert result.success is False
        assert "Invalid or revoked" in result.error

    @pytest.mark.asyncio
    async def test_replay_of_consumed_token_revokes_all_tokens(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """A refresh token with revoked_at already set is a replay.

        regression: security-review finding HIGH-A. The whole token family
        for that user must be revoked as a compromise response.
        """
        already_consumed = make_mock_row(
            {
                "user_id": "u1",
                "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                "revoked_at": datetime.now(timezone.utc) - timedelta(minutes=5),
            }
        )
        query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.token == "x")
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([already_consumed]))
        query_proxy.delete = AsyncMock(return_value=None)
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.refresh_access_token("replayed-token")

        assert result.success is False
        assert "Invalid or revoked" in result.error
        query_proxy.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_token_string_format(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns error when the refresh token is expired (ISO string expires_at)."""
        expired_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        rt_record = make_mock_row({"user_id": "u1", "expires_at": expired_iso, "revoked_at": None})
        query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.token == "x")
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([rt_record]))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.refresh_access_token("expired-token")

        assert result.success is False
        assert "expired" in result.error.lower()

    @pytest.mark.asyncio
    async def test_expired_token_naive_datetime(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns error when expires_at is a naive (tz-less) datetime in the past."""
        expired_naive = datetime.utcnow() - timedelta(hours=1)
        rt_record = make_mock_row(
            {"user_id": "u1", "expires_at": expired_naive, "revoked_at": None}
        )
        query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.token == "x")
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([rt_record]))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.refresh_access_token("expired-token")

        assert result.success is False
        assert "expired" in result.error.lower()

    @pytest.mark.asyncio
    async def test_user_not_found(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns error when the refresh token's user no longer exists."""
        future = datetime.now(timezone.utc) + timedelta(days=1)
        rt_record = make_mock_row({"user_id": "u1", "expires_at": future, "revoked_at": None})

        call_count = {"n": 0}

        def select_side_effect(*args: object, **kwargs: object) -> object:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return make_mock_rowset([rt_record])
            return make_mock_rowset([])

        query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.token == "x")
        query_proxy.select = AsyncMock(side_effect=select_side_effect)
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.refresh_access_token("valid-token")

        assert result.success is False
        assert "User not found or inactive" in result.error

    @pytest.mark.asyncio
    async def test_inactive_user_rejected(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns error when the refresh token's user is inactive."""
        future = datetime.now(timezone.utc) + timedelta(days=1)
        rt_record = make_mock_row({"user_id": "u1", "expires_at": future, "revoked_at": None})
        inactive_user = make_mock_row({"id": "u1", "is_active": False, "role": "viewer"})

        call_count = {"n": 0}

        def select_side_effect(*args: object, **kwargs: object) -> object:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return make_mock_rowset([rt_record])
            return make_mock_rowset([inactive_user])

        query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.token == "x")
        query_proxy.select = AsyncMock(side_effect=select_side_effect)
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.refresh_access_token("valid-token")

        assert result.success is False
        assert "User not found or inactive" in result.error

    @pytest.mark.asyncio
    async def test_swallows_unexpected_exception(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Catches unexpected exceptions and returns a failure AuthResult."""
        query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.token == "x")
        query_proxy.select = AsyncMock(side_effect=RuntimeError("db down"))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.refresh_access_token("token")

        assert result.success is False
        assert "Token refresh failed" in result.error


@pytest.mark.asyncio
async def test_revoke_tokens_success(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """revoke_tokens() returns True on success."""
    service = AuthService(mock_db_for_auth, test_config, key_provider)
    result = await service.revoke_tokens("u1")
    assert result is True


@pytest.mark.asyncio
async def test_revoke_tokens_swallows_exception(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """revoke_tokens() returns False when delete() raises."""
    query_proxy = mock_db_for_auth(mock_db_for_auth.refresh_tokens.user_id == "u1")
    query_proxy.delete = AsyncMock(side_effect=RuntimeError("db down"))
    mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

    service = AuthService(mock_db_for_auth, test_config, key_provider)
    result = await service.revoke_tokens("u1")

    assert result is False


class TestVerifyAndEnableMfa:
    """Tests for AuthService.verify_and_enable_mfa()."""

    @pytest.mark.asyncio
    async def test_user_not_found_returns_false(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns False when the target user doesn't exist."""
        secret = pyotp.random_base32()
        token = pyotp.TOTP(secret).now()

        query_proxy = mock_db_for_auth(mock_db_for_auth.users.id == "missing")
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.verify_and_enable_mfa("missing", secret, token)

        assert result is False

    @pytest.mark.asyncio
    async def test_swallows_unexpected_exception(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns False when the DB query raises unexpectedly."""
        secret = pyotp.random_base32()
        token = pyotp.TOTP(secret).now()

        query_proxy = mock_db_for_auth(mock_db_for_auth.users.id == "u1")
        query_proxy.select = AsyncMock(side_effect=RuntimeError("db down"))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.verify_and_enable_mfa("u1", secret, token)

        assert result is False


@pytest.mark.asyncio
async def test_disable_mfa_success(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """disable_mfa() returns True on success."""
    service = AuthService(mock_db_for_auth, test_config, key_provider)
    result = await service.disable_mfa("u1")
    assert result is True


@pytest.mark.asyncio
async def test_disable_mfa_swallows_exception(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """disable_mfa() returns False when update() raises."""
    query_proxy = mock_db_for_auth(mock_db_for_auth.users.id == "u1")
    query_proxy.update = AsyncMock(side_effect=RuntimeError("db down"))
    mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

    service = AuthService(mock_db_for_auth, test_config, key_provider)
    result = await service.disable_mfa("u1")

    assert result is False


class TestGetUserById:
    """Tests for AuthService.get_user_by_id()."""

    @pytest.mark.asyncio
    async def test_returns_dict_on_success(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns a plain dict with the expected fields."""
        user_row = make_mock_row(
            {
                "id": "u1",
                "email": "a@example.com",
                "username": "alice",
                "is_active": True,
                "mfa_enabled": False,
                "tenant": "t1",
                "role": "viewer",
                "teams": ["team1"],
            }
        )
        query_proxy = mock_db_for_auth(mock_db_for_auth.users.id == "u1")
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([user_row]))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.get_user_by_id("u1")

        assert result == {
            "id": "u1",
            "email": "a@example.com",
            "username": "alice",
            "is_active": True,
            "mfa_enabled": False,
            "tenant": "t1",
            "role": "viewer",
            "teams": ["team1"],
        }

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns None when the user doesn't exist."""
        query_proxy = mock_db_for_auth(mock_db_for_auth.users.id == "missing")
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.get_user_by_id("missing")

        assert result is None

    @pytest.mark.asyncio
    async def test_swallows_unexpected_exception(
        self, mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
    ) -> None:
        """Returns None when the DB query raises unexpectedly."""
        query_proxy = mock_db_for_auth(mock_db_for_auth.users.id == "u1")
        query_proxy.select = AsyncMock(side_effect=RuntimeError("db down"))
        mock_db_for_auth.__call__ = MagicMock(return_value=query_proxy)

        service = AuthService(mock_db_for_auth, test_config, key_provider)
        result = await service.get_user_by_id("u1")

        assert result is None


@pytest.mark.asyncio
async def test_generate_access_token_splits_string_teams(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """_generate_access_token() splits a comma-separated string teams field into a list."""
    from hub_api.auth.jwt import decode_token

    user = MagicMock(id="u1", tenant="t1", role="viewer", teams="team1,team2")

    service = AuthService(mock_db_for_auth, test_config, key_provider)
    token = await service._generate_access_token(user)

    claims = decode_token(token, key_provider)
    assert claims["teams"] == ["team1", "team2"]


@pytest.mark.asyncio
async def test_generate_access_token_empty_string_teams(
    mock_db_for_auth: MagicMock, test_config: Config, key_provider: InAppKeyProvider
) -> None:
    """_generate_access_token() converts an empty string teams field to an empty list."""
    from hub_api.auth.jwt import decode_token

    user = MagicMock(id="u1", tenant="t1", role="viewer", teams="")

    service = AuthService(mock_db_for_auth, test_config, key_provider)
    token = await service._generate_access_token(user)

    claims = decode_token(token, key_provider)
    assert claims["teams"] == []
