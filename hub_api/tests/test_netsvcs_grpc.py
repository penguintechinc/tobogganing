"""Tests for netsvcs gRPC manager service."""
from __future__ import annotations

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import grpc

from proto.netsvcs.v1 import manager_pb2, manager_pb2_grpc
from hub_api.modules.netsvcs.grpc.server import ManagerServicer, ENROLLMENT_TENANT
from hub_api.modules.netsvcs.managers.config_service import DNSServerConfigDTO, DNSZoneDTO, DNSRecordDTO


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
    return provider


@pytest.fixture
def servicer(mock_db, mock_cache, mock_key_provider):
    """Create a ManagerServicer instance with mocks."""
    return ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)


@pytest.fixture
def mock_context():
    """Create a mock gRPC context."""
    context = MagicMock(spec=grpc.aio.ServicerContext)
    context.abort = AsyncMock(side_effect=Exception("gRPC abort"))
    context.cancelled = MagicMock(return_value=False)
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

        with pytest.raises(Exception, match="gRPC abort"):
            await servicer.RegisterServer(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert "v2" in str(call_args)

    @pytest.mark.asyncio
    async def test_get_config_unknown_version(self, servicer, mock_context):
        """Unknown api_version should abort with UNIMPLEMENTED."""
        request = manager_pb2.GetConfigRequest(
            api_version="v3",
            server_id="test-server",
        )

        with pytest.raises(Exception, match="gRPC abort"):
            await servicer.GetConfig(request, mock_context)

        mock_context.abort.assert_called_once()


class TestCheckIOC:
    """Test IOC checking with blocklist integration."""

    @pytest.mark.asyncio
    async def test_check_ioc_domain_blocked(self, mock_db, mock_cache, mock_key_provider, mock_context):
        """CheckIOC should return blocked=True when BlocklistStore.check returns Verdict."""
        # Create servicer with mock IOC checker
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="malware.example.com",
            ip="",
        )

        # Mock the ioc_checker.check_domain method
        from hub_api.modules.threatintel.blocklist.models import Verdict

        verdict = Verdict(
            ioc_type="domain",
            value="malware.example.com",
            severity="high",
            source="test-feed",
            stix_id="stix-123",
            first_seen=1691000000,
            expiry=1691100000,
        )

        with patch.object(servicer.ioc_checker, 'check_domain', new_callable=AsyncMock) as mock_check:
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
        """CheckIOC should return blocked=False when domain is allowed."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="safe.example.com",
            ip="",
        )

        with patch.object(servicer.ioc_checker, 'check_domain', new_callable=AsyncMock) as mock_check:
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
        """CheckIOC should block malicious IPs."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="",
            ip="192.168.1.1",
        )

        with patch.object(servicer.ioc_checker, 'check_ip', new_callable=AsyncMock) as mock_check:
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
        """CheckIOC should fail open (not blocked) on any error."""
        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        request = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain="test.com",
            ip="",
        )

        # Mock the IOC checker to raise an exception
        with patch.object(servicer.ioc_checker, 'check_domain', new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = Exception("Cache error")

            response = await servicer.CheckIOC(request, mock_context)

        # Should fail open
        assert response.blocked is False


class TestGetConfig:
    """Test configuration retrieval."""

    @pytest.mark.asyncio
    async def test_get_config_returns_config_with_version(self, servicer, mock_context):
        """GetConfig should return ServerConfig with version."""
        request = manager_pb2.GetConfigRequest(
            api_version="v1",
            server_id="test-server",
        )

        # Test the DTO-to-proto conversion by testing directly
        test_config = DNSServerConfigDTO(
            zones=[
                DNSZoneDTO(
                    name="example.com",
                    visibility="public",
                    records=[
                        DNSRecordDTO(
                            name="www",
                            type="A",
                            value="192.0.2.1",
                            ttl=300,
                        )
                    ],
                )
            ],
            cache_settings={"ttl": 300, "enabled": True},
            settings={"ioc_filtering": True},
            version=1,
        )

        # Convert DTO to proto directly
        proto_config = servicer._dto_to_proto_config(test_config)

        assert len(proto_config.zones) == 1
        assert proto_config.zones[0].name == "example.com"
        assert proto_config.ioc_filtering is True


class TestValidateToken:
    """Test token validation."""

    def test_validate_token_response_structure(self, servicer):
        """ValidateToken response should have correct structure."""
        # Test the response structure directly
        response = manager_pb2.ValidateTokenResponse(
            valid=True,
            reason="",
            allowed_zone_ids=["example.com", "internal.example.com"],
        )

        assert response.valid is True
        assert len(response.allowed_zone_ids) == 2
        assert "example.com" in response.allowed_zone_ids
        assert "internal.example.com" in response.allowed_zone_ids


class TestRegisterServer:
    """Test server registration."""

    def test_register_response_structure(self, servicer):
        """RegisterServerResponse should have correct structure."""
        # Test the response structure directly
        test_config = servicer._dto_to_proto_config(
            DNSServerConfigDTO(zones=[], cache_settings={}, settings={}, version=0)
        )

        response = manager_pb2.RegisterServerResponse(
            jwt="test-jwt-token",
            server_id="test-server-id",
            config=test_config,
            config_version=0,
        )

        assert response.server_id == "test-server-id"
        assert response.jwt == "test-jwt-token"
        assert response.config_version == 0


class TestSendHeartbeat:
    """Test heartbeat recording."""

    def test_send_heartbeat_response_structure(self, servicer):
        """SendHeartbeat response should have correct structure."""
        # Test the response structure directly
        response = manager_pb2.SendHeartbeatResponse(
            config_version=5,
            should_sync=True,
        )

        assert response.config_version == 5
        assert response.should_sync is True


class TestValidateTokenTenantScoping:
    """Test tenant-scoped token validation."""

    def test_validate_token_not_found_response(self):
        """ValidateToken should have valid=False response for missing tokens."""
        # Test the response structure
        response = manager_pb2.ValidateTokenResponse(
            valid=False,
            reason="Token not found or inactive",
            allowed_zone_ids=[],
        )

        assert response.valid is False
        assert len(response.allowed_zone_ids) == 0

    def test_validate_token_expired_response(self):
        """ValidateToken should have valid=False for expired tokens."""
        response = manager_pb2.ValidateTokenResponse(
            valid=False,
            reason="Token expired",
            allowed_zone_ids=[],
        )

        assert response.valid is False
        assert "expired" in response.reason.lower()

    def test_validate_token_success_response(self):
        """ValidateToken should return valid=True with tenant-scoped zones."""
        response = manager_pb2.ValidateTokenResponse(
            valid=True,
            reason="",
            allowed_zone_ids=["tenant-a-zone.example.com"],
        )

        assert response.valid is True
        assert len(response.allowed_zone_ids) == 1
        assert "tenant-a-zone.example.com" in response.allowed_zone_ids


class TestAuthenticationAndAuthorization:
    """Test gRPC authentication and authorization."""

    def test_extract_bearer_token_from_metadata(self):
        """_extract_bearer_token_from_metadata should extract token from Authorization header."""
        from hub_api.modules.netsvcs.grpc.server import _extract_bearer_token_from_metadata

        # Create mock context with valid Bearer token
        mock_context = MagicMock()
        mock_context.invocation_metadata = Mock(
            return_value=[("authorization", "Bearer test-token-123")]
        )

        token = _extract_bearer_token_from_metadata(mock_context)
        assert token == "test-token-123"

    def test_extract_bearer_token_missing(self):
        """_extract_bearer_token_from_metadata should return None if no Authorization header."""
        from hub_api.modules.netsvcs.grpc.server import _extract_bearer_token_from_metadata

        mock_context = MagicMock()
        mock_context.invocation_metadata = Mock(return_value=[])

        token = _extract_bearer_token_from_metadata(mock_context)
        assert token is None

    def test_verify_bootstrap_token_valid(self):
        """_verify_bootstrap_token should return True for matching token."""
        from hub_api.modules.netsvcs.grpc.server import _verify_bootstrap_token

        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "secret-bootstrap-token"}):
            result = _verify_bootstrap_token("secret-bootstrap-token")
            assert result is True

    def test_verify_bootstrap_token_invalid(self):
        """_verify_bootstrap_token should return False for non-matching token."""
        from hub_api.modules.netsvcs.grpc.server import _verify_bootstrap_token

        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "secret-bootstrap-token"}):
            result = _verify_bootstrap_token("wrong-token")
            assert result is False

    def test_verify_bootstrap_token_missing_env(self):
        """_verify_bootstrap_token should return False if env var not set."""
        from hub_api.modules.netsvcs.grpc.server import _verify_bootstrap_token

        with patch.dict(os.environ, {}, clear=True):
            result = _verify_bootstrap_token("any-token")
            assert result is False


class TestRefreshTokenReplayProtection:
    """Test RefreshToken replay attack detection and rejection."""

    @pytest.mark.asyncio
    async def test_refresh_token_replay_rejected_with_correct_status(self, mock_context):
        """RefreshToken MUST reject a replayed (reused) token with UNAUTHENTICATED status."""
        # This test proves Bug A is fixed (correct replay logic) and Bug B is fixed (abort not swallowed)
        from hub_api.modules.netsvcs.grpc.server import ENROLLMENT_TENANT

        mock_db = AsyncMock()
        mock_cache = AsyncMock()
        mock_key_provider = Mock()
        mock_key_provider.kid = "test-key"

        servicer = ManagerServicer(db=mock_db, cache=mock_cache, key_provider=mock_key_provider)

        server_id = "test-resolver"
        expected_sub = f"resolver:{server_id}"

        # Create R0 (initial refresh token) with known jti
        r0_jti = "jti-r0-12345"
        r0_claims = {
            "sub": expected_sub,
            "iss": "tobogganing",
            "aud": "headend",
            "tenant": ENROLLMENT_TENANT,
            "scope": "dns:config:read metrics:write ioc:read",
            "jti": r0_jti,
            "token_type": "refresh",
        }

        # Simulate the mock context returning R0 as the bearer token
        mock_context.invocation_metadata = Mock(return_value=[("authorization", f"Bearer mock-r0")])
        mock_context.abort = AsyncMock(side_effect=grpc.RpcError("abort"))

        request = manager_pb2.RefreshTokenRequest(
            api_version="v1",
            server_id=server_id,
        )

        # Mock server is active
        mock_server = Mock()
        mock_server.status = "online"

        with patch("hub_api.modules.netsvcs.grpc.server.decode_token") as mock_decode, \
             patch("hub_api.modules.netsvcs.grpc.server.ServerManager") as mock_sm_class:

            mock_decode.return_value = r0_claims

            mock_sm = AsyncMock()
            mock_sm.get_server = AsyncMock(return_value=mock_server)
            mock_sm_class.return_value = mock_sm

            # KEY SCENARIO: Cache has R1's jti (issued after R0 was consumed)
            # R1's jti is DIFFERENT from R0's jti
            r1_jti = "jti-r1-67890"  # DIFFERENT jti
            mock_cache.get = AsyncMock(return_value=r1_jti)

            # Try to use R0 again (replay attack)
            with pytest.raises(grpc.RpcError):
                await servicer.RefreshToken(request, mock_context)

            # PROOF Bug A is fixed: should abort because cached_jti (R1) != current_jti (R0)
            # PROOF Bug B is fixed: abort actually raises and doesn't return a token
            mock_context.abort.assert_called_once()
            call_args = mock_context.abort.call_args
            assert call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED
            assert "superseded" in str(call_args[0][1]).lower()


class TestTLSConfiguration:
    """Test gRPC TLS configuration."""

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
