"""gRPC manager service for DNS resolver fleet coordination."""
from __future__ import annotations

import asyncio
import grpc
import hmac
import os
import structlog
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from proto.netsvcs.v1 import manager_pb2, manager_pb2_grpc
from hub_api.auth.jwt import encode_access_token, decode_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.modules.netsvcs.ioc import IOCChecker
from hub_api.modules.netsvcs.managers.config_service import (
    ConfigService,
    DNSRecordDTO,
    DNSZoneDTO,
    DNSServerConfigDTO,
)
from hub_api.modules.netsvcs.managers.server_manager import ServerManager

logger = structlog.get_logger()

# Enrollment tenant for the resolver fleet
ENROLLMENT_TENANT = "tobogganing.netsvcs.dns"


def _extract_bearer_token_from_metadata(context: grpc.aio.ServicerContext) -> str | None:
    """Extract bearer token from gRPC metadata Authorization header.

    Args:
        context: gRPC context with invocation metadata

    Returns:
        Token string if present, None otherwise.
    """
    metadata_dict = dict(context.invocation_metadata())
    auth_header = metadata_dict.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:].strip()


def _verify_bootstrap_token(token: str | None) -> bool:
    """Constant-time check of enrollment/bootstrap token.

    Args:
        token: The token to verify.

    Returns:
        True if token matches ENROLLMENT_BOOTSTRAP_TOKEN, False otherwise.
    """
    expected = os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


class ManagerServicer(manager_pb2_grpc.ManagerServiceServicer):
    """gRPC servicer for ManagerService.

    Implements all manager RPCs with api_version routing (v1 → handler,
    else UNIMPLEMENTED). Routes to ConfigService, ServerManager, and IOCChecker.
    """

    def __init__(self, db: Any, cache: Any, key_provider: Any) -> None:
        """Initialize ManagerServicer.

        Args:
            db: penguin-dal AsyncDB instance
            cache: CacheClient for blocklist lookup
            key_provider: KeyProvider for JWT signing/verification
        """
        self.db = db
        self.cache = cache
        self.key_provider = key_provider
        self.ioc_checker = IOCChecker(cache=cache)
        self._config_versions: dict[str, int] = {}  # In-memory version tracking for streaming

    async def RegisterServer(
        self, request: manager_pb2.RegisterServerRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.RegisterServerResponse:
        """Register a DNS resolver node and issue machine-JWT.

        Requires ENROLLMENT_BOOTSTRAP_TOKEN for enrollment (fail-closed).
        """
        if request.api_version != "v1":
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"api_version {request.api_version} not supported",
            )

        try:
            # Verify bootstrap token (required for enrollment)
            bootstrap_token = _extract_bearer_token_from_metadata(context)
            if not _verify_bootstrap_token(bootstrap_token):
                logger.warning("register_server_invalid_bootstrap_token")
                await context.abort(
                    grpc.StatusCode.UNAUTHENTICATED,
                    "enrollment token required",
                )

            # Create server record under enrollment tenant
            server_manager = ServerManager(self.db, ENROLLMENT_TENANT)
            server_record = await server_manager.register_server(
                name=request.hostname,
                hostname=request.hostname,
                version=request.version,
                region="unknown",
            )
            server_id = server_record.id

            # Build machine-JWT claims for dns_resolver node
            claims = build_machine_claims(
                sub_id=server_id,
                node_type="dns_resolver",
                tenant=ENROLLMENT_TENANT,
                iss="tobogganing",
                aud="headend",
            )

            # Encode JWT token
            jwt_token = await encode_access_token(
                claims=claims,
                key_provider=self.key_provider,
                ttl_hours=1,
            )

            # Get initial config
            config_service = ConfigService(self.db, ENROLLMENT_TENANT)
            config_dto = await config_service.get_server_config()
            config_version = await config_service.get_config_version()

            # Build response
            return manager_pb2.RegisterServerResponse(
                jwt=jwt_token,
                server_id=server_id,
                config=self._dto_to_proto_config(config_dto),
                config_version=config_version,
            )

        except Exception as e:
            logger.error("register_server_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def RefreshToken(
        self, request: manager_pb2.RefreshTokenRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.RefreshTokenResponse:
        """Refresh machine-JWT for a registered DNS resolver node.

        Validates the refresh token + enforces single-use via cache JTI tracking (fail-closed on replay).
        """
        if request.api_version != "v1":
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"api_version {request.api_version} not supported",
            )

        # ===== AUTH VALIDATION PHASE (before broad try/except) =====
        # Extract and validate refresh token from metadata
        refresh_token_str = _extract_bearer_token_from_metadata(context)
        if not refresh_token_str:
            logger.warning("refresh_token_missing", server_id=request.server_id)
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "refresh token required",
            )

        # Decode and validate refresh token
        claims = decode_token(refresh_token_str, self.key_provider)
        if not claims:
            logger.warning("refresh_token_invalid", server_id=request.server_id)
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "invalid refresh token",
            )

        # Verify token type is 'refresh'
        if claims.get("token_type") != "refresh":
            logger.warning(
                "refresh_token_type_mismatch",
                server_id=request.server_id,
                token_type=claims.get("token_type"),
            )
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "token is not a refresh token",
            )

        # Verify subject matches requested server_id
        expected_sub = f"resolver:{request.server_id}"
        if claims.get("sub") != expected_sub:
            logger.warning(
                "refresh_token_subject_mismatch",
                server_id=request.server_id,
                expected_sub=expected_sub,
                actual_sub=claims.get("sub"),
            )
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "refresh token does not match server_id",
            )

        # Verify audience
        if claims.get("aud") != "headend":
            logger.warning(
                "refresh_token_aud_mismatch",
                server_id=request.server_id,
                aud=claims.get("aud"),
            )
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "invalid token audience",
            )

        # Verify server exists and is active
        server_manager = ServerManager(self.db, ENROLLMENT_TENANT)
        server = await server_manager.get_server(request.server_id)
        if not server or server.status != "online":
            logger.warning(
                "refresh_server_not_active",
                server_id=request.server_id,
                status=server.status if server else "not_found",
            )
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "server not found or not active",
            )

        # ===== REPLAY PROTECTION PHASE (separate from cache error handling) =====
        subject = expected_sub
        current_jti = claims.get("jti")

        # Read cache separately to avoid catching abort in cache-error except
        cached_jti = None
        try:
            cached_jti = await self.cache.get("auth", "refresh", subject, fail_closed=True)
        except Exception as e:
            logger.warning("refresh_cache_read_error", error=str(e))
            # Fall through on cache error; proceed with caution (fail-closed means cache error = treat as unknown state)

        # Check for replay: if cache exists and is DIFFERENT, this is a superseded token
        if cached_jti and cached_jti != current_jti:
            # This refresh token is old; a newer one has been issued (replay attack)
            logger.error(
                "refresh_replay_detected",
                server_id=request.server_id,
                subject=subject,
                cached_jti=cached_jti[:8],  # Log prefix only
                current_jti=current_jti[:8],
            )
            # Revoke all refresh tokens for this subject
            try:
                await self.cache.delete("auth", "refresh", subject)
            except Exception as e:
                logger.warning("refresh_revocation_error", error=str(e))
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "refresh token superseded",
            )

        # ===== TOKEN MINTING PHASE (broad exception handler for logic errors only) =====
        try:
            # Build refreshed claims with new JTI
            new_claims = build_machine_claims(  # nosec B106 - "refresh" is a JWT token_type label, not a secret
                sub_id=request.server_id,
                node_type="dns_resolver",
                tenant=ENROLLMENT_TENANT,
                iss="tobogganing",
                aud="headend",
                token_type="refresh",
            )

            # Encode new refresh token
            jwt_token = await encode_access_token(
                claims=new_claims,
                key_provider=self.key_provider,
                ttl_hours=24,
            )

            # Cache new refresh JTI (24 hour TTL) for single-use tracking
            new_jti = new_claims.get("jti")
            try:
                await self.cache.set(
                    "auth",
                    "refresh",
                    subject,
                    value=new_jti,
                    ttl_seconds=86400,
                    fail_closed=True,
                )
            except Exception as e:
                logger.warning("refresh_cache_set_error", error=str(e))

            logger.info(
                "refresh_token_issued",
                server_id=request.server_id,
                subject=subject,
            )

            return manager_pb2.RefreshTokenResponse(jwt=jwt_token)

        except Exception as e:
            # Only catches logic errors in minting, not auth failures
            logger.error("refresh_token_minting_error", error=str(e), server_id=request.server_id)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetConfig(
        self, request: manager_pb2.GetConfigRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.GetConfigResponse:
        """Get current configuration for a DNS resolver node."""
        if request.api_version != "v1":
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"api_version {request.api_version} not supported",
            )

        try:
            config_service = ConfigService(self.db, ENROLLMENT_TENANT)
            config_dto = await config_service.get_server_config()
            config_version = await config_service.get_config_version()

            return manager_pb2.GetConfigResponse(
                config=self._dto_to_proto_config(config_dto),
                version=config_version,
            )

        except Exception as e:
            logger.error("get_config_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def StreamConfigUpdates(
        self,
        request: manager_pb2.StreamConfigUpdatesRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[manager_pb2.ConfigUpdate]:
        """Stream configuration updates to a DNS resolver node on version bump.

        Yields the current config, then polls for version changes and yields
        updates as they occur.
        """
        if request.api_version != "v1":
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"api_version {request.api_version} not supported",
            )

        try:
            config_service = ConfigService(self.db, ENROLLMENT_TENANT)

            # Yield current config
            config_dto = await config_service.get_server_config()
            current_version = await config_service.get_config_version()

            yield manager_pb2.ConfigUpdate(
                config=self._dto_to_proto_config(config_dto),
                version=current_version,
                update_type="full",
            )

            # Poll for version bumps and stream updates
            last_version = current_version
            poll_interval = 5  # seconds
            max_iterations = 3600  # 5 hours max stream lifetime

            for _ in range(max_iterations):
                # Check if client cancelled
                if context.cancelled():
                    return

                await asyncio.sleep(poll_interval)

                # Check for version bump
                new_version = await config_service.get_config_version()
                if new_version > last_version:
                    config_dto = await config_service.get_server_config()
                    yield manager_pb2.ConfigUpdate(
                        config=self._dto_to_proto_config(config_dto),
                        version=new_version,
                        update_type="incremental",
                    )
                    last_version = new_version

        except Exception as e:
            logger.error("stream_config_updates_error", error=str(e))
            # Let the stream end naturally; client can reconnect

    async def SendHeartbeat(
        self, request: manager_pb2.SendHeartbeatRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.SendHeartbeatResponse:
        """Record resolver heartbeat and check config version status.

        Unary RPC: server receives metrics once, responds with current config version
        and sync flag. This keeps heartbeat fast and allows the resolver to
        independently decide whether to stream config updates.
        """
        if request.api_version != "v1":
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"api_version {request.api_version} not supported",
            )

        try:
            server_manager = ServerManager(self.db, ENROLLMENT_TENANT)
            config_service = ConfigService(self.db, ENROLLMENT_TENANT)

            # Record metrics
            await server_manager.record_heartbeat(
                server_id=request.server_id,
                metrics={
                    "queries_total": request.metrics.queries_total,
                    "cache_hits": request.metrics.cache_hits,
                    "errors": request.metrics.errors,
                    "avg_response_ms": request.metrics.avg_response_ms,
                    "queries_by_type": dict(request.metrics.queries_by_type),
                },
            )

            # Get current config version
            current_version = await config_service.get_config_version()

            # Determine if resolver should sync (always suggest sync to keep fresh)
            should_sync = True

            return manager_pb2.SendHeartbeatResponse(
                config_version=current_version,
                should_sync=should_sync,
            )

        except Exception as e:
            logger.error("send_heartbeat_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def ValidateToken(
        self, request: manager_pb2.ValidateTokenRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.ValidateTokenResponse:
        """Validate resolver-token and return tenant-scoped allowed zone IDs.

        Looks up the dns_resolver_tokens table for the given token.
        Returns zones for the token's tenant only (never enrollment tenant zones to a tenant's token).
        Updates last_used on successful validation.
        """
        if request.api_version != "v1":
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"api_version {request.api_version} not supported",
            )

        try:
            # Look up the resolver token in the database
            rowset = await self.db(
                self.db.dns_resolver_tokens.token == request.token,
                self.db.dns_resolver_tokens.active == True,
            ).select()
            token_row = rowset.first()

            # Token not found or inactive
            if not token_row:
                return manager_pb2.ValidateTokenResponse(
                    valid=False,
                    reason="Token not found or inactive",
                    allowed_zone_ids=[],
                )

            # Check expiration
            now = datetime.now(timezone.utc)
            if token_row.expires_at and token_row.expires_at < now:
                return manager_pb2.ValidateTokenResponse(
                    valid=False,
                    reason="Token expired",
                    allowed_zone_ids=[],
                )

            # Get zones for the token's tenant only
            config_service = ConfigService(self.db, token_row.tenant)
            config_dto = await config_service.get_server_config()

            zone_ids = [zone.name for zone in config_dto.zones]

            # Update last_used timestamp
            await self.db(
                self.db.dns_resolver_tokens.id == token_row.id,
            ).update(
                last_used=now,
            )

            logger.info(
                "resolver_token_validated",
                token_id=token_row.id,
                tenant=token_row.tenant,
                zone_count=len(zone_ids),
            )

            return manager_pb2.ValidateTokenResponse(
                valid=True,
                reason="",
                allowed_zone_ids=zone_ids,
            )

        except Exception as e:
            logger.error("validate_token_error", error=str(e))
            return manager_pb2.ValidateTokenResponse(
                valid=False,
                reason=f"Validation error: {str(e)}",
                allowed_zone_ids=[],
            )

    async def CheckIOC(
        self, request: manager_pb2.CheckIOCRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.CheckIOCResponse:
        """Check if domain or IP is in blocklist.

        This is a high-frequency operation called during resolver query processing.
        Fails open: any blocklist lookup error returns blocked=False.
        """
        if request.api_version != "v1":
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"api_version {request.api_version} not supported",
            )

        try:
            # Check domain if provided
            if request.domain:
                result = await self.ioc_checker.check_domain(request.domain)
                if result["blocked"]:
                    return manager_pb2.CheckIOCResponse(
                        blocked=True,
                        reason=result["reason"],
                        feed_source=result["feed_source"],
                        severity=result["severity"],
                    )

            # Check IP if provided
            if request.ip:
                result = await self.ioc_checker.check_ip(request.ip)
                if result["blocked"]:
                    return manager_pb2.CheckIOCResponse(
                        blocked=True,
                        reason=result["reason"],
                        feed_source=result["feed_source"],
                        severity=result["severity"],
                    )

            # Not blocked
            return manager_pb2.CheckIOCResponse(
                blocked=False,
                reason="",
                feed_source="",
                severity="",
            )

        except Exception as e:
            logger.error("check_ioc_error", domain=request.domain, ip=request.ip, error=str(e))
            # Fail open: return not blocked on any error
            return manager_pb2.CheckIOCResponse(
                blocked=False,
                reason="",
                feed_source="",
                severity="",
            )

    def _dto_to_proto_config(self, dto: DNSServerConfigDTO) -> manager_pb2.ServerConfig:
        """Convert DNSServerConfigDTO to ServerConfig protobuf message."""
        zones = [
            manager_pb2.DNSZone(
                id="",  # Zone ID not in DTO, leave empty for now
                name=zone.name,
                visibility=zone.visibility,
                records=[
                    manager_pb2.DNSRecord(
                        name=rec.name,
                        type=rec.type,
                        value=rec.value,
                        ttl=rec.ttl,
                        priority=rec.priority or 0,
                        weight=rec.weight or 0,
                        port=rec.port or 0,
                    )
                    for rec in zone.records
                ],
            )
            for zone in dto.zones
        ]

        cache_settings = manager_pb2.CacheSettings(
            ttl=dto.cache_settings.get("ttl", 300),
            enabled=dto.cache_settings.get("enabled", True),
            max_entries=dto.cache_settings.get("max_entries", 10000),
        )

        # Convert settings to string-only map (proto map<string, string>)
        string_settings = {k: str(v) for k, v in dto.settings.items()}

        return manager_pb2.ServerConfig(
            zones=zones,
            cache_settings=cache_settings,
            settings=string_settings,
            ioc_filtering=dto.settings.get("ioc_filtering", False),
        )


async def create_grpc_server(
    db: Any,
    cache: Any,
    key_provider: Any,
    port: int = 50051,
    use_tls: bool = True,
) -> grpc.aio.Server:
    """Create and configure a gRPC manager service server.

    Args:
        db: penguin-dal AsyncDB instance
        cache: CacheClient for blocklist
        key_provider: KeyProvider for JWT signing
        port: Port to listen on (default 50051)
        use_tls: Whether to use TLS with server credentials (default True)

    Returns:
        Configured gRPC server instance (call server.start() to run)
    """
    # Create async server
    server = grpc.aio.server()

    # Add servicer
    servicer = ManagerServicer(db=db, cache=cache, key_provider=key_provider)
    manager_pb2_grpc.add_ManagerServiceServicer_to_server(servicer, server)

    # Add health and reflection services
    from grpc_health.v1 import health, health_pb2, health_pb2_grpc
    from grpc_reflection.v1alpha import reflection

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark service as serving
    health_servicer.set(
        manager_pb2.DESCRIPTOR.services_by_name["ManagerService"].full_name,
        health_pb2.HealthCheckResponse.SERVING,
    )

    # Add reflection for debugging
    SERVICE_NAMES = [
        manager_pb2.DESCRIPTOR.services_by_name["ManagerService"].full_name,
        reflection.SERVICE_NAME,
    ]
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    # Bind to port with TLS or insecure based on configuration
    if use_tls:
        # Load TLS cert and key from env paths
        cert_path = os.environ.get("NETSVCS_GRPC_TLS_CERT_PATH")
        key_path = os.environ.get("NETSVCS_GRPC_TLS_KEY_PATH")

        if not cert_path or not key_path:
            raise ValueError(
                "TLS enabled but NETSVCS_GRPC_TLS_CERT_PATH or NETSVCS_GRPC_TLS_KEY_PATH not set"
            )

        # Read cert and key
        try:
            with open(cert_path, "rb") as f:
                cert_bytes = f.read()
            with open(key_path, "rb") as f:
                key_bytes = f.read()
        except FileNotFoundError as e:
            raise ValueError(f"TLS cert or key file not found: {e}")

        # Build server credentials
        ca_bytes = None
        require_client_auth = False

        # Check for mTLS client CA (for SPIFFE-ready path)
        client_ca_path = os.environ.get("NETSVCS_GRPC_CLIENT_CA_PATH")
        if client_ca_path:
            try:
                with open(client_ca_path, "rb") as f:
                    ca_bytes = f.read()
                require_client_auth = True
                logger.info("grpc_mtls_enabled", client_ca_path=client_ca_path)
            except FileNotFoundError as e:
                logger.warning("grpc_client_ca_not_found", error=str(e))

        # Create SSL credentials
        ssl_credentials = grpc.ssl_server_credentials(
            [(key_bytes, cert_bytes)],
            root_certificates=ca_bytes,
            require_client_auth=require_client_auth,
        )

        server.add_secure_port(f"[::]:{port}", ssl_credentials)
        logger.info(
            "grpc_manager_service_created",
            port=port,
            tls_enabled=True,
            mtls_enabled=require_client_auth,
        )
    else:
        # Insecure mode requires explicit opt-in via env var (for service-mesh-terminated-mTLS only)
        insecure_allowed = os.environ.get("NETSVCS_GRPC_INSECURE") == "1"
        if not insecure_allowed:
            raise ValueError(
                "TLS disabled but NETSVCS_GRPC_INSECURE != '1'. "
                "Insecure gRPC is only allowed in service-mesh-terminated-mTLS deployments. "
                "Set NETSVCS_GRPC_INSECURE=1 to opt in (not recommended)."
            )

        logger.warning(
            "grpc_insecure_mode_enabled",
            reason="NETSVCS_GRPC_INSECURE=1; assuming service-mesh-terminated mTLS",
        )
        server.add_insecure_port(f"[::]:{port}")
        logger.info("grpc_manager_service_created", port=port, tls_enabled=False)

    return server
