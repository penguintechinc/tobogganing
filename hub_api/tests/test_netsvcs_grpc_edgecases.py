"""Edge-case tests for the netsvcs gRPC ManagerServicer.

Complements tests/test_netsvcs_grpc*.py with: the _authenticate() helper's
invalid-token/aud-mismatch/insufficient-scope branches, RegisterServer's
cache-set and outer-exception branches, RefreshToken's full validation
chain (missing/invalid/wrong-type/subject-mismatch/aud-mismatch/
inactive-server/cache-read-error/replay-detected/minting-error/full
success), GetConfig's success + exception body, StreamConfigUpdates'
full generator body, SendHeartbeat's exception branch, ValidateToken's
not-found/expired/success/exception branches, CheckIOC's version/feature
gates, and create_grpc_server()'s successful TLS/mTLS/insecure paths.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import grpc
import pytest

from hub_api.modules.netsvcs.grpc.server import (
    ENROLLMENT_TENANT,
    ManagerServicer,
    _authenticate,
)
from hub_api.modules.netsvcs.managers.config_service import (
    DNSRecordDTO,
    DNSServerConfigDTO,
    DNSZoneDTO,
)
from proto.netsvcs.v1 import manager_pb2


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_cache() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_key_provider() -> Mock:
    provider = Mock()
    provider.kid = "test-key-id"
    provider.public_pem = b"-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----"
    return provider


@pytest.fixture
def servicer(mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock) -> ManagerServicer:
    return ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)


@pytest.fixture
def mock_context() -> MagicMock:
    context = MagicMock(spec=grpc.aio.ServicerContext)

    async def abort_impl(code: object, details: object) -> None:
        raise grpc.RpcError(f"gRPC abort: {code} {details}")

    context.abort = AsyncMock(side_effect=abort_impl)
    context.cancelled = MagicMock(return_value=False)
    context.invocation_metadata = Mock(return_value=[])
    return context


def _valid_config_dto() -> DNSServerConfigDTO:
    return DNSServerConfigDTO(
        zones=[
            DNSZoneDTO(
                id="zone-1",
                name="example.com",
                visibility="public",
                records=[DNSRecordDTO(name="www", type="A", value="1.2.3.4", ttl=300)],
            )
        ],
        cache_settings={"ttl": 300},
        settings={"ioc_filtering": True},
        version=1,
    )


# --- _authenticate() helper branches -----------------------------------------


@pytest.mark.asyncio
async def test_authenticate_invalid_token_aborts_unauthenticated(
    mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """_authenticate() aborts UNAUTHENTICATED when decode_token() returns None."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer garbage")])

    with patch("hub_api.modules.netsvcs.grpc.server.decode_token", return_value=None):
        with pytest.raises(grpc.RpcError):
            await _authenticate(mock_context, mock_key_provider, "dns:config:read")

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_authenticate_aud_mismatch_aborts_unauthenticated(
    mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """_authenticate() aborts UNAUTHENTICATED when the token audience isn't 'headend'."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])

    with patch(
        "hub_api.modules.netsvcs.grpc.server.decode_token",
        return_value={"aud": "wrong-audience", "scope": "dns:config:read"},
    ):
        with pytest.raises(grpc.RpcError):
            await _authenticate(mock_context, mock_key_provider, "dns:config:read")

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_authenticate_insufficient_scope_aborts_permission_denied(
    mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """_authenticate() aborts PERMISSION_DENIED when required scope is missing."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])

    with patch(
        "hub_api.modules.netsvcs.grpc.server.decode_token",
        return_value={"aud": "headend", "scope": "other:scope"},
    ):
        with pytest.raises(grpc.RpcError):
            await _authenticate(mock_context, mock_key_provider, "dns:config:read")

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_authenticate_success_returns_claims(
    mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """_authenticate() returns claims when token is valid with the required scope."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])

    with patch(
        "hub_api.modules.netsvcs.grpc.server.decode_token",
        return_value={"aud": "headend", "scope": "dns:config:read", "sub": "resolver:x"},
    ):
        claims = await _authenticate(mock_context, mock_key_provider, "dns:config:read")

    assert claims["sub"] == "resolver:x"
    mock_context.abort.assert_not_called()


# --- RegisterServer: cache failure + outer exception ------------------------


@pytest.mark.asyncio
async def test_register_server_continues_on_cache_set_failure(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RegisterServer logs and continues (still returns 201-equivalent) if cache.set fails."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-token")])
    mock_cache.set = AsyncMock(side_effect=RuntimeError("cache down"))

    mock_server_record = Mock()
    mock_server_record.id = "resolver-999"

    with (
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "valid-token"}),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
        patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS,
        patch("hub_api.modules.netsvcs.grpc.server.encode_access_token") as mock_encode,
    ):
        mock_sm = AsyncMock()
        mock_sm.register_server = AsyncMock(return_value=mock_server_record)
        MockSM.return_value = mock_sm

        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(return_value=_valid_config_dto())
        mock_cs.get_config_version = AsyncMock(return_value=1)
        MockCS.return_value = mock_cs

        mock_encode.side_effect = ["access-jwt", "refresh-jwt"]

        request = manager_pb2.RegisterServerRequest(
            api_version="v1", hostname="resolver1", version="1.0.0"
        )

        response = await servicer.RegisterServer(request, mock_context)

    assert response.jwt == "access-jwt"
    mock_context.abort.assert_not_called()


@pytest.mark.asyncio
async def test_register_server_outer_exception_aborts_internal(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RegisterServer aborts INTERNAL when server_manager.register_server raises."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-token")])

    with (
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "valid-token"}),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
    ):
        mock_sm = AsyncMock()
        mock_sm.register_server = AsyncMock(side_effect=RuntimeError("db down"))
        MockSM.return_value = mock_sm

        request = manager_pb2.RegisterServerRequest(
            api_version="v1", hostname="resolver1", version="1.0.0"
        )

        with pytest.raises(grpc.RpcError):
            await servicer.RegisterServer(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.INTERNAL


# --- RefreshToken: full validation chain -------------------------------------


def _refresh_request(server_id: str = "server-1") -> manager_pb2.RefreshTokenRequest:
    return manager_pb2.RefreshTokenRequest(api_version="v1", server_id=server_id)


@pytest.mark.asyncio
async def test_refresh_token_unknown_api_version_aborts_unimplemented(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNIMPLEMENTED for an unsupported api_version."""
    request = manager_pb2.RefreshTokenRequest(api_version="v9", server_id="server-1")

    with pytest.raises(grpc.RpcError):
        await servicer.RefreshToken(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_refresh_token_missing_token_aborts_unauthenticated(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAUTHENTICATED when no bearer token is present."""
    mock_context.invocation_metadata = Mock(return_value=[])

    with pytest.raises(grpc.RpcError):
        await servicer.RefreshToken(_refresh_request(), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_refresh_token_invalid_token_aborts_unauthenticated(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAUTHENTICATED when decode_token() returns None."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer garbage")])

    with patch("hub_api.modules.netsvcs.grpc.server.decode_token", return_value=None):
        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request(), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_refresh_token_wrong_type_aborts_unauthenticated(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAUTHENTICATED when token_type isn't 'refresh'."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])

    with patch(
        "hub_api.modules.netsvcs.grpc.server.decode_token",
        return_value={"token_type": "access"},
    ):
        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request(), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_refresh_token_subject_mismatch_aborts_unauthenticated(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAUTHENTICATED when sub doesn't match resolver:{server_id}."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])

    with patch(
        "hub_api.modules.netsvcs.grpc.server.decode_token",
        return_value={"token_type": "refresh", "sub": "resolver:OTHER"},
    ):
        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_refresh_token_aud_mismatch_aborts_unauthenticated(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAUTHENTICATED when aud isn't 'headend'."""
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])

    with patch(
        "hub_api.modules.netsvcs.grpc.server.decode_token",
        return_value={"token_type": "refresh", "sub": "resolver:server-1", "aud": "wrong"},
    ):
        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_refresh_token_server_not_active_aborts_unauthenticated(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAUTHENTICATED when the server isn't found or not online."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server.decode_token",
            return_value={"token_type": "refresh", "sub": "resolver:server-1", "aud": "headend"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
    ):
        mock_sm = AsyncMock()
        mock_sm.get_server = AsyncMock(return_value=None)
        MockSM.return_value = mock_sm

        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_refresh_token_cache_read_error_aborts_unavailable(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAVAILABLE (fail-closed) when the replay-check cache read errors."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])
    mock_cache.get = AsyncMock(side_effect=RuntimeError("cache down"))

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server.decode_token",
            return_value={"token_type": "refresh", "sub": "resolver:server-1", "aud": "headend"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
    ):
        mock_sm = AsyncMock()
        mock_sm.get_server = AsyncMock(return_value=Mock(status="online"))
        MockSM.return_value = mock_sm

        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAVAILABLE


@pytest.mark.asyncio
async def test_refresh_token_replay_detected_aborts_unauthenticated(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAUTHENTICATED and revokes the subject on jti replay."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])
    mock_cache.get = AsyncMock(return_value="cached-newer-jti")
    mock_cache.delete = AsyncMock()

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server.decode_token",
            return_value={
                "token_type": "refresh",
                "sub": "resolver:server-1",
                "aud": "headend",
                "jti": "stale-jti",
            },
        ),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
    ):
        mock_sm = AsyncMock()
        mock_sm.get_server = AsyncMock(return_value=Mock(status="online"))
        MockSM.return_value = mock_sm

        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED
    mock_cache.delete.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_token_replay_revocation_error_still_aborts(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RefreshToken still aborts on replay even if the revocation delete() itself fails."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])
    mock_cache.get = AsyncMock(return_value="cached-newer-jti")
    mock_cache.delete = AsyncMock(side_effect=RuntimeError("delete failed"))

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server.decode_token",
            return_value={
                "token_type": "refresh",
                "sub": "resolver:server-1",
                "aud": "headend",
                "jti": "stale-jti",
            },
        ),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
    ):
        mock_sm = AsyncMock()
        mock_sm.get_server = AsyncMock(return_value=Mock(status="online"))
        MockSM.return_value = mock_sm

        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_refresh_token_minting_error_aborts_internal(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RefreshToken aborts INTERNAL when new-token minting raises (logic error)."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])
    mock_cache.get = AsyncMock(return_value=None)

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server.decode_token",
            return_value={
                "token_type": "refresh",
                "sub": "resolver:server-1",
                "aud": "headend",
                "jti": "old-jti",
            },
        ),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
        patch(
            "hub_api.modules.netsvcs.grpc.server.encode_access_token",
            side_effect=RuntimeError("signing key unavailable"),
        ),
    ):
        mock_sm = AsyncMock()
        mock_sm.get_server = AsyncMock(return_value=Mock(status="online"))
        MockSM.return_value = mock_sm

        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.INTERNAL


@pytest.mark.asyncio
async def test_refresh_token_cache_set_error_aborts_unavailable(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RefreshToken aborts UNAVAILABLE (fail-closed) when caching the new jti fails."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(side_effect=RuntimeError("cache write failed"))

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server.decode_token",
            return_value={
                "token_type": "refresh",
                "sub": "resolver:server-1",
                "aud": "headend",
                "jti": "old-jti",
            },
        ),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
        patch(
            "hub_api.modules.netsvcs.grpc.server.encode_access_token",
            return_value="new-refresh-jwt",
        ),
    ):
        mock_sm = AsyncMock()
        mock_sm.get_server = AsyncMock(return_value=Mock(status="online"))
        MockSM.return_value = mock_sm

        with pytest.raises(grpc.RpcError):
            await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAVAILABLE


@pytest.mark.asyncio
async def test_refresh_token_full_success(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """RefreshToken returns a new jwt on the full success path (no replay, cache ok)."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer tok")])
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server.decode_token",
            return_value={
                "token_type": "refresh",
                "sub": "resolver:server-1",
                "aud": "headend",
                "jti": "old-jti",
            },
        ),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
        patch(
            "hub_api.modules.netsvcs.grpc.server.encode_access_token",
            return_value="brand-new-refresh-jwt",
        ),
    ):
        mock_sm = AsyncMock()
        mock_sm.get_server = AsyncMock(return_value=Mock(status="online"))
        MockSM.return_value = mock_sm

        response = await servicer.RefreshToken(_refresh_request("server-1"), mock_context)

    assert response.jwt == "brand-new-refresh-jwt"
    mock_context.abort.assert_not_called()


# --- GetConfig: success + exception body -------------------------------------


@pytest.mark.asyncio
async def test_get_config_success(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """GetConfig returns the assembled config + version on the success path."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server._authenticate",
            return_value={"sub": "resolver:server-1"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS,
    ):
        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(return_value=_valid_config_dto())
        mock_cs.get_config_version = AsyncMock(return_value=3)
        MockCS.return_value = mock_cs

        request = manager_pb2.GetConfigRequest(api_version="v1", server_id="server-1")
        response = await servicer.GetConfig(request, mock_context)

    assert response.version == 3
    assert len(response.config.zones) == 1


@pytest.mark.asyncio
async def test_get_config_exception_aborts_internal(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """GetConfig aborts INTERNAL when ConfigService raises."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server._authenticate",
            return_value={"sub": "resolver:server-1"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS,
    ):
        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(side_effect=RuntimeError("boom"))
        MockCS.return_value = mock_cs

        request = manager_pb2.GetConfigRequest(api_version="v1", server_id="server-1")
        with pytest.raises(grpc.RpcError):
            await servicer.GetConfig(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.INTERNAL


# --- StreamConfigUpdates: full generator body --------------------------------


@pytest.mark.asyncio
async def test_stream_config_updates_yields_full_then_cancels(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """StreamConfigUpdates yields an initial 'full' update, then returns on client cancel."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_context.cancelled = MagicMock(return_value=True)  # Cancel immediately after first yield

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server._authenticate",
            return_value={"sub": "resolver:server-1"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS,
    ):
        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(return_value=_valid_config_dto())
        mock_cs.get_config_version = AsyncMock(return_value=1)
        MockCS.return_value = mock_cs

        request = manager_pb2.StreamConfigUpdatesRequest(api_version="v1", server_id="server-1")

        updates = [u async for u in servicer.StreamConfigUpdates(request, mock_context)]

    assert len(updates) == 1
    assert updates[0].update_type == "full"


@pytest.mark.asyncio
async def test_stream_config_updates_yields_incremental_on_version_bump(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """StreamConfigUpdates yields an incremental update when the version bumps."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    # cancelled() False for first two checks (poll once, get bump), True after to stop the loop
    cancel_calls = [False, False, True]

    def cancelled_side_effect() -> bool:
        return cancel_calls.pop(0) if cancel_calls else True

    mock_context.cancelled = MagicMock(side_effect=cancelled_side_effect)

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server._authenticate",
            return_value={"sub": "resolver:server-1"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.asyncio.sleep", new_callable=AsyncMock),
        patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS,
    ):
        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(return_value=_valid_config_dto())
        # First call (initial yield) = version 1; poll call returns version 2 (bump)
        mock_cs.get_config_version = AsyncMock(side_effect=[1, 2])
        MockCS.return_value = mock_cs

        request = manager_pb2.StreamConfigUpdatesRequest(api_version="v1", server_id="server-1")

        updates = [u async for u in servicer.StreamConfigUpdates(request, mock_context)]

    assert [u.update_type for u in updates] == ["full", "incremental"]
    assert updates[1].version == 2


@pytest.mark.asyncio
async def test_stream_config_updates_exception_ends_stream_quietly(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """StreamConfigUpdates ends the generator (no raise) if ConfigService errors."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server._authenticate",
            return_value={"sub": "resolver:server-1"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS,
    ):
        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(side_effect=RuntimeError("boom"))
        MockCS.return_value = mock_cs

        request = manager_pb2.StreamConfigUpdatesRequest(api_version="v1", server_id="server-1")

        updates = [u async for u in servicer.StreamConfigUpdates(request, mock_context)]

    assert updates == []  # Stream ended cleanly, no items yielded


@pytest.mark.asyncio
async def test_stream_config_updates_unknown_version_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """StreamConfigUpdates aborts UNIMPLEMENTED for an unknown api_version."""
    request = manager_pb2.StreamConfigUpdatesRequest(api_version="v9", server_id="server-1")

    with pytest.raises(grpc.RpcError):
        async for _ in servicer.StreamConfigUpdates(request, mock_context):
            pass

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNIMPLEMENTED


# --- SendHeartbeat: exception branch -----------------------------------------


@pytest.mark.asyncio
async def test_send_heartbeat_exception_aborts_internal(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """SendHeartbeat aborts INTERNAL when record_heartbeat raises."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server._authenticate",
            return_value={"sub": "resolver:server-1"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM,
    ):
        mock_sm = AsyncMock()
        mock_sm.record_heartbeat = AsyncMock(side_effect=RuntimeError("boom"))
        MockSM.return_value = mock_sm

        request = manager_pb2.SendHeartbeatRequest(
            api_version="v1",
            server_id="server-1",
            metrics=manager_pb2.ServerMetrics(queries_total=1),
        )

        with pytest.raises(grpc.RpcError):
            await servicer.SendHeartbeat(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.INTERNAL


@pytest.mark.asyncio
async def test_send_heartbeat_unknown_version_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """SendHeartbeat aborts UNIMPLEMENTED for an unknown api_version."""
    request = manager_pb2.SendHeartbeatRequest(api_version="v9", server_id="server-1")

    with pytest.raises(grpc.RpcError):
        await servicer.SendHeartbeat(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_send_heartbeat_feature_disabled_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """SendHeartbeat aborts PERMISSION_DENIED when the netsvcs.dns flag is off."""
    request = manager_pb2.SendHeartbeatRequest(api_version="v1", server_id="server-1")

    with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=False):
        with pytest.raises(grpc.RpcError):
            await servicer.SendHeartbeat(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_send_heartbeat_subject_mismatch_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """SendHeartbeat aborts PERMISSION_DENIED when the machine-JWT subject mismatches."""
    request = manager_pb2.SendHeartbeatRequest(api_version="v1", server_id="server-1")

    with (
        patch(
            "hub_api.modules.netsvcs.grpc.server._authenticate",
            return_value={"sub": "resolver:OTHER"},
        ),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
    ):
        with pytest.raises(grpc.RpcError):
            await servicer.SendHeartbeat(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED


# --- ValidateToken: not found/expired/success/exception ----------------------


@pytest.mark.asyncio
async def test_validate_token_unknown_version_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """ValidateToken aborts UNIMPLEMENTED for an unknown api_version."""
    request = manager_pb2.ValidateTokenRequest(api_version="v9", token="tok")

    with pytest.raises(grpc.RpcError):
        await servicer.ValidateToken(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_validate_token_feature_disabled_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """ValidateToken aborts PERMISSION_DENIED when the netsvcs.dns flag is off."""
    request = manager_pb2.ValidateTokenRequest(api_version="v1", token="tok")

    with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=False):
        with pytest.raises(grpc.RpcError):
            await servicer.ValidateToken(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_validate_token_not_found(
    mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """ValidateToken returns valid=False when the token row doesn't exist.

    self.db(query) must be a *synchronous* call returning a query-builder
    (only .select()/.update() on it are awaited) — a plain MagicMock, not
    AsyncMock, models this correctly (AsyncMock.__call__ itself returns an
    unawaited coroutine, which breaks `.select()` on the result).
    """
    mock_db = MagicMock()
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    query_result = MagicMock()
    query_result.first = MagicMock(return_value=None)
    mock_db.return_value.select = AsyncMock(return_value=query_result)

    with (
        patch("hub_api.modules.netsvcs.grpc.server._authenticate", return_value={}),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
    ):
        request = manager_pb2.ValidateTokenRequest(api_version="v1", token="unknown-token")
        response = await servicer.ValidateToken(request, mock_context)

    assert response.valid is False
    assert "not found" in response.reason.lower()


@pytest.mark.asyncio
async def test_validate_token_expired(
    mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """ValidateToken returns valid=False when the token row is past expires_at."""
    mock_db = MagicMock()
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    token_row = Mock()
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    query_result = MagicMock()
    query_result.first = MagicMock(return_value=token_row)
    mock_db.return_value.select = AsyncMock(return_value=query_result)

    with (
        patch("hub_api.modules.netsvcs.grpc.server._authenticate", return_value={}),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
    ):
        request = manager_pb2.ValidateTokenRequest(api_version="v1", token="expired-token")
        response = await servicer.ValidateToken(request, mock_context)

    assert response.valid is False
    assert "expired" in response.reason.lower()


@pytest.mark.asyncio
async def test_validate_token_success_returns_zone_ids(
    mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """ValidateToken returns valid=True with the tenant's zone IDs and updates last_used."""
    mock_db = MagicMock()
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

    token_row = Mock()
    token_row.expires_at = None
    token_row.tenant = "tenant-x"
    token_row.id = "token-row-1"
    query_result = MagicMock()
    query_result.first = MagicMock(return_value=token_row)
    mock_db.return_value.select = AsyncMock(return_value=query_result)
    mock_db.return_value.update = AsyncMock()

    with (
        patch("hub_api.modules.netsvcs.grpc.server._authenticate", return_value={}),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS,
    ):
        mock_cs = AsyncMock()
        mock_cs.get_server_config = AsyncMock(return_value=_valid_config_dto())
        MockCS.return_value = mock_cs

        request = manager_pb2.ValidateTokenRequest(api_version="v1", token="good-token")
        response = await servicer.ValidateToken(request, mock_context)

    assert response.valid is True
    assert list(response.allowed_zone_ids) == ["zone-1"]


@pytest.mark.asyncio
async def test_validate_token_exception_returns_invalid_not_raise(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, mock_context: MagicMock
) -> None:
    """ValidateToken never exposes exception details; returns valid=False on error."""
    servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
    mock_db.side_effect = RuntimeError("db down")

    with (
        patch("hub_api.modules.netsvcs.grpc.server._authenticate", return_value={}),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
    ):
        request = manager_pb2.ValidateTokenRequest(api_version="v1", token="tok")
        response = await servicer.ValidateToken(request, mock_context)

    assert response.valid is False
    assert response.reason == "validation failed"


# --- CheckIOC: version + feature gates ---------------------------------------


@pytest.mark.asyncio
async def test_check_ioc_unknown_version_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """CheckIOC aborts UNIMPLEMENTED for an unknown api_version."""
    request = manager_pb2.CheckIOCRequest(api_version="v9", domain="x.com")

    with pytest.raises(grpc.RpcError):
        await servicer.CheckIOC(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_check_ioc_feature_disabled_aborts(
    servicer: ManagerServicer, mock_context: MagicMock
) -> None:
    """CheckIOC aborts PERMISSION_DENIED when the netsvcs.dns flag is off."""
    request = manager_pb2.CheckIOCRequest(api_version="v1", domain="x.com")

    with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=False):
        with pytest.raises(grpc.RpcError):
            await servicer.CheckIOC(request, mock_context)

    assert mock_context.abort.call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED


# --- create_grpc_server: successful TLS/mTLS/insecure paths ------------------


def _server_factory_with_stubbed_bind() -> object:
    """Return a patch target that builds a *real* grpc.aio.Server but stubs
    add_secure_port()/add_insecure_port() to avoid an actual TLS handshake /
    socket bind against throwaway fake cert bytes (grpc.ssl_server_credentials
    itself doesn't validate PEM content eagerly, but add_secure_port does).
    """
    import grpc as real_grpc

    real_server_factory = real_grpc.aio.server

    def fake_server_factory(*args: object, **kwargs: object) -> object:
        srv = real_server_factory(*args, **kwargs)
        srv.add_secure_port = MagicMock(return_value=50999)
        srv.add_insecure_port = MagicMock(return_value=50999)
        return srv

    return patch("grpc.aio.server", side_effect=fake_server_factory)


@pytest.mark.asyncio
async def test_create_grpc_server_tls_success(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, tmp_path: object
) -> None:
    """create_grpc_server() binds a secure port when valid cert/key files are provided."""
    from hub_api.modules.netsvcs.grpc.server import create_grpc_server

    cert_path = tmp_path / "cert.pem"  # type: ignore[operator]
    key_path = tmp_path / "key.pem"  # type: ignore[operator]
    cert_path.write_bytes(b"fake-cert-bytes")
    key_path.write_bytes(b"fake-key-bytes")

    with (
        patch.dict(
            os.environ,
            {
                "NETSVCS_GRPC_TLS_CERT_PATH": str(cert_path),
                "NETSVCS_GRPC_TLS_KEY_PATH": str(key_path),
            },
            clear=False,
        ),
        _server_factory_with_stubbed_bind(),
        patch("hub_api.modules.netsvcs.grpc.server.grpc.ssl_server_credentials") as mock_ssl_creds,
    ):
        mock_ssl_creds.return_value = Mock()

        server = await create_grpc_server(
            db=mock_db, cache=mock_cache, key_provider=mock_key_provider, port=50999, use_tls=True
        )

    assert server is not None
    mock_ssl_creds.assert_called_once()
    await server.stop(grace=None)


@pytest.mark.asyncio
async def test_create_grpc_server_mtls_client_ca(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, tmp_path: object
) -> None:
    """create_grpc_server() enables mTLS (require_client_auth) when a client CA is configured."""
    from hub_api.modules.netsvcs.grpc.server import create_grpc_server

    cert_path = tmp_path / "cert.pem"  # type: ignore[operator]
    key_path = tmp_path / "key.pem"  # type: ignore[operator]
    ca_path = tmp_path / "ca.pem"  # type: ignore[operator]
    cert_path.write_bytes(b"fake-cert-bytes")
    key_path.write_bytes(b"fake-key-bytes")
    ca_path.write_bytes(b"fake-ca-bytes")

    with (
        patch.dict(
            os.environ,
            {
                "NETSVCS_GRPC_TLS_CERT_PATH": str(cert_path),
                "NETSVCS_GRPC_TLS_KEY_PATH": str(key_path),
                "NETSVCS_GRPC_CLIENT_CA_PATH": str(ca_path),
            },
            clear=False,
        ),
        _server_factory_with_stubbed_bind(),
        patch("hub_api.modules.netsvcs.grpc.server.grpc.ssl_server_credentials") as mock_ssl_creds,
    ):
        mock_ssl_creds.return_value = Mock()

        server = await create_grpc_server(
            db=mock_db, cache=mock_cache, key_provider=mock_key_provider, port=50998, use_tls=True
        )

    call_kwargs = mock_ssl_creds.call_args.kwargs
    assert call_kwargs["require_client_auth"] is True
    await server.stop(grace=None)


@pytest.mark.asyncio
async def test_create_grpc_server_mtls_ca_file_missing_falls_back(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock, tmp_path: object
) -> None:
    """create_grpc_server() logs and continues without mTLS if the client CA file is missing."""
    from hub_api.modules.netsvcs.grpc.server import create_grpc_server

    cert_path = tmp_path / "cert.pem"  # type: ignore[operator]
    key_path = tmp_path / "key.pem"  # type: ignore[operator]
    cert_path.write_bytes(b"fake-cert-bytes")
    key_path.write_bytes(b"fake-key-bytes")

    with (
        patch.dict(
            os.environ,
            {
                "NETSVCS_GRPC_TLS_CERT_PATH": str(cert_path),
                "NETSVCS_GRPC_TLS_KEY_PATH": str(key_path),
                "NETSVCS_GRPC_CLIENT_CA_PATH": "/nonexistent/ca.pem",
            },
            clear=False,
        ),
        _server_factory_with_stubbed_bind(),
        patch("hub_api.modules.netsvcs.grpc.server.grpc.ssl_server_credentials") as mock_ssl_creds,
    ):
        mock_ssl_creds.return_value = Mock()

        server = await create_grpc_server(
            db=mock_db, cache=mock_cache, key_provider=mock_key_provider, port=50997, use_tls=True
        )

    call_kwargs = mock_ssl_creds.call_args.kwargs
    assert call_kwargs["require_client_auth"] is False
    await server.stop(grace=None)


@pytest.mark.asyncio
async def test_create_grpc_server_insecure_success(
    mock_db: AsyncMock, mock_cache: AsyncMock, mock_key_provider: Mock
) -> None:
    """create_grpc_server() binds an insecure port when explicitly opted in."""
    from hub_api.modules.netsvcs.grpc.server import create_grpc_server

    with patch.dict(os.environ, {"NETSVCS_GRPC_INSECURE": "1"}, clear=False):
        server = await create_grpc_server(
            db=mock_db,
            cache=mock_cache,
            key_provider=mock_key_provider,
            port=50996,
            use_tls=False,
        )

    assert server is not None
    await server.stop(grace=None)
