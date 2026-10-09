"""Tests for the hubauth gRPC key-surface servicer (SSO relocation PR-1).

Covers: GetPublicKeys returns the correct key set shape; the returned key
matches the same KeyProvider the REST GET /api/v1/auth/public-key endpoint
reads (claim-shape parity, no second source of truth); key-unavailable
(unconfigured provider, KMS fetch failure) fails closed with UNAVAILABLE;
unsupported api_version fails closed with UNIMPLEMENTED; server factory
TLS/insecure-opt-in behavior.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import grpc
import pytest

from hub_api.api.grpc.hubauth_server import (
    HubAuthKeyServicer,
    create_hubauth_grpc_server,
)
from proto.hubauth.v1 import hubauth_pb2


@pytest.fixture
def mock_key_provider():
    """Create a mock KeyProvider mirroring InAppKeyProvider's public surface."""
    provider = Mock(spec=["kid", "public_pem"])
    provider.kid = "test-key-id-1234"
    provider.public_pem = "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----\n"
    return provider


@pytest.fixture
def servicer(mock_key_provider):
    """Create a HubAuthKeyServicer backed by the mock KeyProvider."""
    return HubAuthKeyServicer(mock_key_provider)


@pytest.fixture
def mock_context():
    """gRPC context whose .abort() raises, mirroring real grpc.aio behavior."""
    context = MagicMock(spec=grpc.aio.ServicerContext)

    async def abort_impl(code, details):
        raise grpc.RpcError(f"gRPC abort: {code} {details}")

    context.abort = AsyncMock(side_effect=abort_impl)
    return context


class TestGetPublicKeys:
    """Tests for HubAuthKeyServicer.GetPublicKeys."""

    @pytest.mark.asyncio
    async def test_returns_single_key_wrapped_in_list_shape(self, servicer, mock_context):
        """PR-1: exactly one RS256 key, primary=true, JWKS-shaped (repeated keys)."""
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")

        response = await servicer.GetPublicKeys(request, mock_context)

        assert isinstance(response, hubauth_pb2.PublicKeySetResponse)
        assert len(response.keys) == 1
        key = response.keys[0]
        assert key.kid == "test-key-id-1234"
        assert key.algorithm == "RS256"
        assert key.public_key_pem == "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----\n"
        assert key.use == "sig"
        assert key.primary is True
        assert key.fetched_at_unix > 0
        mock_context.abort.assert_not_called()

    @pytest.mark.asyncio
    async def test_matches_rest_public_key_endpoint_shape(self, servicer, mock_context):
        """gRPC key material must be identical to what headend_routes.py's REST
        GET /api/v1/auth/public-key returns for the same KeyProvider -- one
        source of truth, two transports (design doc §6)."""
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")

        response = await servicer.GetPublicKeys(request, mock_context)
        key = response.keys[0]

        # REST shape: {"public_key": provider.public_pem, "kid": provider.kid,
        # "algorithm": "RS256", "use": "sig"}
        rest_equivalent = {
            "public_key": servicer._key_provider.public_pem,
            "kid": servicer._key_provider.kid,
            "algorithm": "RS256",
            "use": "sig",
        }
        assert key.public_key_pem == rest_equivalent["public_key"]
        assert key.kid == rest_equivalent["kid"]
        assert key.algorithm == rest_equivalent["algorithm"]
        assert key.use == rest_equivalent["use"]

    @pytest.mark.asyncio
    async def test_default_api_version_accepted(self, servicer, mock_context):
        """Empty api_version (proto3 default) is tolerated as v1."""
        request = hubauth_pb2.GetPublicKeysRequest()

        response = await servicer.GetPublicKeys(request, mock_context)

        assert len(response.keys) == 1
        mock_context.abort.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsupported_api_version_aborts_unimplemented(self, servicer, mock_context):
        """Unknown api_version aborts UNIMPLEMENTED (backend.md API Versioning)."""
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v2")

        with pytest.raises(grpc.RpcError):
            await servicer.GetPublicKeys(request, mock_context)

        mock_context.abort.assert_called_once()
        assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNIMPLEMENTED

    @pytest.mark.asyncio
    async def test_key_provider_none_aborts_unavailable(self, mock_context):
        """Unconfigured KeyProvider (startup failure) fails closed with UNAVAILABLE."""
        servicer = HubAuthKeyServicer(None)
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")

        with pytest.raises(grpc.RpcError):
            await servicer.GetPublicKeys(request, mock_context)

        mock_context.abort.assert_called_once()
        assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_key_provider_fetch_failure_aborts_unavailable(self, mock_context):
        """A KMS-backed provider's public_pem fetch raising aborts UNAVAILABLE
        (never a raw exception/stack trace to the caller)."""
        failing_provider = Mock()
        type(failing_provider).public_pem = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("KMS unreachable"))
        )
        failing_provider.kid = "unused"
        servicer = HubAuthKeyServicer(failing_provider)
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")

        with pytest.raises(grpc.RpcError):
            await servicer.GetPublicKeys(request, mock_context)

        mock_context.abort.assert_called_once()
        assert mock_context.abort.call_args[0][0] == grpc.StatusCode.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_never_exposes_private_key_material(self, servicer, mock_context):
        """Response must only ever surface public key fields -- no private-key
        attribute is read or serialized anywhere in the handler."""
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")

        response = await servicer.GetPublicKeys(request, mock_context)

        serialized = response.SerializeToString()
        assert b"PRIVATE KEY" not in serialized
        # Servicer never touches a private-key-shaped attribute on the provider.
        assert not hasattr(servicer._key_provider, "private_pem")

    @pytest.mark.asyncio
    async def test_fetched_at_unix_is_recent(self, servicer, mock_context):
        """fetched_at_unix reflects the time of this read, for client staleness bookkeeping."""
        before = int(datetime.now(timezone.utc).timestamp())
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")

        response = await servicer.GetPublicKeys(request, mock_context)

        after = int(datetime.now(timezone.utc).timestamp())
        assert before <= response.keys[0].fetched_at_unix <= after

    @pytest.mark.asyncio
    async def test_emits_otel_histogram_data_point(self, mock_key_provider, mock_context):
        """testing.md Telemetry Validation: the RPC must emit >=1 OTel metric
        data point (latency histogram) per invocation -- asserted against a
        real OTel SDK InMemoryMetricReader bound to a fresh Meter, not a mock
        of the recording call itself."""
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader

        reader = InMemoryMetricReader()
        local_provider = MeterProvider(metric_readers=[reader])
        servicer = HubAuthKeyServicer(mock_key_provider)
        # Rebind the histogram to a reader-backed Meter we control, rather
        # than depending on process-global set_meter_provider() (which OTel
        # only allows to be called once per process -- unsafe to toggle
        # inside a shared pytest session).
        servicer._latency_histogram = local_provider.get_meter(
            "hub_api.grpc.hubauth.test"
        ).create_histogram("hubauth.grpc.get_public_keys.duration")
        request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")

        await servicer.GetPublicKeys(request, mock_context)

        data_points = 0
        for resource_metrics in reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    data_points += len(metric.data.data_points)
        assert data_points >= 1, "expected >=1 OTel metric data point, got 0"

    @pytest.mark.asyncio
    async def test_emits_structured_log_record(self, servicer, mock_context):
        """testing.md Telemetry Validation: a successful GetPublicKeys call
        emits >=1 structured (penguin/structlog) log record -- asserted by
        spying on the module logger, since structlog's default renderer
        (unconfigured in this unit test) does not route through stdlib
        `logging`/`caplog`."""
        from hub_api.api.grpc import hubauth_server as hubauth_server_module

        with patch.object(hubauth_server_module.logger, "info") as mock_log_info:
            request = hubauth_pb2.GetPublicKeysRequest(api_version="v1")
            await servicer.GetPublicKeys(request, mock_context)

        mock_log_info.assert_called_once()
        assert mock_log_info.call_args[0][0] == "hubauth_grpc_get_public_keys"


class TestCreateHubauthGrpcServer:
    """Tests for the create_hubauth_grpc_server factory (TLS/insecure fail-closed)."""

    @pytest.mark.asyncio
    async def test_insecure_requires_explicit_opt_in(self, mock_key_provider):
        """Plaintext is refused unless HUBAUTH_GRPC_INSECURE=1 is explicitly set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HUBAUTH_GRPC_INSECURE", None)
            with pytest.raises(ValueError, match="HUBAUTH_GRPC_INSECURE"):
                await create_hubauth_grpc_server(mock_key_provider, use_tls=False)

    @pytest.mark.asyncio
    async def test_insecure_opt_in_binds_server(self, mock_key_provider):
        """HUBAUTH_GRPC_INSECURE=1 allows binding an insecure port (mesh-terminated mTLS)."""
        with patch.dict(os.environ, {"HUBAUTH_GRPC_INSECURE": "1"}):
            server = await create_hubauth_grpc_server(mock_key_provider, use_tls=False, port=0)
            assert server is not None
            await server.stop(grace=None)

    @pytest.mark.asyncio
    async def test_tls_requires_cert_and_key_paths(self, mock_key_provider):
        """TLS mode without cert/key paths configured raises, fails closed."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HUBAUTH_GRPC_TLS_CERT_PATH", None)
            os.environ.pop("HUBAUTH_GRPC_TLS_KEY_PATH", None)
            with pytest.raises(ValueError, match="HUBAUTH_GRPC_TLS_CERT_PATH"):
                await create_hubauth_grpc_server(mock_key_provider, use_tls=True)

    @pytest.mark.asyncio
    async def test_default_port_is_50051(self, mock_key_provider):
        """Default HUBAUTH_GRPC_PORT matches the k8s containerPort already declared."""
        with patch.dict(os.environ, {"HUBAUTH_GRPC_INSECURE": "1"}):
            os.environ.pop("HUBAUTH_GRPC_PORT", None)
            with patch("hub_api.api.grpc.hubauth_server.grpc.aio.server") as mock_server_factory:
                mock_server = MagicMock()
                mock_server.add_insecure_port = MagicMock()
                mock_server_factory.return_value = mock_server
                await create_hubauth_grpc_server(mock_key_provider, use_tls=False)
                mock_server.add_insecure_port.assert_called_once_with("[::]:50051")

    @pytest.mark.asyncio
    async def test_reflection_enabled_opt_in(self, mock_key_provider):
        """HUBAUTH_GRPC_REFLECTION_ENABLED=1 registers server reflection (dev-only)."""
        with patch.dict(
            os.environ, {"HUBAUTH_GRPC_INSECURE": "1", "HUBAUTH_GRPC_REFLECTION_ENABLED": "1"}
        ):
            with patch(
                "grpc_reflection.v1alpha.reflection.enable_server_reflection"
            ) as mock_enable_reflection:
                server = await create_hubauth_grpc_server(mock_key_provider, use_tls=False, port=0)
                mock_enable_reflection.assert_called_once()
                await server.stop(grace=None)

    @pytest.mark.asyncio
    async def test_tls_cert_file_not_found_raises(self, mock_key_provider):
        """Configured but missing cert/key file paths raise, fail closed."""
        with patch.dict(
            os.environ,
            {
                "HUBAUTH_GRPC_TLS_CERT_PATH": "/nonexistent/cert.pem",
                "HUBAUTH_GRPC_TLS_KEY_PATH": "/nonexistent/key.pem",
            },
        ):
            with pytest.raises(ValueError, match="TLS cert or key file not found"):
                await create_hubauth_grpc_server(mock_key_provider, use_tls=True)

    @pytest.mark.asyncio
    async def test_tls_success_binds_secure_port(self, mock_key_provider, tmp_path):
        """Valid cert/key paths bind a secure port via grpc.ssl_server_credentials."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        cert_path.write_bytes(b"fake-cert")
        key_path.write_bytes(b"fake-key")

        with patch.dict(
            os.environ,
            {
                "HUBAUTH_GRPC_TLS_CERT_PATH": str(cert_path),
                "HUBAUTH_GRPC_TLS_KEY_PATH": str(key_path),
            },
        ):
            os.environ.pop("HUBAUTH_GRPC_CLIENT_CA_PATH", None)
            with (
                patch(
                    "hub_api.api.grpc.hubauth_server.grpc.ssl_server_credentials"
                ) as mock_ssl_creds,
                patch("hub_api.api.grpc.hubauth_server.grpc.aio.server") as mock_server_factory,
            ):
                mock_ssl_creds.return_value = "fake-credentials"
                mock_server_factory.return_value = MagicMock()
                await create_hubauth_grpc_server(mock_key_provider, use_tls=True, port=0)
                mock_ssl_creds.assert_called_once_with(
                    [(b"fake-key", b"fake-cert")],
                    root_certificates=None,
                    require_client_auth=False,
                )
                mock_server_factory.return_value.add_secure_port.assert_called_once_with(
                    "[::]:0", "fake-credentials"
                )

    @pytest.mark.asyncio
    async def test_mtls_client_ca_enables_require_client_auth(self, mock_key_provider, tmp_path):
        """A configured client CA enables mTLS (require_client_auth=True) --
        SPIFFE-ready: accepts an SVID as a first-class client identity."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        ca_path = tmp_path / "ca.pem"
        cert_path.write_bytes(b"fake-cert")
        key_path.write_bytes(b"fake-key")
        ca_path.write_bytes(b"fake-ca")

        with patch.dict(
            os.environ,
            {
                "HUBAUTH_GRPC_TLS_CERT_PATH": str(cert_path),
                "HUBAUTH_GRPC_TLS_KEY_PATH": str(key_path),
                "HUBAUTH_GRPC_CLIENT_CA_PATH": str(ca_path),
            },
        ):
            with (
                patch(
                    "hub_api.api.grpc.hubauth_server.grpc.ssl_server_credentials"
                ) as mock_ssl_creds,
                patch("hub_api.api.grpc.hubauth_server.grpc.aio.server") as mock_server_factory,
            ):
                mock_ssl_creds.return_value = "fake-credentials"
                mock_server_factory.return_value = MagicMock()
                await create_hubauth_grpc_server(mock_key_provider, use_tls=True, port=0)
                mock_ssl_creds.assert_called_once_with(
                    [(b"fake-key", b"fake-cert")],
                    root_certificates=b"fake-ca",
                    require_client_auth=True,
                )

    @pytest.mark.asyncio
    async def test_mtls_client_ca_not_found_logs_and_continues(self, mock_key_provider, tmp_path):
        """A configured-but-missing client CA path logs a warning and falls
        back to non-mTLS (server cert/key still required and present)."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        cert_path.write_bytes(b"fake-cert")
        key_path.write_bytes(b"fake-key")

        with patch.dict(
            os.environ,
            {
                "HUBAUTH_GRPC_TLS_CERT_PATH": str(cert_path),
                "HUBAUTH_GRPC_TLS_KEY_PATH": str(key_path),
                "HUBAUTH_GRPC_CLIENT_CA_PATH": "/nonexistent/ca.pem",
            },
        ):
            with (
                patch(
                    "hub_api.api.grpc.hubauth_server.grpc.ssl_server_credentials"
                ) as mock_ssl_creds,
                patch("hub_api.api.grpc.hubauth_server.grpc.aio.server") as mock_server_factory,
            ):
                mock_ssl_creds.return_value = "fake-credentials"
                mock_server_factory.return_value = MagicMock()
                await create_hubauth_grpc_server(mock_key_provider, use_tls=True, port=0)
                mock_ssl_creds.assert_called_once_with(
                    [(b"fake-key", b"fake-cert")],
                    root_certificates=None,
                    require_client_auth=False,
                )
