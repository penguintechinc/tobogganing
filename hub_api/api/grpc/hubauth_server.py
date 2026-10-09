"""gRPC server exposing hub-api's JWT verification public key(s).

PR-1 of the hub-api SSO relocation's gRPC key surface (design doc §6): a
JWKS-shaped (multi-key) `HubAuthKeyService.GetPublicKeys` RPC, dual-served
alongside the existing single-key REST `GET /api/v1/auth/public-key`
endpoint (`hub_api/api/headend_routes.py`). Both read from the same
`KeyProvider` configured at `app.config["KEY_PROVIDER"]` -- one source of
truth, two transports. This PR wraps that single provider in the new list
shape (`primary=true`, zero algorithm change); a later PR (ES256 rekey)
swaps in a `KeyProviderSet` without a second transport migration, because
the wire shape already supports multiple simultaneously-valid keys.

The public key is non-secret -- this RPC is intentionally unauthenticated
at the application layer, symmetric with the REST endpoint ("headends need
the key before they can authenticate"). Transport security (SPIFFE-ready
mTLS, or plaintext only via explicit intra-cluster opt-in) is enforced by
`create_hubauth_grpc_server` below, mirroring
`hub_api/modules/netsvcs/grpc/server.py`'s TLS/mTLS fail-closed pattern.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING

import grpc
import structlog
from opentelemetry import metrics as otel_metrics
from opentelemetry import trace as otel_trace

from proto.hubauth.v1 import hubauth_pb2, hubauth_pb2_grpc

if TYPE_CHECKING:
    from hub_api.crypto.keys import KeyProvider

logger = structlog.get_logger()
tracer = otel_trace.get_tracer("hub_api.grpc.hubauth")

# Mirrors hub_api/modules/netsvcs/grpc/server.py's hardening defaults: a
# single oversized/unbounded-concurrency caller must not be able to exhaust
# this process's memory/threads (security.md Input Validation: bounds
# validation applies to RPC transport limits too, not just payload fields).
_DEFAULT_GRPC_MAX_MESSAGE_BYTES = 4 * 1024 * 1024  # 4 MiB
_DEFAULT_GRPC_MAX_CONCURRENT_RPCS = 100

# backend.md API Versioning: runtime `api_version` field, routed here;
# unknown/missing-but-set -> UNIMPLEMENTED. Absent field (proto3 default
# "") is tolerated as "v1" for the REST-parity default client that hasn't
# been updated to send it yet.
_SUPPORTED_API_VERSIONS = {"v1", ""}


class HubAuthKeyServicer(hubauth_pb2_grpc.HubAuthKeyServiceServicer):
    """Serves hub-api's current JWT verification public key set.

    Wraps the single app-wide signing `KeyProvider` (same object the REST
    `/api/v1/auth/public-key` endpoint reads) in the new JWKS-shaped
    response. Never exposes private key material -- only `public_pem`/`kid`
    properties are read.
    """

    def __init__(self, key_provider: KeyProvider | None, *, algorithm: str = "RS256") -> None:
        """Initialize with the shared KeyProvider and its current algorithm.

        Args:
            key_provider: The app's signing KeyProvider (`app.config["KEY_PROVIDER"]`).
                `None` is accepted (and handled as UNAVAILABLE per-RPC) so
                this servicer can be constructed before key-provider startup
                failures are fatal, matching the REST endpoint's existing
                "not configured" 500 behavior.
            algorithm: The JWS alg this key signs with. Fixed to "RS256" for
                PR-1; a future rekey PR will pass "ES256" for the new
                primary key alongside a legacy RS256 entry.
        """
        self._key_provider = key_provider
        self._algorithm = algorithm
        meter = otel_metrics.get_meter("hub_api.grpc.hubauth")
        self._latency_histogram = meter.create_histogram(
            "hubauth.grpc.get_public_keys.duration",
            unit="s",
            description="HubAuthKeyService.GetPublicKeys handler latency",
        )

    async def GetPublicKeys(
        self,
        request: hubauth_pb2.GetPublicKeysRequest,
        context: grpc.aio.ServicerContext,
    ) -> hubauth_pb2.PublicKeySetResponse:
        """Return the current public-key set (today: exactly one RS256 key).

        PUBLIC, unauthenticated by design: callers need this key before they
        can hold any token to authenticate with, exactly like the REST
        endpoint it dual-serves alongside. Returns UNAVAILABLE (never a raw
        exception) if the key provider is unconfigured or a KMS-backed
        provider's key fetch fails.
        """
        start = time.monotonic()
        try:
            if request.api_version not in _SUPPORTED_API_VERSIONS:
                logger.warning(
                    "hubauth_grpc_unsupported_api_version",
                    api_version=request.api_version,
                )
                await context.abort(
                    grpc.StatusCode.UNIMPLEMENTED,
                    f"api_version {request.api_version} not supported",
                )
                return hubauth_pb2.PublicKeySetResponse()  # unreachable after abort

            key_provider = self._key_provider
            if key_provider is None:
                logger.error("hubauth_grpc_key_provider_not_configured")
                await context.abort(grpc.StatusCode.UNAVAILABLE, "key provider unavailable")
                return hubauth_pb2.PublicKeySetResponse()  # unreachable after abort

            try:
                # KMS-backed providers (AwsKmsKeyProvider/GcpKmsKeyProvider)
                # perform a blocking network call on first access (cached
                # after); hop to a thread so one cold KMS fetch can't stall
                # every other concurrent RPC on this event loop.
                with tracer.start_as_current_span("hubauth.key_provider.read"):
                    public_pem = await asyncio.to_thread(lambda: key_provider.public_pem)
                    kid = await asyncio.to_thread(lambda: key_provider.kid)
            except Exception as e:
                logger.error("hubauth_grpc_key_fetch_failed", error=str(e), exc_info=True)
                await context.abort(grpc.StatusCode.UNAVAILABLE, "key provider unavailable")
                return hubauth_pb2.PublicKeySetResponse()  # unreachable after abort

            key = hubauth_pb2.PublicKey(
                kid=kid,
                algorithm=self._algorithm,
                public_key_pem=public_pem,
                use="sig",
                primary=True,
                fetched_at_unix=int(time.time()),
            )
            logger.info("hubauth_grpc_get_public_keys", kid=kid, algorithm=self._algorithm)
            return hubauth_pb2.PublicKeySetResponse(keys=[key])
        finally:
            self._latency_histogram.record(time.monotonic() - start)


async def create_hubauth_grpc_server(
    key_provider: KeyProvider | None,
    *,
    algorithm: str = "RS256",
    port: int | None = None,
    use_tls: bool | None = None,
) -> grpc.aio.Server:
    """Create and configure the HubAuthKeyService gRPC server.

    Mirrors `hub_api/modules/netsvcs/grpc/server.py::create_grpc_server`'s
    hardening pattern (message-size + concurrent-RPC caps, structlog,
    fail-closed TLS, no unconditional reflection) on its own env-var
    namespace (`HUBAUTH_GRPC_*`) and port (default 50051, matching the
    `grpc` containerPort already declared in k8s/manifests/hub-api-deployment.yaml).

    Args:
        key_provider: The app's signing KeyProvider, or None if startup
            failed to configure one (servicer answers UNAVAILABLE per-RPC).
        algorithm: JWS alg of the wrapped key (see `HubAuthKeyServicer`).
        port: Listen port; defaults to `HUBAUTH_GRPC_PORT` env var or 50051.
        use_tls: Whether to bind a TLS-secured port; defaults to
            `HUBAUTH_GRPC_INSECURE != "1"` (fail-closed: TLS unless
            explicitly opted out for service-mesh-terminated-mTLS setups).

    Returns:
        Configured `grpc.aio.Server` (call `.start()` to begin serving).
    """
    resolved_port = port if port is not None else int(os.environ.get("HUBAUTH_GRPC_PORT", "50051"))
    resolved_use_tls = (
        use_tls if use_tls is not None else os.environ.get("HUBAUTH_GRPC_INSECURE") != "1"
    )

    max_message_bytes = int(
        os.environ.get("HUBAUTH_GRPC_MAX_MESSAGE_BYTES", str(_DEFAULT_GRPC_MAX_MESSAGE_BYTES))
    )
    maximum_concurrent_rpcs = int(
        os.environ.get("HUBAUTH_GRPC_MAX_CONCURRENT_RPCS", str(_DEFAULT_GRPC_MAX_CONCURRENT_RPCS))
    )

    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ],
        maximum_concurrent_rpcs=maximum_concurrent_rpcs,
    )

    servicer = HubAuthKeyServicer(key_provider, algorithm=algorithm)
    hubauth_pb2_grpc.add_HubAuthKeyServiceServicer_to_server(servicer, server)

    # Health service (always on -- used by orchestrators/load balancers).
    from grpc_health.v1 import health, health_pb2, health_pb2_grpc

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(
        hubauth_pb2.DESCRIPTOR.services_by_name["HubAuthKeyService"].full_name,
        health_pb2.HealthCheckResponse.SERVING,
    )

    # Reflection: dev-only, explicit opt-in (same fail-closed pattern as
    # netsvcs' NETSVCS_GRPC_REFLECTION_ENABLED) -- exposes the full
    # service/method/message surface to anyone who can reach the port.
    if os.environ.get("HUBAUTH_GRPC_REFLECTION_ENABLED") == "1":
        from grpc_reflection.v1alpha import reflection

        service_names = [
            hubauth_pb2.DESCRIPTOR.services_by_name["HubAuthKeyService"].full_name,
            reflection.SERVICE_NAME,
        ]
        reflection.enable_server_reflection(service_names, server)
        logger.warning(
            "hubauth_grpc_reflection_enabled",
            reason="HUBAUTH_GRPC_REFLECTION_ENABLED=1; dev-only, exposes full service surface",
        )

    if resolved_use_tls:
        cert_path = os.environ.get("HUBAUTH_GRPC_TLS_CERT_PATH")
        key_path = os.environ.get("HUBAUTH_GRPC_TLS_KEY_PATH")
        if not cert_path or not key_path:
            raise ValueError(
                "TLS enabled but HUBAUTH_GRPC_TLS_CERT_PATH or HUBAUTH_GRPC_TLS_KEY_PATH not set"
            )

        try:
            with open(cert_path, "rb") as f:
                cert_bytes = f.read()
            with open(key_path, "rb") as f:
                key_bytes = f.read()
        except FileNotFoundError as e:
            raise ValueError(f"TLS cert or key file not found: {e}") from e

        # SPIFFE-ready mTLS: a client CA enables mutual TLS so an
        # SPIFFE/SPIRE-issued X.509-SVID (or any other client cert chaining
        # to this CA) is accepted as a first-class identity, per
        # security.md Service-to-Service Auth -- optional, since the public
        # key itself is non-secret and this RPC has no app-layer auth check.
        ca_bytes = None
        require_client_auth = False
        client_ca_path = os.environ.get("HUBAUTH_GRPC_CLIENT_CA_PATH")
        if client_ca_path:
            try:
                with open(client_ca_path, "rb") as f:
                    ca_bytes = f.read()
                require_client_auth = True
                logger.info("hubauth_grpc_mtls_enabled", client_ca_path=client_ca_path)
            except FileNotFoundError as e:
                logger.warning("hubauth_grpc_client_ca_not_found", error=str(e))

        ssl_credentials = grpc.ssl_server_credentials(
            [(key_bytes, cert_bytes)],
            root_certificates=ca_bytes,
            require_client_auth=require_client_auth,
        )
        server.add_secure_port(f"[::]:{resolved_port}", ssl_credentials)
        logger.info(
            "hubauth_grpc_server_created",
            port=resolved_port,
            tls_enabled=True,
            mtls_enabled=require_client_auth,
        )
    else:
        insecure_allowed = os.environ.get("HUBAUTH_GRPC_INSECURE") == "1"
        if not insecure_allowed:
            raise ValueError(
                "TLS disabled but HUBAUTH_GRPC_INSECURE != '1'. Insecure gRPC is only "
                "allowed in service-mesh-terminated-mTLS deployments. Set "
                "HUBAUTH_GRPC_INSECURE=1 to opt in (not recommended)."
            )
        logger.warning(
            "hubauth_grpc_insecure_mode_enabled",
            reason="HUBAUTH_GRPC_INSECURE=1; assuming service-mesh-terminated mTLS",
        )
        server.add_insecure_port(f"[::]:{resolved_port}")
        logger.info("hubauth_grpc_server_created", port=resolved_port, tls_enabled=False)

    return server
