"""Tests for netsvcs gRPC manager service."""
from __future__ import annotations

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import grpc

from proto.netsvcs.v1 import manager_pb2, manager_pb2_grpc
from hub_api.modules.netsvcs.grpc.server import (
    ManagerServicer,
    ENROLLMENT_TENANT,
    _authenticate,
    _extract_bearer_token_from_metadata,
    _verify_bootstrap_token,
)
from hub_api.modules.netsvcs.managers.config_service import (
    DNSServerConfigDTO,
    DNSZoneDTO,
    DNSRecordDTO,
)


@pytest.fixture
def mock_db():
    """Create a mock penguin-dal database."""
    return AsyncMock()


@pytest.fixture
def mock_cache():
    """Create a mock CacheClient."""
    return AsyncMock()


@pytest.fixture
def mock_key_provider():
    """Create a mock KeyProvider."""
    provider = Mock()
    provider.kid = "test-key-id"
    provider.public_pem = b"-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----"
    return provider


@pytest.fixture
def servicer(mock_db, mock_cache, mock_key_provider):
    """Create a ManagerServicer instance with mocks."""
    return ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)


@pytest.fixture
def mock_context():
    """Create a mock gRPC context that properly raises on abort."""
    context = MagicMock(spec=grpc.aio.ServicerContext)

    async def abort_impl(code, details):
        raise grpc.RpcError(f"gRPC abort: {code} {details}")

    context.abort = AsyncMock(side_effect=abort_impl)
    context.cancelled = MagicMock(return_value=False)
    context.invocation_metadata = Mock(return_value=[])
    return context


class TestApiVersionRouting:
    """Test api_version routing on all RPCs."""

    @pytest.mark.asyncio
    async def test_register_server_unknown_version(self, servicer, mock_context):
        """Unknown api_version should abort with UNIMPLEMENTED."""
        request = manager_pb2.RegisterServerRequest(
            api_version="v2",
            hostname="resolver1",
            version="1.0.0",
        )

        with pytest.raises(grpc.RpcError):
            await servicer.RegisterServer(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.UNIMPLEMENTED

    @pytest.mark.asyncio
    async def test_get_config_unknown_version(self, servicer, mock_context):
        """Unknown api_version should abort with UNIMPLEMENTED."""
        request = manager_pb2.GetConfigRequest(
            api_version="v3",
            server_id="test-server",
        )

        with pytest.raises(grpc.RpcError):
            await servicer.GetConfig(request, mock_context)

        mock_context.abort.assert_called_once()


class TestAuthenticationHelpers:
    """Test auth token extraction and verification utilities."""

    def test_extract_bearer_token_valid(self):
        """_extract_bearer_token_from_metadata should extract token from Authorization header."""
        mock_context = MagicMock()
        mock_context.invocation_metadata = Mock(
            return_value=[("authorization", "Bearer test-token-123")]
        )

        token = _extract_bearer_token_from_metadata(mock_context)
        assert token == "test-token-123"

    def test_extract_bearer_token_missing(self):
        """_extract_bearer_token_from_metadata should return None if no Authorization header."""
        mock_context = MagicMock()
        mock_context.invocation_metadata = Mock(return_value=[])

        token = _extract_bearer_token_from_metadata(mock_context)
        assert token is None

    def test_verify_bootstrap_token_valid(self):
        """_verify_bootstrap_token should return True for matching token."""
        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "secret-bootstrap-token"}):
            result = _verify_bootstrap_token("secret-bootstrap-token")
            assert result is True

    def test_verify_bootstrap_token_invalid(self):
        """_verify_bootstrap_token should return False for non-matching token."""
        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "secret-bootstrap-token"}):
            result = _verify_bootstrap_token("wrong-token")
            assert result is False


class TestRegisterServerAuthentication:
    """Test RegisterServer bootstrap token validation (M1 fix)."""

    @pytest.mark.asyncio
    async def test_register_server_missing_bootstrap_token(self, servicer, mock_context):
        """RegisterServer should abort UNAUTHENTICATED if bootstrap token missing."""
        mock_context.invocation_metadata = Mock(return_value=[])

        request = manager_pb2.RegisterServerRequest(
            api_version="v1",
            hostname="resolver1",
            version="1.0.0",
        )

        with pytest.raises(grpc.RpcError):
            await servicer.RegisterServer(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED

    @pytest.mark.asyncio
    async def test_register_server_invalid_bootstrap_token(self, servicer, mock_context):
        """RegisterServer should abort UNAUTHENTICATED if bootstrap token invalid."""
        mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer wrong-token")])

        request = manager_pb2.RegisterServerRequest(
            api_version="v1",
            hostname="resolver1",
            version="1.0.0",
        )

        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "correct-token"}):
            with pytest.raises(grpc.RpcError):
                await servicer.RegisterServer(request, mock_context)

            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


class TestRegisterServerRefreshToken:
    """Test RegisterServer refresh token issuance (M3, M2 fixes)."""

    @pytest.mark.asyncio
    async def test_register_server_returns_refresh_token(self, mock_db, mock_cache, mock_key_provider, mock_context):
        """RegisterServer should return both access and refresh tokens (M3)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-token")])

        # Mock register_server to return a server record
        mock_server_record = Mock()
        mock_server_record.id = "resolver-123"

        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "valid-token"}), \
             patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM, \
             patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS, \
             patch("hub_api.modules.netsvcs.grpc.server.encode_access_token") as mock_encode:

            mock_sm = AsyncMock()
            mock_sm.register_server = AsyncMock(return_value=mock_server_record)
            MockSM.return_value = mock_sm

            mock_cs = AsyncMock()
            mock_cs.get_server_config = AsyncMock(return_value=DNSServerConfigDTO())
            mock_cs.get_config_version = AsyncMock(return_value=1)
            MockCS.return_value = mock_cs

            # Mock token encoding to return distinct tokens
            mock_encode.side_effect = ["access-jwt-token", "refresh-jwt-token"]

            request = manager_pb2.RegisterServerRequest(
                api_version="v1",
                hostname="resolver1",
                version="1.0.0",
            )

            response = await servicer.RegisterServer(request, mock_context)

            # M3: Response should include both jwt and refresh_token
            assert response.jwt == "access-jwt-token"
            assert response.refresh_token == "refresh-jwt-token"
            assert response.server_id == "resolver-123"

    @pytest.mark.asyncio
    async def test_register_server_caches_refresh_jti(self, mock_db, mock_cache, mock_key_provider, mock_context):
        """RegisterServer should cache refresh token JTI for single-use (M2)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-token")])

        # Mock register_server to return a server record
        mock_server_record = Mock()
        mock_server_record.id = "resolver-123"

        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "valid-token"}), \
             patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM, \
             patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS, \
             patch("hub_api.modules.netsvcs.grpc.server.encode_access_token") as mock_encode:

            mock_sm = AsyncMock()
            mock_sm.register_server = AsyncMock(return_value=mock_server_record)
            MockSM.return_value = mock_sm

            mock_cs = AsyncMock()
            mock_cs.get_server_config = AsyncMock(return_value=DNSServerConfigDTO())
            mock_cs.get_config_version = AsyncMock(return_value=1)
            MockCS.return_value = mock_cs

            # Mock token encoding
            mock_encode.side_effect = ["access-jwt-token", "refresh-jwt-token"]

            # Track the claims built in encode_access_token to get the refresh JTI
            refresh_jti = "test-refresh-jti-123"

            request = manager_pb2.RegisterServerRequest(
                api_version="v1",
                hostname="resolver1",
                version="1.0.0",
            )

            response = await servicer.RegisterServer(request, mock_context)

            # M2: Cache should have been set with the refresh JTI
            mock_cache.set.assert_called_once()
            call_args = mock_cache.set.call_args
            assert call_args[0][0] == "auth"
            assert call_args[0][1] == "refresh"
            assert call_args[0][2] == "resolver:resolver-123"


class TestSendHeartbeatSignature:
    """Test SendHeartbeat call signature fix (H2)."""

    @pytest.mark.asyncio
    async def test_send_heartbeat_calls_record_heartbeat_with_positional_args(
        self, mock_db, mock_cache, mock_key_provider, mock_context
    ):
        """SendHeartbeat should call record_heartbeat with positional args (H2 fix)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
        servicer.key_provider = mock_key_provider

        # Mock authentication
        with patch("hub_api.modules.netsvcs.grpc.server._authenticate") as mock_auth, \
             patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature, \
             patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM, \
             patch("hub_api.modules.netsvcs.grpc.server.ConfigService") as MockCS:

            mock_auth.return_value = {
                "sub": "resolver:test-server",
                "aud": "headend",
                "scope": "metrics:write",
            }
            mock_feature.return_value = True

            mock_sm = AsyncMock()
            mock_sm.record_heartbeat = AsyncMock(return_value=True)
            MockSM.return_value = mock_sm

            mock_cs = AsyncMock()
            mock_cs.get_config_version = AsyncMock(return_value=5)
            MockCS.return_value = mock_cs

            request = manager_pb2.SendHeartbeatRequest(
                api_version="v1",
                server_id="test-server",
                timestamp=1234567890,
                metrics=manager_pb2.ServerMetrics(
                    queries_total=1000,
                    cache_hits=900,
                    errors=10,
                    avg_response_ms=5.5,
                    queries_by_type={},
                ),
            )

            response = await servicer.SendHeartbeat(request, mock_context)

            # H2: Verify record_heartbeat called with positional args
            mock_sm.record_heartbeat.assert_called_once()
            call_args = mock_sm.record_heartbeat.call_args
            # First positional arg should be server_id, second should be metrics dict
            assert call_args[0][0] == "test-server"
            assert isinstance(call_args[0][1], dict)
            assert call_args[0][1]["queries_total"] == 1000


class TestCacheFailureClosed:
    """Test cache-set failure handling (M4 fix)."""

    @pytest.mark.asyncio
    async def test_refresh_token_aborts_on_cache_set_failure(
        self, mock_db, mock_cache, mock_key_provider, mock_context
    ):
        """RefreshToken should abort UNAVAILABLE if cache-set fails (M4 fix)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)
        servicer.key_provider = mock_key_provider

        # Mock cache.get to succeed (replay protection passes)
        # Mock cache.set to fail
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(side_effect=Exception("Cache write failed"))

        # Mock context to fail-closed
        mock_context.key_provider = mock_key_provider  # type: ignore[attr-defined]

        with patch("hub_api.modules.netsvcs.grpc.server.decode_token") as mock_decode, \
             patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as MockSM, \
             patch("hub_api.modules.netsvcs.grpc.server.encode_access_token") as mock_encode:

            mock_decode.return_value = {
                "sub": "resolver:test-resolver",
                "aud": "headend",
                "token_type": "refresh",
                "jti": "old-jti",
                "tenant": ENROLLMENT_TENANT,
            }

            mock_sm = AsyncMock()
            mock_sm.get_server = AsyncMock(return_value=Mock(status="online"))
            MockSM.return_value = mock_sm

            mock_encode.return_value = "new-refresh-jwt"

            mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer refresh-token")])

            request = manager_pb2.RefreshTokenRequest(
                api_version="v1",
                server_id="test-resolver",
            )

            with pytest.raises(grpc.RpcError):
                await servicer.RefreshToken(request, mock_context)

            # M4: Should abort UNAVAILABLE on cache-set failure
            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.UNAVAILABLE


class TestValidateTokenZoneIds:
    """Test ValidateToken zone ID fix (M5)."""

    def test_dto_to_proto_config_includes_zone_ids(self, servicer):
        """Test that _dto_to_proto_config uses zone IDs in proto (M5 verification)."""
        # Create config with zones that have distinct ids and names
        zone1_id = "zone-uuid-1"
        zone2_id = "zone-uuid-2"

        config_dto = DNSServerConfigDTO(
            zones=[
                DNSZoneDTO(
                    id=zone1_id,
                    name="example.com",
                    visibility="public",
                    records=[],
                ),
                DNSZoneDTO(
                    id=zone2_id,
                    name="internal.example.com",
                    visibility="internal",
                    records=[],
                ),
            ],
            cache_settings={"ttl": 300},
            settings={},
        )

        # Call the conversion method
        proto_config = servicer._dto_to_proto_config(config_dto)

        # M5: Verify zone IDs are in the proto, not zone names
        assert len(proto_config.zones) == 2
        assert proto_config.zones[0].id == zone1_id
        assert proto_config.zones[1].id == zone2_id
        assert proto_config.zones[0].name == "example.com"
        assert proto_config.zones[1].name == "internal.example.com"


class TestGetConfigAuthentication:
    """Test GetConfig authentication requirements (H1)."""

    @pytest.mark.asyncio
    async def test_get_config_requires_auth(self, servicer, mock_context):
        """GetConfig should abort UNAUTHENTICATED if no token provided."""
        servicer.key_provider = servicer.key_provider
        mock_context.invocation_metadata = Mock(return_value=[])

        request = manager_pb2.GetConfigRequest(
            api_version="v1",
            server_id="test-server",
        )

        with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature:
            mock_feature.return_value = True

            with pytest.raises(grpc.RpcError):
                await servicer.GetConfig(request, mock_context)

            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED

    @pytest.mark.asyncio
    async def test_get_config_subject_mismatch(self, servicer, mock_context):
        """GetConfig should abort PERMISSION_DENIED if subject doesn't match server_id."""
        servicer.key_provider = servicer.key_provider

        with patch("hub_api.modules.netsvcs.grpc.server._authenticate") as mock_auth, \
             patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature:

            # Auth succeeds but sub is for a different resolver
            mock_auth.return_value = {
                "sub": "resolver:OTHER-resolver",
                "aud": "headend",
                "scope": "dns:config:read",
            }
            mock_feature.return_value = True

            request = manager_pb2.GetConfigRequest(
                api_version="v1",
                server_id="test-server",
            )

            with pytest.raises(grpc.RpcError):
                await servicer.GetConfig(request, mock_context)

            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED


class TestCheckIOC:
    """Test IOC checking with blocklist integration (restored behavioral tests)."""

    @pytest.mark.asyncio
    async def test_check_ioc_domain_blocked(self, mock_db, mock_cache, mock_key_provider, mock_context):
        """CheckIOC should return blocked=True when domain is blocked (adapted for auth gate)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="malware.example.com",
            ip="",
        )

        # Provide valid machine-JWT to pass auth gate
        mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-jwt")])

        with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature, \
             patch("hub_api.modules.netsvcs.grpc.server.decode_token") as mock_decode, \
             patch.object(servicer.ioc_checker, 'check_domain', new_callable=AsyncMock) as mock_check:

            mock_feature.return_value = True
            mock_decode.return_value = {
                "sub": "resolver:test",
                "aud": "headend",
                "scope": "ioc:read",
                "tenant": "default",
            }
            mock_check.return_value = {
                "blocked": True,
                "reason": "Blocked by test-feed",
                "feed_source": "test-feed",
                "severity": "high",
            }

            response = await servicer.CheckIOC(request, mock_context)

            assert response.blocked is True
            assert response.severity == "high"
            assert response.feed_source == "test-feed"

    @pytest.mark.asyncio
    async def test_check_ioc_domain_allowed(self, mock_db, mock_cache, mock_key_provider, mock_context):
        """CheckIOC should return blocked=False when domain is allowed (adapted for auth gate)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="safe.example.com",
            ip="",
        )

        # Provide valid machine-JWT to pass auth gate
        mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-jwt")])

        with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature, \
             patch("hub_api.modules.netsvcs.grpc.server.decode_token") as mock_decode, \
             patch.object(servicer.ioc_checker, 'check_domain', new_callable=AsyncMock) as mock_check:

            mock_feature.return_value = True
            mock_decode.return_value = {
                "sub": "resolver:test",
                "aud": "headend",
                "scope": "ioc:read",
                "tenant": "default",
            }
            mock_check.return_value = {
                "blocked": False,
                "reason": "",
                "feed_source": "",
                "severity": "",
            }

            response = await servicer.CheckIOC(request, mock_context)

            assert response.blocked is False
            assert response.feed_source == ""

    @pytest.mark.asyncio
    async def test_check_ioc_ip_blocked(self, mock_db, mock_cache, mock_key_provider, mock_context):
        """CheckIOC should block malicious IPs (adapted for auth gate)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="",
            ip="192.168.1.1",
        )

        # Provide valid machine-JWT to pass auth gate
        mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-jwt")])

        with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature, \
             patch("hub_api.modules.netsvcs.grpc.server.decode_token") as mock_decode, \
             patch.object(servicer.ioc_checker, 'check_ip', new_callable=AsyncMock) as mock_check:

            mock_feature.return_value = True
            mock_decode.return_value = {
                "sub": "resolver:test",
                "aud": "headend",
                "scope": "ioc:read",
                "tenant": "default",
            }
            mock_check.return_value = {
                "blocked": True,
                "reason": "Blocked by ip-feed",
                "feed_source": "ip-feed",
                "severity": "critical",
            }

            response = await servicer.CheckIOC(request, mock_context)

            assert response.blocked is True
            assert response.severity == "critical"

    @pytest.mark.asyncio
    async def test_check_ioc_fail_open_on_error(self, mock_db, mock_cache, mock_key_provider, mock_context):
        """CheckIOC should fail open (not blocked) on any error (adapted for auth gate)."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="test.com",
            ip="",
        )

        # Provide valid machine-JWT to pass auth gate
        mock_context.invocation_metadata = Mock(return_value=[("authorization", "Bearer valid-jwt")])

        with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature, \
             patch("hub_api.modules.netsvcs.grpc.server.decode_token") as mock_decode, \
             patch.object(servicer.ioc_checker, 'check_domain', new_callable=AsyncMock) as mock_check:

            mock_feature.return_value = True
            mock_decode.return_value = {
                "sub": "resolver:test",
                "aud": "headend",
                "scope": "ioc:read",
                "tenant": "default",
            }
            mock_check.side_effect = Exception("Cache error")

            response = await servicer.CheckIOC(request, mock_context)

            # Should fail open
            assert response.blocked is False


class TestCheckIOCAuthentication:
    """Test CheckIOC authentication requirements (H1)."""

    @pytest.mark.asyncio
    async def test_check_ioc_requires_auth(self, servicer, mock_context):
        """CheckIOC should abort UNAUTHENTICATED if no token provided."""
        servicer.key_provider = servicer.key_provider
        mock_context.invocation_metadata = Mock(return_value=[])

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="test.com",
            ip="",
        )

        with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature:
            mock_feature.return_value = True

            with pytest.raises(grpc.RpcError):
                await servicer.CheckIOC(request, mock_context)

            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


class TestTLSConfiguration:
    """Test gRPC TLS configuration (restored from baseline)."""

    @pytest.mark.asyncio
    async def test_tls_missing_cert_raises_error(self, mock_db, mock_cache, mock_key_provider):
        """create_grpc_server should raise if TLS enabled but cert/key paths missing."""
        from hub_api.modules.netsvcs.grpc.server import create_grpc_server

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="TLS enabled but.*not set"):
                await create_grpc_server(
                    db=mock_db,
                    cache=mock_cache,
                    key_provider=mock_key_provider,
                    use_tls=True,
                )

    @pytest.mark.asyncio
    async def test_tls_missing_file_raises_error(self, mock_db, mock_cache, mock_key_provider):
        """create_grpc_server should raise if cert/key files don't exist."""
        from hub_api.modules.netsvcs.grpc.server import create_grpc_server

        with patch.dict(
            os.environ,
            {
                "NETSVCS_GRPC_TLS_CERT_PATH": "/nonexistent/cert.pem",
                "NETSVCS_GRPC_TLS_KEY_PATH": "/nonexistent/key.pem",
            },
        ):
            with pytest.raises(ValueError, match="TLS cert or key file not found"):
                await create_grpc_server(
                    db=mock_db,
                    cache=mock_cache,
                    key_provider=mock_key_provider,
                    use_tls=True,
                )

    @pytest.mark.asyncio
    async def test_insecure_requires_env_opt_in(self, mock_db, mock_cache, mock_key_provider):
        """create_grpc_server should raise if insecure without NETSVCS_GRPC_INSECURE=1."""
        from hub_api.modules.netsvcs.grpc.server import create_grpc_server

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="TLS disabled but NETSVCS_GRPC_INSECURE"):
                await create_grpc_server(
                    db=mock_db,
                    cache=mock_cache,
                    key_provider=mock_key_provider,
                    use_tls=False,
                )


class TestFeatureGating:
    """Test feature flag enforcement (L4)."""

    @pytest.mark.asyncio
    async def test_get_config_aborts_when_feature_disabled(self, servicer, mock_context):
        """GetConfig should abort PERMISSION_DENIED when feature flag is off."""
        servicer.key_provider = servicer.key_provider

        request = manager_pb2.GetConfigRequest(
            api_version="v1",
            server_id="test-server",
        )

        with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature:
            mock_feature.return_value = False  # Feature disabled

            with pytest.raises(grpc.RpcError):
                await servicer.GetConfig(request, mock_context)

            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.PERMISSION_DENIED
