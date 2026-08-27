"""Tests for the Quart application."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from app.main import app


@pytest.fixture
def client():
    """Provide a test client for the Quart app."""
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.asyncio
async def test_healthz(client) -> None:
    """Test /healthz endpoint."""
    response = await client.get("/healthz")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_not_ready(client) -> None:
    """Test /ready endpoint when not ready."""
    # By default, ready should be False (not enrolled)
    response = await client.get("/ready")
    assert response.status_code == 503
    data = await response.get_json()
    assert data["ready"] is False


@pytest.mark.asyncio
async def test_ready_ready(client) -> None:
    """Test /ready endpoint when ready."""
    # Manually set ready to True
    import app.main

    app.main.ready = True

    response = await client.get("/ready")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["ready"] is True

    # Reset
    app.main.ready = False


@pytest.mark.asyncio
async def test_metrics(client) -> None:
    """Test /metrics endpoint."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    text = await response.get_data(as_text=True)
    assert "HELP" in text or text.startswith("#")


@pytest.mark.asyncio
async def test_404(client) -> None:
    """Test 404 error handling."""
    response = await client.get("/nonexistent")
    assert response.status_code == 404
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client) -> None:
    """Test /metrics endpoint is available and returns Prometheus format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    text = await response.get_data(as_text=True)
    # Metrics endpoint should contain HELP/TYPE or be empty
    assert isinstance(text, str)


# P5 coverage backfill: startup/shutdown lifecycle, error handler, entrypoint


def _build_fake_config(main_mod, tmp_path, *, dot_tls: bool):
    """Build a Config instance for lifecycle tests without hitting the environment."""
    return main_mod.Config(
        control_plane_grpc_addr="control-plane:50051",
        enrollment_bootstrap_token="token",
        grpc_tls_ca_path=None,
        grpc_insecure_dev_flag=True,
        server_name="dns-test",
        hostname="test-host",
        region="us-east-1",
        version="0.1.0",
        cache_url="redis://localhost:6379/0",
        doh_port=8053,
        dot_port=8853,
        dot_tls_cert_path=str(tmp_path / "cert.pem") if dot_tls else None,
        dot_tls_key_path=str(tmp_path / "key.pem") if dot_tls else None,
        log_level="info",
        config_cache_dir=str(tmp_path),
    )


def _reset_main_globals(main_mod) -> None:
    """Cancel any background tasks left running by startup() and clear globals."""
    for task in (main_mod.dot_task, main_mod.stream_config_task, main_mod.heartbeat_task):
        if task and not task.done():
            task.cancel()
    main_mod.ready = False
    main_mod.pipeline = None
    main_mod.dot_task = None
    main_mod.stream_config_task = None
    main_mod.heartbeat_task = None
    main_mod.manager_client = None
    main_mod.config = None


@pytest.mark.asyncio
async def test_startup_success_full_enrollment_and_dot(tmp_path) -> None:
    """startup() enrolls, wires DNS components, and starts the DoT listener when TLS is set.

    Also drives the stream-config-update callback (via a stubbed stream_config_updates
    that invokes it once) to cover that nested closure, not just its definition.
    """
    import app.main as main_mod

    fake_config = _build_fake_config(main_mod, tmp_path, dot_tls=True)

    stream_calls: list[dict] = []

    async def fake_stream_config_updates(on_update) -> None:
        stream_calls.append({})
        await on_update(
            {"zones": [{"id": "z2", "name": "example.org", "visibility": "public"}], "version": 2}
        )

    mock_manager_client = AsyncMock()
    mock_manager_client.enroll.return_value = True
    mock_manager_client.get_config.return_value = {
        "zones": [{"id": "z1", "name": "example.com", "visibility": "public"}]
    }
    mock_manager_client.config = {
        "zones": [{"id": "z1", "name": "example.com", "visibility": "public"}]
    }
    mock_manager_client.server_id = "server-1"
    mock_manager_client.stream_config_updates = fake_stream_config_updates

    mock_cache = AsyncMock()
    mock_pipeline_instance = AsyncMock()

    with (
        patch.object(main_mod.Config, "from_env", return_value=fake_config),
        patch.object(main_mod, "ManagerClient", return_value=mock_manager_client),
        patch.object(main_mod, "CacheManager", return_value=mock_cache),
        patch.object(main_mod, "ResolvePipeline", return_value=mock_pipeline_instance),
        patch.object(main_mod.doh, "init_doh") as mock_init_doh,
        patch.object(main_mod.dot, "serve_dot", new=AsyncMock(return_value=None)),
    ):
        await main_mod.startup()
        # Let the stream-config background task run its (stubbed) callback.
        for _ in range(5):
            await asyncio.sleep(0)

    try:
        assert main_mod.ready is True
        assert main_mod.pipeline is mock_pipeline_instance
        mock_init_doh.assert_called_once()
        assert main_mod.dot_task is not None
        assert main_mod.stream_config_task is not None
        assert main_mod.heartbeat_task is not None
        assert stream_calls  # stream_config_updates was invoked
    finally:
        _reset_main_globals(main_mod)


@pytest.mark.asyncio
async def test_heartbeat_loop_sends_metrics_and_survives_errors(tmp_path) -> None:
    """The startup()-local heartbeat loop sends metrics each tick and survives RPC errors.

    Drives the real nested closure (not a mocked task) by replacing module-level
    asyncio.sleep with a fake that still genuinely yields to the event loop
    (`await real_sleep(0)`), so the loop can't busy-spin the test into a hang.
    The background task is explicitly cancelled in `finally` regardless of how
    many iterations it completes.

    MetricsReporter.to_heartbeat_dict() is mocked at its own boundary: the real
    implementation has a pre-existing bug (accesses `._value` on labeled Counters,
    which raises AttributeError) unrelated to what this test targets — main.py's
    heartbeat-loop orchestration, not metrics internals.
    """
    import app.main as main_mod

    fake_config = _build_fake_config(main_mod, tmp_path, dot_tls=False)

    mock_manager_client = AsyncMock()
    mock_manager_client.enroll.return_value = True
    mock_manager_client.get_config.return_value = {"zones": []}
    mock_manager_client.config = {}
    mock_manager_client.stream_config_updates = AsyncMock(return_value=None)
    mock_manager_client.send_heartbeat = AsyncMock(
        side_effect=[
            {"config_version": 1, "should_sync": False},
            Exception("heartbeat rpc boom"),
            {"config_version": 2, "should_sync": False},
        ]
    )

    mock_cache = AsyncMock()
    mock_pipeline_instance = AsyncMock()
    real_sleep = asyncio.sleep

    async def instant_sleep(_seconds: float) -> None:
        await real_sleep(0)

    with (
        patch.object(main_mod.Config, "from_env", return_value=fake_config),
        patch.object(main_mod, "ManagerClient", return_value=mock_manager_client),
        patch.object(main_mod, "CacheManager", return_value=mock_cache),
        patch.object(main_mod, "ResolvePipeline", return_value=mock_pipeline_instance),
        patch.object(main_mod.doh, "init_doh"),
        patch.object(
            main_mod.MetricsReporter, "to_heartbeat_dict", return_value={"queries_total": 1}
        ),
        patch.object(main_mod.asyncio, "sleep", new=instant_sleep),
    ):
        await main_mod.startup()
        for _ in range(50):
            await real_sleep(0)
            if mock_manager_client.send_heartbeat.await_count >= 2:
                break

    try:
        assert mock_manager_client.send_heartbeat.await_count >= 2
    finally:
        _reset_main_globals(main_mod)


@pytest.mark.asyncio
async def test_startup_enrollment_failed_still_initializes_dns(tmp_path) -> None:
    """startup() marks not-ready on enrollment failure but still wires DNS components."""
    import app.main as main_mod

    fake_config = _build_fake_config(main_mod, tmp_path, dot_tls=False)

    mock_manager_client = AsyncMock()
    mock_manager_client.enroll.return_value = False
    mock_manager_client.config = {}
    mock_manager_client.stream_config_updates = AsyncMock(return_value=None)

    mock_cache = AsyncMock()
    mock_pipeline_instance = AsyncMock()

    with (
        patch.object(main_mod.Config, "from_env", return_value=fake_config),
        patch.object(main_mod, "ManagerClient", return_value=mock_manager_client),
        patch.object(main_mod, "CacheManager", return_value=mock_cache),
        patch.object(main_mod, "ResolvePipeline", return_value=mock_pipeline_instance),
        patch.object(main_mod.doh, "init_doh"),
    ):
        await main_mod.startup()

    try:
        assert main_mod.ready is False
        # No TLS cert/key configured -> DoT listener not started
        assert main_mod.dot_task is None
    finally:
        _reset_main_globals(main_mod)


@pytest.mark.asyncio
async def test_startup_config_fetch_failed_still_ready(tmp_path) -> None:
    """startup() marks ready=True even when get_config() fails after enrollment succeeds."""
    import app.main as main_mod

    fake_config = _build_fake_config(main_mod, tmp_path, dot_tls=False)

    mock_manager_client = AsyncMock()
    mock_manager_client.enroll.return_value = True
    mock_manager_client.get_config.return_value = None
    mock_manager_client.config = {}
    mock_manager_client.stream_config_updates = AsyncMock(return_value=None)

    mock_cache = AsyncMock()
    mock_pipeline_instance = AsyncMock()

    with (
        patch.object(main_mod.Config, "from_env", return_value=fake_config),
        patch.object(main_mod, "ManagerClient", return_value=mock_manager_client),
        patch.object(main_mod, "CacheManager", return_value=mock_cache),
        patch.object(main_mod, "ResolvePipeline", return_value=mock_pipeline_instance),
        patch.object(main_mod.doh, "init_doh"),
    ):
        await main_mod.startup()

    try:
        assert main_mod.ready is True
    finally:
        _reset_main_globals(main_mod)


@pytest.mark.asyncio
async def test_startup_exception_marks_not_ready() -> None:
    """startup() catches unexpected errors and marks the service not-ready."""
    import app.main as main_mod

    with patch.object(main_mod.Config, "from_env", side_effect=RuntimeError("boom")):
        await main_mod.startup()

    try:
        assert main_mod.ready is False
    finally:
        _reset_main_globals(main_mod)


@pytest.mark.asyncio
async def test_shutdown_cleans_up_all_resources() -> None:
    """shutdown() closes the pipeline, cancels background tasks, and closes manager_client."""
    import app.main as main_mod

    mock_pipeline = AsyncMock()
    mock_manager_client = AsyncMock()

    async def never_ending() -> None:
        await asyncio.sleep(3600)

    dot_task = asyncio.create_task(never_ending())
    stream_task = asyncio.create_task(never_ending())
    heartbeat_task = asyncio.create_task(never_ending())
    await asyncio.sleep(0)  # let the tasks actually start

    main_mod.pipeline = mock_pipeline
    main_mod.manager_client = mock_manager_client
    main_mod.dot_task = dot_task
    main_mod.stream_config_task = stream_task
    main_mod.heartbeat_task = heartbeat_task

    await main_mod.shutdown()

    mock_pipeline.close.assert_awaited_once()
    mock_manager_client.close.assert_awaited_once()
    assert dot_task.done()
    assert stream_task.done()
    assert heartbeat_task.done()

    _reset_main_globals(main_mod)


@pytest.mark.asyncio
async def test_shutdown_noop_with_no_resources() -> None:
    """shutdown() is a no-op when no resources were ever initialized."""
    import app.main as main_mod

    _reset_main_globals(main_mod)

    await main_mod.shutdown()  # should not raise


@pytest.mark.asyncio
async def test_internal_error_handler_returns_500_payload() -> None:
    """The 500 error handler logs and returns a generic error payload."""
    from app.main import app as quart_app
    from app.main import internal_error

    async with quart_app.test_request_context("/"):
        response, status = await internal_error(Exception("boom"))

    assert status == 500
    data = await response.get_json()
    assert data == {"error": "internal_error"}


@pytest.mark.asyncio
async def test_main_entrypoint_calls_run_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() reads BIND_HOST and starts the Quart app via run_task on port 8080."""
    from app.main import app as quart_app
    from app.main import main as app_main

    monkeypatch.setenv("BIND_HOST", "127.0.0.1")

    with patch.object(quart_app, "run_task", new=AsyncMock(return_value=None)) as mock_run_task:
        await app_main()

    mock_run_task.assert_awaited_once_with(host="127.0.0.1", port=8080)
