"""Shared fixtures/doubles for cross-module seam integration tests (P5-E2E/D)."""

from __future__ import annotations

import ipaddress
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import grpc
import pytest
import pytest_asyncio

from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.modules.netsvcs.grpc.server import ManagerServicer
from proto.netsvcs.v1 import manager_pb2_grpc


@dataclass(slots=True)
class FakeCache:
    """In-process stand-in for ``CacheClient``'s get/set/delete/exists.

    The real ``CacheClient`` (hub_api/cache/client.py) raises
    ``CacheUnavailable`` on ANY backend failure when ``fail_closed=True`` —
    by design, so JTI/replay-protection callers never silently pretend a
    write succeeded. In this test environment there is no reachable
    Valkey/Redis, so a real ``CacheClient`` pointed at an unreachable host
    would make every ``fail_closed=True`` call (RegisterServer/RefreshToken's
    JTI caching) raise unconditionally, making the single-use replay logic
    those RPCs are built around untestable. This fake behaves like a
    ``CacheClient`` backed by an always-reachable store: a plain dict,
    honoring TTL, never raising regardless of ``fail_closed``.

    For blocklist reads (which always pass ``fail_closed=False``), a real
    unreachable ``CacheClient`` and this fake are behaviorally equivalent —
    this fake is used uniformly across seams for consistency and speed
    (no 50ms-per-call socket-timeout tax from probing a dead Redis port).
    """

    _store: dict[tuple[str, tuple[str, ...]], tuple[float, str]] = field(default_factory=dict)

    async def get(self, namespace: str, *parts: str, fail_closed: bool = False) -> str | None:
        """Get a value, honoring TTL; never raises."""
        key = (namespace, parts)
        entry = self._store.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if expiry < time.time():
            del self._store[key]
            return None
        return value

    async def set(
        self,
        namespace: str,
        *parts: str,
        value: str,
        ttl_seconds: int | None = None,
        fail_closed: bool = False,
    ) -> None:
        """Set a value with optional TTL; never raises."""
        key = (namespace, parts)
        self._store[key] = (time.time() + (ttl_seconds or 3600), value)

    async def delete(self, namespace: str, *parts: str) -> None:
        """Delete a key; a no-op if absent."""
        self._store.pop((namespace, parts), None)

    async def exists(self, namespace: str, *parts: str) -> bool:
        """Check existence, honoring TTL."""
        key = (namespace, parts)
        entry = self._store.get(key)
        if entry is None:
            return False
        expiry, _ = entry
        return expiry >= time.time()


@dataclass(slots=True)
class ManagerGrpcHarness:
    """A ``ManagerServicer`` bound to a real ephemeral-port gRPC server.

    Exercises real wire serialization + gRPC metadata auth (not direct
    Python method calls, unlike test_netsvcs_grpc.py's unit tests), backed
    by real_dal — the anti-mock integration harness.
    """

    stub: manager_pb2_grpc.ManagerServiceStub
    servicer: ManagerServicer
    key_provider: InAppKeyProvider
    cache: FakeCache
    channel: grpc.aio.Channel


@pytest_asyncio.fixture
async def manager_grpc_harness(real_dal: Any) -> AsyncIterator[ManagerGrpcHarness]:
    """Bind a real ``ManagerServicer`` to 127.0.0.1:<ephemeral> and yield a stub.

    Skips TLS/health/reflection (what ``create_grpc_server`` adds) — those
    need ``grpcio-health-checking``/``grpcio-reflection`` and TLS cert
    material, which is a pre-existing requirements.in gap (3 tests in
    test_netsvcs_grpc.py::TestTLSConfiguration already fail on
    ``ModuleNotFoundError: grpc_health`` before this change) — out of scope
    here per the P5-E2E task (grpcio pins are a separate CI task).
    """
    private_pem, public_pem = generate_rsa_key_pair()
    key_provider = InAppKeyProvider(private_pem, public_pem)
    cache = FakeCache()

    servicer = ManagerServicer(db=real_dal, cache=cache, key_provider=key_provider)
    server = grpc.aio.server()
    manager_pb2_grpc.add_ManagerServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    stub = manager_pb2_grpc.ManagerServiceStub(channel)

    try:
        yield ManagerGrpcHarness(
            stub=stub,
            servicer=servicer,
            key_provider=key_provider,
            cache=cache,
            channel=channel,
        )
    finally:
        await channel.close()
        await server.stop(grace=None)


def _fake_resolve_default(host: str) -> list[str]:
    """Pass literal IPs through unchanged; fake hostnames resolve to 8.8.8.8.

    Mirrors test_threatintel_feeds_ingestor.py's DNS mock so feed-ingest
    seam tests don't depend on real DNS resolution of ``.example`` hosts.
    """
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        return ["8.8.8.8"]


@pytest.fixture(autouse=True)
def _mock_safe_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default all feed-URL SSRF DNS resolution to a safe public IP.

    Autouse: harmless for seams that never call ``ingest_feed_source``.
    """
    monkeypatch.setattr(
        "hub_api.modules.threatintel.feeds.url_safety._resolve_addresses_sync",
        _fake_resolve_default,
    )


class FakeFeedResponse:
    """Minimal async-context-manager stand-in for ``aiohttp.ClientResponse``."""

    def __init__(self, status: int, body: str, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def __aenter__(self) -> "FakeFeedResponse":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def text(self) -> str:
        return self._body

    async def json(self, content_type: Any = None) -> Any:
        return json.loads(self._body)


class FakeFeedSession:
    """Minimal stand-in for ``aiohttp.ClientSession`` exposing only ``.get()``."""

    def __init__(self, status: int, body: str) -> None:
        self._status = status
        self._body = body
        self.calls: list[str] = []

    def get(self, url: str, timeout: Any = None, allow_redirects: bool = True) -> FakeFeedResponse:
        self.calls.append(url)
        return FakeFeedResponse(self._status, self._body)
