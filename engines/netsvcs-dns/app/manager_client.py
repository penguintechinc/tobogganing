"""Async gRPC client for netsvcs ManagerService.

Handles enrollment (RegisterServer), config retrieval (GetConfig), token refresh,
and offline disk-cache resilience.
"""
from __future__ import annotations

import asyncio
import grpc
import json
import os
import sys
import structlog
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure proto modules are importable from repo root
# __file__ = .../engines/netsvcs-dns/app/manager_client.py
# Need to go up 4 levels to reach the repo root
_repo_root = Path(__file__).parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from proto.netsvcs.v1 import manager_pb2, manager_pb2_grpc

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
            return grpc.aio.secure_channel(self.grpc_addr, credentials, server_hostname=self.server_name)
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
                "zones": [{"id": z.id, "name": z.name, "visibility": z.visibility} for z in resp.config.zones],
                "version": resp.config_version,
            }
            self._persist_cache()
            logger.info("manager_enrollment_success", server_id=self.server_id)
            return True
        except Exception as e:
            logger.warning("manager_enrollment_failed", error=str(e), msg="Falling back to disk cache")
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
                "zones": [{"id": z.id, "name": z.name, "visibility": z.visibility} for z in resp.config.zones],
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
            resp = await self.stub.RefreshToken(req, metadata=self._metadata(self.refresh_token), timeout=5.0)
            self.jwt = resp.jwt
            self._persist_cache()
            logger.info("manager_token_refreshed", server_id=self.server_id)
            return True
        except Exception as e:
            logger.error("manager_refresh_failed", error=str(e))
            return False
