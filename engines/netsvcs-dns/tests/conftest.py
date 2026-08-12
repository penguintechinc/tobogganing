"""Pytest fixtures for netsvcs-dns tests."""
from __future__ import annotations

import asyncio
import grpc
import pytest
import threading
from typing import Generator

from proto.netsvcs.v1 import manager_pb2, manager_pb2_grpc


class StubManagerService(manager_pb2_grpc.ManagerServiceServicer):
    """Stub implementation of ManagerService for testing."""

    def __init__(self) -> None:
        """Initialize stub servicer."""
        self.registered_bootstrap_tokens: dict[str, str] = {"test-bootstrap": "test-server-1"}
        self.server_tokens: dict[str, str] = {
            "test-server-1": "test-jwt-v1"
        }

    async def RegisterServer(
        self, request: manager_pb2.RegisterServerRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.RegisterServerResponse:
        """Stub RegisterServer — extracts bootstrap token from metadata."""
        metadata_dict = dict(context.invocation_metadata())
        auth_header = metadata_dict.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""

        if token not in self.registered_bootstrap_tokens:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid bootstrap token")

        server_id = self.registered_bootstrap_tokens[token]
        config = manager_pb2.ServerConfig(
            zones=[
                manager_pb2.DNSZone(id="z1", name="example.com", visibility="public"),
            ],
            cache_settings=manager_pb2.CacheSettings(ttl=3600, enabled=True, max_entries=10000),
            settings={"policy": "allow_all"},
            ioc_filtering=False,
        )

        return manager_pb2.RegisterServerResponse(
            jwt="test-jwt-v1",
            server_id=server_id,
            config=config,
            config_version=1,
            refresh_token="test-refresh-token",
        )

    async def GetConfig(
        self, request: manager_pb2.GetConfigRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.GetConfigResponse:
        """Stub GetConfig — checks access JWT in metadata."""
        metadata_dict = dict(context.invocation_metadata())
        auth_header = metadata_dict.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""

        if token not in self.server_tokens.values():
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid jwt")

        config = manager_pb2.ServerConfig(
            zones=[
                manager_pb2.DNSZone(id="z1", name="example.com", visibility="public"),
            ],
            cache_settings=manager_pb2.CacheSettings(ttl=3600, enabled=True, max_entries=10000),
            settings={"policy": "allow_all"},
            ioc_filtering=False,
        )

        return manager_pb2.GetConfigResponse(config=config, version=1)

    async def RefreshToken(
        self, request: manager_pb2.RefreshTokenRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.RefreshTokenResponse:
        """Stub RefreshToken — accepts any refresh token."""
        metadata_dict = dict(context.invocation_metadata())
        auth_header = metadata_dict.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""

        if not token:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "no token")

        return manager_pb2.RefreshTokenResponse(jwt="test-jwt-refreshed")

    async def SendHeartbeat(
        self, request: manager_pb2.SendHeartbeatRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.SendHeartbeatResponse:
        """Stub SendHeartbeat."""
        return manager_pb2.SendHeartbeatResponse(config_version=1, should_sync=False)

    async def ValidateToken(
        self, request: manager_pb2.ValidateTokenRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.ValidateTokenResponse:
        """Stub ValidateToken."""
        return manager_pb2.ValidateTokenResponse(valid=True, allowed_zone_ids=["z1"])

    async def CheckIOC(
        self, request: manager_pb2.CheckIOCRequest, context: grpc.aio.ServicerContext
    ) -> manager_pb2.CheckIOCResponse:
        """Stub CheckIOC."""
        return manager_pb2.CheckIOCResponse(blocked=False)


_server_port: int | None = None
_server_loop: asyncio.AbstractEventLoop | None = None


def run_server_in_thread() -> None:
    """Run the gRPC server in a background thread."""
    global _server_port, _server_loop

    async def start_server() -> None:
        global _server_port
        server = grpc.aio.server()
        manager_pb2_grpc.add_ManagerServiceServicer_to_server(
            StubManagerService(), server
        )
        _server_port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        await server.wait_for_termination()

    _server_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_server_loop)
    _server_loop.run_until_complete(start_server())


@pytest.fixture(scope="session", autouse=True)
def stub_server_session() -> Generator[None, None, None]:
    """Start stub server for the test session."""
    thread = threading.Thread(target=run_server_in_thread, daemon=True)
    thread.start()
    # Give the server time to start
    import time
    time.sleep(0.5)
    yield
    # Server cleanup happens via daemon thread


@pytest.fixture
def stub_server_addr() -> str:
    """Return the stub server address."""
    if _server_port is None:
        raise RuntimeError("Stub server not started")
    return f"127.0.0.1:{_server_port}"
