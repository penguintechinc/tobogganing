"""Coverage backfill for perftest_cluster/api/live_test.py.

test_wpc_live_test.py covers auth/scope/feature-flag rejection and the
device-not-found error frame via the real ``client.websocket()`` test-client
transport, which -- confirmed via that suite's own skip -- returns a bare 400
in this environment and never actually reaches the route body (a pre-existing
Quart test-client/ASGI limitation, not something introduced here). This file
instead invokes the ``live_test_stream()`` coroutine directly inside a real
request context, with the module's ``websocket`` name monkeypatched to a
lightweight fake exposing ``.server`` (matching ``ws = websocket.server`` in
the source) -- the same technique the existing suite's docstring points at
("Full WebSocket functionality should be tested via integration tests"),
scoped down to a direct unit-level call instead of a live ASGI socket.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from quart import Quart

from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager

WS_PATH = "/api/v1/perftest_cluster/live-test/stream"


class _FakeWSServer:
    """Fake stand-in for ``websocket.server`` driving the message loop directly.

    ``receive()`` yields each queued message then raises StopAsyncIteration,
    ending the ``async for message in ws.receive():`` loop cleanly so the
    route function returns instead of blocking forever.
    """

    def __init__(
        self,
        messages: list[str],
        *,
        fail_send_after: int | None = None,
        raise_from_receive: BaseException | None = None,
    ) -> None:
        """Store the message queue and initialize send/close recorders.

        Args:
            messages: Raw messages to yield from receive().
            fail_send_after: If set, the Nth+1 call to send() raises instead
                of recording (used to hit the "send also failed" branches).
            raise_from_receive: If set, raised from receive() after yielding
                all queued messages (simulates a transport-level failure).
        """
        self._messages = list(messages)
        self.sent: list[str] = []
        self.closed: list[tuple[int | None, str | None]] = []
        self._fail_send_after = fail_send_after
        self._raise_from_receive = raise_from_receive

    async def close(self, code: int | None = None, message: str | None = None) -> None:
        """Record a close call."""
        self.closed.append((code, message))

    async def send(self, data: str) -> None:
        """Record a sent frame, or raise if configured to fail."""
        if self._fail_send_after is not None and len(self.sent) >= self._fail_send_after:
            raise ConnectionResetError("connection closed")
        self.sent.append(data)

    async def receive(self) -> Any:
        """Yield each queued raw message, then stop or raise if configured."""
        for msg in self._messages:
            yield msg
        if self._raise_from_receive is not None:
            raise self._raise_from_receive


class _FakeWebsocketNamespace:
    """Stand-in for the ``websocket`` proxy exposing only ``.server``."""

    def __init__(self, server: _FakeWSServer) -> None:
        """Wrap the fake server."""
        self.server = server


async def _run_stream(
    app: Quart, token: str, monkeypatch: Any, messages: list[str]
) -> _FakeWSServer:
    """Invoke live_test_stream() directly with a real request context + fake ws."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    fake_server = _FakeWSServer(messages)
    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app.test_request_context(WS_PATH, headers={"Authorization": f"Bearer {token}"}):
        await live_test_mod.live_test_stream()

    return fake_server


@pytest.mark.asyncio
async def test_stream_full_success_flow(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any, monkeypatch: Any
) -> None:
    """A valid message flows: test_started -> test_complete, with persistence."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "d", "serial": "SN"})

    with patch("hub_api.modules.perftest_cluster.api.live_test.EngineClient") as mock_engine_class:
        mock_engine = AsyncMock()
        mock_engine.run_test = AsyncMock(return_value={"status": "success", "latency_ms": 10.0})
        mock_engine.close = AsyncMock()
        mock_engine_class.return_value = mock_engine

        server = await _run_stream(
            app_all_perftest_realdal,
            pf_write_token,
            monkeypatch,
            [
                json.dumps(
                    {
                        "test_type": "http",
                        "target": "example.com",
                        "device_id": device.id,
                        "params": {},
                    }
                )
            ],
        )

    events = [json.loads(f)["event"] for f in server.sent]
    assert "test_started" in events
    assert "test_complete" in events

    results = await real_dal(real_dal.perf_test_results.tenant == "test-tenant").select()
    assert len(results) == 1


@pytest.mark.asyncio
async def test_stream_missing_required_fields(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A message missing test_type/target/device_id gets an error frame."""
    server = await _run_stream(
        app_all_perftest_realdal,
        pf_write_token,
        monkeypatch,
        [json.dumps({"test_type": "http"})],
    )
    frame = json.loads(server.sent[0])
    assert frame["event"] == "error"
    assert "missing required fields" in frame["data"]["message"].lower()


@pytest.mark.asyncio
async def test_stream_rate_limited(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any, monkeypatch: Any
) -> None:
    """When the rate limiter denies, a rate_limit frame is sent."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "d2", "serial": "SN2"})

    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    mock_limiter = AsyncMock()
    mock_limiter.is_allowed = AsyncMock(return_value=(False, 42))
    monkeypatch.setattr(live_test_mod, "_rate_limiter", mock_limiter)

    server = await _run_stream(
        app_all_perftest_realdal,
        pf_write_token,
        monkeypatch,
        [
            json.dumps(
                {
                    "test_type": "http",
                    "target": "x",
                    "device_id": device.id,
                    "params": {},
                }
            )
        ],
    )
    frame = json.loads(server.sent[0])
    assert frame["event"] == "rate_limit"
    assert frame["data"]["retry_after"] == 42


@pytest.mark.asyncio
async def test_stream_invalid_json(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A non-JSON message returns an 'Invalid JSON format' error frame."""
    server = await _run_stream(
        app_all_perftest_realdal, pf_write_token, monkeypatch, ["not valid json{{{"]
    )
    frame = json.loads(server.sent[0])
    assert frame["event"] == "error"
    assert "invalid json" in frame["data"]["message"].lower()


@pytest.mark.asyncio
async def test_stream_persistence_failure_still_completes(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any, monkeypatch: Any
) -> None:
    """A TestManager persistence failure is logged but doesn't break the stream."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "d3", "serial": "SN3"})

    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    async def _boom_create_test(self: Any, data: dict) -> None:
        raise RuntimeError("db write failed")

    monkeypatch.setattr(live_test_mod.TestManager, "create_test", _boom_create_test)

    with patch("hub_api.modules.perftest_cluster.api.live_test.EngineClient") as mock_engine_class:
        mock_engine = AsyncMock()
        mock_engine.run_test = AsyncMock(return_value={"status": "success"})
        mock_engine.close = AsyncMock()
        mock_engine_class.return_value = mock_engine

        server = await _run_stream(
            app_all_perftest_realdal,
            pf_write_token,
            monkeypatch,
            [
                json.dumps(
                    {
                        "test_type": "http",
                        "target": "x",
                        "device_id": device.id,
                        "params": {},
                    }
                )
            ],
        )

    events = [json.loads(f)["event"] for f in server.sent]
    assert "test_complete" in events


@pytest.mark.asyncio
async def test_stream_progress_engine_error(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any, monkeypatch: Any
) -> None:
    """An EngineError during run_test sends an error frame via _stream_test_progress."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "d4", "serial": "SN4"})

    with patch("hub_api.modules.perftest_cluster.api.live_test.EngineClient") as mock_engine_class:
        from hub_api.modules.perftest_cluster.services.engine_client import EngineError

        mock_engine = AsyncMock()
        mock_engine.run_test = AsyncMock(side_effect=EngineError("unreachable"))
        mock_engine.close = AsyncMock()
        mock_engine_class.return_value = mock_engine

        server = await _run_stream(
            app_all_perftest_realdal,
            pf_write_token,
            monkeypatch,
            [
                json.dumps(
                    {
                        "test_type": "http",
                        "target": "x",
                        "device_id": device.id,
                        "params": {},
                    }
                )
            ],
        )

    frames = [json.loads(f) for f in server.sent]
    assert any(f["event"] == "error" and "failed" in f["data"]["message"].lower() for f in frames)


@pytest.mark.asyncio
async def test_stream_progress_unexpected_error(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any, monkeypatch: Any
) -> None:
    """A generic exception during run_test also sends an error frame."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "d5", "serial": "SN5"})

    with patch("hub_api.modules.perftest_cluster.api.live_test.EngineClient") as mock_engine_class:
        mock_engine = AsyncMock()
        mock_engine.run_test = AsyncMock(side_effect=RuntimeError("boom"))
        mock_engine.close = AsyncMock()
        mock_engine_class.return_value = mock_engine

        server = await _run_stream(
            app_all_perftest_realdal,
            pf_write_token,
            monkeypatch,
            [
                json.dumps(
                    {
                        "test_type": "http",
                        "target": "x",
                        "device_id": device.id,
                        "params": {},
                    }
                )
            ],
        )

    frames = [json.loads(f) for f in server.sent]
    assert any(
        f["event"] == "error" and "unexpected error" in f["data"]["message"].lower() for f in frames
    )


@pytest.mark.asyncio
async def test_stream_progress_send_also_fails_is_swallowed(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any, monkeypatch: Any
) -> None:
    """If ws.send() itself fails while reporting an unexpected engine error,
    that secondary failure is swallowed (connection may already be closed)."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "d5b", "serial": "SN5B"})

    with patch("hub_api.modules.perftest_cluster.api.live_test.EngineClient") as mock_engine_class:
        mock_engine = AsyncMock()
        mock_engine.run_test = AsyncMock(side_effect=RuntimeError("boom"))
        mock_engine.close = AsyncMock()
        mock_engine_class.return_value = mock_engine

        # fail_send_after=0: the very first send() attempt (from within
        # _stream_test_progress's own error frame) raises.
        fake_server = _FakeWSServer(
            [
                json.dumps(
                    {
                        "test_type": "http",
                        "target": "x",
                        "device_id": device.id,
                        "params": {},
                    }
                )
            ],
            fail_send_after=0,
        )
        monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))
        async with app_all_perftest_realdal.test_request_context(
            WS_PATH, headers={"Authorization": f"Bearer {pf_write_token}"}
        ):
            # Must not raise even though every send() attempt fails.
            await live_test_mod.live_test_stream()


@pytest.mark.asyncio
async def test_stream_unknown_device_sends_error_frame(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A device_id unregistered for the caller's tenant gets an error frame
    (device-spoofing guard) and the loop continues without calling the engine."""
    with patch("hub_api.modules.perftest_cluster.api.live_test.EngineClient") as mock_engine_class:
        mock_engine = AsyncMock()
        mock_engine.close = AsyncMock()
        mock_engine_class.return_value = mock_engine

        server = await _run_stream(
            app_all_perftest_realdal,
            pf_write_token,
            monkeypatch,
            [
                json.dumps(
                    {
                        "test_type": "http",
                        "target": "x",
                        "device_id": "unregistered-device",
                        "params": {},
                    }
                )
            ],
        )

    frames = [json.loads(f) for f in server.sent]
    assert any(
        f["event"] == "error" and "unknown device" in f["data"]["message"].lower() for f in frames
    )
    mock_engine.run_test.assert_not_called()


@pytest.mark.asyncio
async def test_stream_message_processing_generic_exception(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any, monkeypatch: Any
) -> None:
    """A non-JSONDecodeError exception while processing a message sends a
    'Message processing error' frame and the loop continues."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "d6", "serial": "SN6"})

    async def _boom_get_device(self: Any, device_id: str) -> None:
        raise RuntimeError("device lookup exploded")

    monkeypatch.setattr(DeviceManager, "get_device", _boom_get_device)

    server = await _run_stream(
        app_all_perftest_realdal,
        pf_write_token,
        monkeypatch,
        [
            json.dumps(
                {
                    "test_type": "http",
                    "target": "x",
                    "device_id": device.id,
                    "params": {},
                }
            )
        ],
    )

    frames = [json.loads(f) for f in server.sent]
    assert any(
        f["event"] == "error" and "message processing error" in f["data"]["message"].lower()
        for f in frames
    )


@pytest.mark.asyncio
async def test_stream_receive_cancelled_error_logged_not_raised(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A CancelledError from ws.receive() (client disconnect mid-stream) is
    caught, logged, and the handler returns cleanly (finally still runs)."""
    import asyncio

    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    fake_server = _FakeWSServer([], raise_from_receive=asyncio.CancelledError())
    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app_all_perftest_realdal.test_request_context(
        WS_PATH, headers={"Authorization": f"Bearer {pf_write_token}"}
    ):
        await live_test_mod.live_test_stream()


@pytest.mark.asyncio
async def test_stream_receive_unexpected_exception_sends_error_and_closes(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A generic exception from ws.receive() itself (transport failure) is
    caught by the outer handler, which attempts to notify the client."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    fake_server = _FakeWSServer([], raise_from_receive=RuntimeError("transport died"))
    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app_all_perftest_realdal.test_request_context(
        WS_PATH, headers={"Authorization": f"Bearer {pf_write_token}"}
    ):
        await live_test_mod.live_test_stream()

    frames = [json.loads(f) for f in fake_server.sent]
    assert any(
        f["event"] == "error" and "websocket error" in f["data"]["message"].lower() for f in frames
    )


@pytest.mark.asyncio
async def test_stream_receive_unexpected_exception_send_also_fails(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """When the outer-handler's own error-frame send() also fails, it's swallowed."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    fake_server = _FakeWSServer(
        [], raise_from_receive=RuntimeError("transport died"), fail_send_after=0
    )
    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app_all_perftest_realdal.test_request_context(
        WS_PATH, headers={"Authorization": f"Bearer {pf_write_token}"}
    ):
        # Must not raise even though the final send() attempt also fails.
        await live_test_mod.live_test_stream()


@pytest.mark.asyncio
async def test_stream_auth_rejected_closes_socket(
    app_all_perftest_realdal: Quart, monkeypatch: Any
) -> None:
    """No Authorization header -> auth fails -> socket closed with 1008."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    fake_server = _FakeWSServer([])
    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app_all_perftest_realdal.test_request_context(WS_PATH):
        await live_test_mod.live_test_stream()

    assert fake_server.closed == [(1008, "Unauthorized")]


@pytest.mark.asyncio
async def test_stream_no_scope_closes_socket(
    app_all_perftest_realdal: Quart, monkeypatch: Any, pf_token_factory: Any
) -> None:
    """A token with an empty scope string closes the socket (insufficient privileges)."""
    token = await pf_token_factory("")
    fake_server = _FakeWSServer([])
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app_all_perftest_realdal.test_request_context(
        WS_PATH, headers={"Authorization": f"Bearer {token}"}
    ):
        await live_test_mod.live_test_stream()

    assert fake_server.closed and fake_server.closed[0][0] == 1008


@pytest.mark.asyncio
async def test_stream_insufficient_scope_closes_socket(
    app_all_perftest_realdal: Quart, monkeypatch: Any, pf_token_factory: Any
) -> None:
    """A token lacking tests:write closes the socket."""
    token = await pf_token_factory("stats:read")
    fake_server = _FakeWSServer([])
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app_all_perftest_realdal.test_request_context(
        WS_PATH, headers={"Authorization": f"Bearer {token}"}
    ):
        await live_test_mod.live_test_stream()

    assert fake_server.closed and fake_server.closed[0][0] == 1008


@pytest.mark.asyncio
async def test_stream_feature_disabled_closes_socket(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """A disabled live_test feature flag closes the socket."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    monkeypatch.setattr(live_test_mod, "_check_feature_flag", AsyncMock(return_value=False))

    fake_server = _FakeWSServer([])
    monkeypatch.setattr(live_test_mod, "websocket", _FakeWebsocketNamespace(fake_server))

    async with app_all_perftest_realdal.test_request_context(
        WS_PATH, headers={"Authorization": f"Bearer {pf_write_token}"}
    ):
        await live_test_mod.live_test_stream()

    assert fake_server.closed == [(1008, "Feature not enabled")]


# ---------------------------------------------------------------------------
# _validate_websocket_auth / _check_feature_flag direct unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_websocket_auth_no_key_provider(
    app_all_perftest_realdal: Quart,
) -> None:
    """Missing KEY_PROVIDER config causes auth to fail closed."""
    from hub_api.modules.perftest_cluster.api.live_test import _validate_websocket_auth

    async with app_all_perftest_realdal.test_request_context(
        "/x", headers={"Authorization": "Bearer sometoken"}
    ):
        app_all_perftest_realdal.config["KEY_PROVIDER"] = None
        tenant, claims = await _validate_websocket_auth()
        assert tenant is None
        assert claims is None


@pytest.mark.asyncio
async def test_validate_websocket_auth_token_missing_tenant_claim(
    app_all_perftest_realdal: Quart, monkeypatch: Any
) -> None:
    """A decoded token missing the tenant claim fails closed.

    ``_validate_websocket_auth`` does ``from hub_api.auth.jwt import
    decode_token`` inline (no module-level binding in live_test.py), so the
    patch target is the source module, not live_test.py itself.
    """
    import hub_api.auth.jwt as jwt_mod
    from hub_api.modules.perftest_cluster.api.live_test import _validate_websocket_auth

    monkeypatch.setattr(
        jwt_mod,
        "decode_token",
        lambda token, key_provider: {"sub": "u", "scope": "*:*"},  # no tenant
    )

    async with app_all_perftest_realdal.test_request_context(
        "/x", headers={"Authorization": "Bearer whatever"}
    ):
        tenant, claims = await _validate_websocket_auth()
        assert tenant is None
        assert claims is None


@pytest.mark.asyncio
async def test_check_feature_flag_delegates_to_feature_enabled(
    app_all_perftest_realdal: Quart,
) -> None:
    """_check_feature_flag() reflects the perftest.cluster.live_test flag state."""
    from hub_api.modules.perftest_cluster.api.live_test import _check_feature_flag

    async with app_all_perftest_realdal.test_request_context("/x"):
        # The realdal fixture force-enables all perftest.* flags.
        enabled = await _check_feature_flag("test-tenant")
        assert enabled is True


# ---------------------------------------------------------------------------
# /run (sync) endpoint: persistence success + outer exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_test_sync_persists_result(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any
) -> None:
    """The sync /run endpoint persists a completed test result via real TestManager."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "sync-d", "serial": "SYNC-SN"})

    with patch("hub_api.modules.perftest_cluster.api.live_test.EngineClient") as mock_engine_class:
        mock_engine = AsyncMock()
        mock_engine.run_test = AsyncMock(return_value={"status": "success", "latency_ms": 33.0})
        mock_engine_class.return_value = mock_engine

        client = app_all_perftest_realdal.test_client()
        resp = await client.post(
            "/api/v1/perftest_cluster/live-test/run",
            json={"test_type": "http", "target": "example.com", "device_id": device.id},
            headers={"Authorization": f"Bearer {pf_write_token}"},
        )
        assert resp.status_code == 200

    results = await real_dal(real_dal.perf_test_results.tenant == "test-tenant").select()
    assert len(results) == 1
    assert results.first()["status"] == "completed"


@pytest.mark.asyncio
async def test_run_test_sync_outer_exception_returns_500(
    app_all_perftest_realdal: Quart, pf_write_token: str, monkeypatch: Any
) -> None:
    """An exception outside the inner try (e.g. the rate limiter) yields 500."""
    import hub_api.modules.perftest_cluster.api.live_test as live_test_mod

    mock_limiter = AsyncMock()
    mock_limiter.is_allowed = AsyncMock(side_effect=RuntimeError("limiter exploded"))
    monkeypatch.setattr(live_test_mod, "_rate_limiter", mock_limiter)

    client = app_all_perftest_realdal.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/live-test/run",
        json={"test_type": "http", "target": "x", "device_id": "d"},
        headers={"Authorization": f"Bearer {pf_write_token}"},
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# End-to-end: "throughput" test type through the real EngineClient, mocking
# only the testserver HTTP transport (not EngineClient itself).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_test_sync_throughput_maps_and_persists(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any
) -> None:
    """POST /run with test_type=throughput drives the real EngineClient +
    TestserverSpeedtestBackend against a mocked testserver HTTP response,
    and persists the mapped `throughput` value via TestManager."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "tp-d", "serial": "TP-SN"})

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "bytes_received": 10485760,
            "duration_ms": 812,
            "throughput_mbps": 103.4,
        }
        mock_post.return_value = mock_response

        client = app_all_perftest_realdal.test_client()
        resp = await client.post(
            "/api/v1/perftest_cluster/live-test/run",
            json={
                "test_type": "throughput",
                "target": "8.8.8.8",
                "device_id": device.id,
            },
            headers={"Authorization": f"Bearer {pf_write_token}"},
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["data"]["throughput"] == 103.4
        assert body["data"]["throughput_mbps"] == 103.4

        # Confirm the real backend hit the testserver's speedtest upload
        # endpoint, not the generic /api/v1/test/{type} path.
        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/speedtest/upload")

    results = await real_dal(real_dal.perf_test_results.tenant == "test-tenant").select()
    matching = [r for r in results if r["device_id"] == device.id]
    assert len(matching) == 1
    assert matching[0]["throughput"] == 103.4


@pytest.mark.asyncio
async def test_run_test_sync_speedtest_alias_maps_to_throughput(
    app_all_perftest_realdal: Quart, pf_write_token: str, real_dal: Any
) -> None:
    """The "speedtest" alias resolves to the same throughput backend/path."""
    dev_mgr = DeviceManager(real_dal, "test-tenant")
    device, _key = await dev_mgr.register_device({"name": "sp-d", "serial": "SP-SN"})

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "bytes_received": 1048576,
            "duration_ms": 100,
            "throughput_mbps": 83.9,
        }
        mock_post.return_value = mock_response

        client = app_all_perftest_realdal.test_client()
        resp = await client.post(
            "/api/v1/perftest_cluster/live-test/run",
            json={
                "test_type": "speedtest",
                "target": "8.8.8.8",
                "device_id": device.id,
            },
            headers={"Authorization": f"Bearer {pf_write_token}"},
        )
        assert resp.status_code == 200
        body = await resp.get_json()
        assert body["data"]["throughput"] == 83.9

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/speedtest/upload")
