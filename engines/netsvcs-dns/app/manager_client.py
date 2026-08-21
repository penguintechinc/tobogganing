"""Async gRPC client for netsvcs ManagerService.

Handles enrollment (RegisterServer), config retrieval (GetConfig), token refresh,
and offline disk-cache resilience.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import grpc
import structlog

# Ensure proto modules are importable from repo root
# __file__ = .../engines/netsvcs-dns/app/manager_client.py
# Need to go up 4 levels to reach the repo root
_repo_root = Path(__file__).parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from proto.netsvcs.v1 import manager_pb2, manager_pb2_grpc  # noqa: E402

logger = structlog.get_logger()


@dataclass(slots=True)
class ManagerCache:
    """Persistent cache for manager enrollment state."""

    server_id: str
    jwt: str
    refresh_token: str
    config: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "server_id": self.server_id,
            "jwt": self.jwt,
            "refresh_token": self.refresh_token,
            "config": self.config,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ManagerCache:
        """Deserialize from dict."""
        return ManagerCache(
            server_id=data["server_id"],
            jwt=data["jwt"],
            refresh_token=data["refresh_token"],
            config=data["config"],
            timestamp=data.get("timestamp", ""),
        )


class ManagerClient:
    """Async gRPC client for ManagerService enrollment and config retrieval."""

    def __init__(
        self,
        grpc_addr: str,
        tls_ca_path: str | None,
        insecure_dev_flag: bool,
        cache_dir: str,
        server_name: str,
    ) -> None:
        """Initialize the gRPC client.

        Args:
            grpc_addr: Control plane gRPC address (host:port)
            tls_ca_path: Path to CA certificate for TLS; None for insecure (dev only)
            insecure_dev_flag: If True and no CA path, allow insecure gRPC (dev flag, logged)
            cache_dir: Directory for offline cache persistence
            server_name: Server name for gRPC
        """
        self.grpc_addr = grpc_addr
        self.cache_dir = Path(cache_dir)
        # 0700: the dir holds credential cache; enforce even if it pre-exists.
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.cache_dir, 0o700)
        except OSError:
            pass
        self.cache_file = self.cache_dir / "manager_cache.json"
        self.server_name = server_name

        self.channel: grpc.aio.Channel | None = None
        self.stub: manager_pb2_grpc.ManagerServiceStub | None = None

        self.server_id: str = ""
        self.jwt: str = ""
        self.refresh_token: str = ""
        self.config: dict[str, Any] = {}

        # Setup TLS or insecure channel
        self.use_tls = tls_ca_path is not None
        self.tls_ca_path = tls_ca_path

        if not self.use_tls and insecure_dev_flag:
            logger.warning(
                "grpc_insecure_dev_flag_enabled",
                addr=grpc_addr,
                msg="gRPC channel using INSECURE connection (dev only). "
                "Ensure NETSVCS_DNS_GRPC_INSECURE is NEVER set in production.",
            )

        if not self.use_tls and not insecure_dev_flag:
            raise RuntimeError(
                "GRPC_TLS_CA_PATH not set and NETSVCS_DNS_GRPC_INSECURE not enabled. "
                "Secure gRPC channel required."
            )

    async def _create_channel(self) -> grpc.aio.Channel:
        """Create secure or insecure gRPC channel."""
        if self.use_tls and self.tls_ca_path:
            with open(self.tls_ca_path, "rb") as f:
                ca_cert = f.read()
            credentials = grpc.ssl_channel_credentials(root_certificates=ca_cert)
            # grpc.aio.secure_channel() has no server_hostname kwarg; SNI/cert-name
            # override goes through the grpc.ssl_target_name_override channel option.
            return grpc.aio.secure_channel(
                self.grpc_addr,
                credentials,
                options=(("grpc.ssl_target_name_override", self.server_name),),
            )
        else:
            return grpc.aio.insecure_channel(self.grpc_addr)

    async def connect(self) -> None:
        """Establish gRPC channel."""
        if self.channel is not None:
            return
        self.channel = await self._create_channel()
        self.stub = manager_pb2_grpc.ManagerServiceStub(self.channel)
        logger.info("grpc_channel_established", addr=self.grpc_addr)

    async def close(self) -> None:
        """Close gRPC channel."""
        if self.channel is not None:
            await self.channel.close()
            self.channel = None
            self.stub = None

    def _metadata(self, token: str) -> list[tuple[str, str]]:
        """Build gRPC metadata with bearer token."""
        return [("authorization", f"Bearer {token}")]

    def _persist_cache(self) -> None:
        """Write current state to disk cache."""
        cache = ManagerCache(
            server_id=self.server_id,
            jwt=self.jwt,
            refresh_token=self.refresh_token,
            config=self.config,
        )
        # The cache holds the machine-JWT + refresh token — write 0600 so the
        # credentials are not world/group readable.
        fd = os.open(self.cache_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cache.to_dict(), f)
        logger.info("manager_cache_persisted", path=str(self.cache_file))

    def _load_cache(self) -> bool:
        """Load state from disk cache. Returns True if loaded successfully."""
        if not self.cache_file.exists():
            return False
        try:
            with open(self.cache_file, "r") as f:
                data = json.load(f)
            cache = ManagerCache.from_dict(data)
            self.server_id = cache.server_id
            self.jwt = cache.jwt
            self.refresh_token = cache.refresh_token
            self.config = cache.config
            logger.info("manager_cache_loaded", path=str(self.cache_file), server_id=self.server_id)
            return True
        except Exception as e:
            logger.error("manager_cache_load_failed", path=str(self.cache_file), error=str(e))
            return False

    async def enroll(self, bootstrap_token: str, hostname: str, version: str) -> bool:
        """Register this server with the control plane.

        Uses bootstrap token in metadata; on success, stores server_id, jwt, refresh_token, and config.
        On failure, attempts to load from disk cache.

        Args:
            bootstrap_token: One-time enrollment token (sent in metadata)
            hostname: Server hostname
            version: Server version string

        Returns:
            True if enrolled (live or from cache), False if enrollment failed and no cache.
        """
        await self.connect()

        req = manager_pb2.RegisterServerRequest(
            api_version="v1",
            hostname=hostname,
            version=version,
        )

        try:
            resp = await self.stub.RegisterServer(
                req, metadata=self._metadata(bootstrap_token), timeout=10.0
            )
            self.server_id = resp.server_id
            self.jwt = resp.jwt
            self.refresh_token = resp.refresh_token
            self.config = {
                "zones": [
                    {"id": z.id, "name": z.name, "visibility": z.visibility}
                    for z in resp.config.zones
                ],
                "version": resp.config_version,
            }
            self._persist_cache()
            logger.info("manager_enrollment_success", server_id=self.server_id)
            return True
        except Exception as e:
            logger.warning(
                "manager_enrollment_failed", error=str(e), msg="Falling back to disk cache"
            )
            if self._load_cache():
                logger.info("manager_using_cached_enrollment", server_id=self.server_id)
                return True
            logger.error("manager_no_cache_fallback", error=str(e))
            return False

    async def get_config(self) -> dict[str, Any] | None:
        """Retrieve current config from control plane.

        Uses the access JWT in metadata.

        Returns:
            Config dict, or None on error.
        """
        if not self.jwt or not self.server_id:
            logger.error("get_config_not_enrolled")
            return None

        req = manager_pb2.GetConfigRequest(
            api_version="v1",
            server_id=self.server_id,
        )

        try:
            resp = await self.stub.GetConfig(req, metadata=self._metadata(self.jwt), timeout=5.0)
            config_dict = {
                "zones": [
                    {"id": z.id, "name": z.name, "visibility": z.visibility}
                    for z in resp.config.zones
                ],
                "version": resp.version,
            }
            self.config = config_dict
            self._persist_cache()
            logger.info("manager_config_fetched", version=resp.version)
            return config_dict
        except Exception as e:
            logger.error("manager_get_config_failed", error=str(e))
            return None

    async def refresh(self) -> bool:
        """Refresh access + refresh tokens.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if not self.refresh_token or not self.server_id:
            logger.error("refresh_not_enrolled")
            return False

        req = manager_pb2.RefreshTokenRequest(
            api_version="v1",
            server_id=self.server_id,
        )

        try:
            resp = await self.stub.RefreshToken(
                req, metadata=self._metadata(self.refresh_token), timeout=5.0
            )
            self.jwt = resp.jwt
            self._persist_cache()
            logger.info("manager_token_refreshed", server_id=self.server_id)
            return True
        except Exception as e:
            logger.error("manager_refresh_failed", error=str(e))
            return False

    async def check_ioc(self, domain: str, ip: str = "") -> dict:
        """Check if domain/IP is blocked by IOC feeds (Indicator of Compromise).

        Fails open: returns {"blocked": False} on any error (control-plane unreachable, timeout).
        This ensures DNS resolution never hangs due to control-plane hiccup.

        Args:
            domain: Domain to check.
            ip: Optional IP address to check.

        Returns:
            {"blocked": bool, "reason": str, "feed_source": str} on success,
            {"blocked": False} on error (fail-open).
        """
        if not self.jwt or not self.server_id:
            logger.warning("check_ioc_not_enrolled")
            return {"blocked": False}

        req = manager_pb2.CheckIOCRequest(
            api_version="v1",
            domain=domain,
            ip=ip,
        )

        try:
            resp = await self.stub.CheckIOC(req, metadata=self._metadata(self.jwt), timeout=2.0)
            return {
                "blocked": resp.blocked,
                "reason": resp.reason,
                "feed_source": resp.feed_source,
            }
        except Exception as e:
            logger.warning(
                "check_ioc_error",
                domain=domain,
                error=str(e),
                msg="Failing open (allowing resolution)",
            )
            return {"blocked": False}

    async def validate_token(self, token: str) -> dict:
        """Validate a DNS-client token with the control plane.

        This delegates token validation to the control plane rather than doing it locally.
        The control plane's response includes allowed_zone_ids for the token's tenant/teams.

        Fails closed: returns {"valid": False, "allowed_zone_ids": []} on error.
        An invalid/unvalidatable token should get no access to private zones.

        Args:
            token: Bearer token from DNS client (without "Bearer " prefix).

        Returns:
            {"valid": bool, "allowed_zone_ids": [...], "reason": str} on success,
            {"valid": False, "allowed_zone_ids": []} on error (fail-closed).
        """
        if not self.jwt or not self.server_id:
            logger.warning("validate_token_not_enrolled")
            return {"valid": False, "allowed_zone_ids": []}

        req = manager_pb2.ValidateTokenRequest(
            api_version="v1",
            token=token,
        )

        try:
            resp = await self.stub.ValidateToken(
                req, metadata=self._metadata(self.jwt), timeout=2.0
            )
            return {
                "valid": resp.valid,
                "allowed_zone_ids": list(resp.allowed_zone_ids),
                "reason": resp.reason,
            }
        except Exception as e:
            logger.warning("validate_token_error", error=str(e), msg="Failing closed (no access)")
            return {"valid": False, "allowed_zone_ids": []}

    async def stream_config_updates(self, on_update: callable) -> None:
        """Stream configuration updates from the control plane.

        Subscribes to StreamConfigUpdates; on each ConfigUpdate with version bump,
        calls on_update(config). This enables live resync without restart.

        Runs indefinitely until the stream ends or an error occurs.
        Should be spawned as a background task in main.py.

        Args:
            on_update: Callable(config_dict) invoked on each config update.
        """
        if not self.jwt or not self.server_id:
            logger.error("stream_config_updates_not_enrolled")
            return

        req = manager_pb2.StreamConfigUpdatesRequest(
            api_version="v1",
            server_id=self.server_id,
        )

        try:
            async for update in self.stub.StreamConfigUpdates(
                req, metadata=self._metadata(self.jwt), timeout=None
            ):
                config_dict = {
                    "zones": [
                        {
                            "id": z.id,
                            "name": z.name,
                            "visibility": z.visibility,
                            "records": [
                                {
                                    "name": r.name,
                                    "type": r.type,
                                    "value": r.value,
                                    "ttl": r.ttl,
                                    "priority": r.priority,
                                    "weight": r.weight,
                                    "port": r.port,
                                }
                                for r in z.records
                            ],
                        }
                        for z in update.config.zones
                    ],
                    "version": update.version,
                }
                logger.info(
                    "config_update_received", version=update.version, update_type=update.update_type
                )
                await on_update(config_dict)
        except Exception as e:
            logger.error("stream_config_updates_error", error=str(e))

    async def send_heartbeat(self, metrics: dict) -> dict:
        """Send heartbeat with metrics to the control plane.

        Args:
            metrics: Metrics dict with keys like queries_total, cache_hits, errors, etc.

        Returns:
            {"config_version": int, "should_sync": bool} on success,
            {"config_version": 0, "should_sync": False} on error.
        """
        if not self.jwt or not self.server_id:
            logger.warning("send_heartbeat_not_enrolled")
            return {"config_version": 0, "should_sync": False}

        server_metrics = manager_pb2.ServerMetrics(
            queries_total=metrics.get("queries_total", 0),
            cache_hits=metrics.get("cache_hits", 0),
            errors=metrics.get("errors", 0),
            avg_response_ms=metrics.get("avg_response_ms", 0.0),
            queries_by_type={k: v for k, v in metrics.get("queries_by_type", {}).items()},
        )

        req = manager_pb2.SendHeartbeatRequest(
            api_version="v1",
            server_id=self.server_id,
            timestamp=int(time.time() * 1000),
            metrics=server_metrics,
        )

        try:
            resp = await self.stub.SendHeartbeat(
                req, metadata=self._metadata(self.jwt), timeout=5.0
            )
            return {
                "config_version": resp.config_version,
                "should_sync": resp.should_sync,
            }
        except Exception as e:
            logger.warning("send_heartbeat_error", error=str(e))
            return {"config_version": 0, "should_sync": False}
