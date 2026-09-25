"""Coverage backfill for perftest_c2c/worker/tasks.py.

Exercises _execute_pair (all source/dest/engine-factory/engine-run error
branches), _start_recurring_run, _node_health, and the sync Celery task
wrappers (run_pair, start_recurring_run, node_health).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_c2c.services.endpoint_manager import EndpointManager
from hub_api.modules.perftest_c2c.worker import tasks as c2c_tasks
from hub_api.modules.perftest_cluster.services.engine_client import EngineError


class _FakeEngineOK:
    """Engine stub returning a canned successful result."""

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        """Return a fixed passing result."""
        return {"latency_ms": 5.0, "throughput": 42.0, "loss_pct": 0.0, "output": "ok"}


class _FakeEngineError:
    """Engine stub raising EngineError."""

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        """Raise EngineError."""
        raise EngineError("unreachable")


class _FakeEngineUnexpected:
    """Engine stub raising a generic exception."""

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        """Raise a plain exception."""
        raise RuntimeError("boom")


class _FakeHealthOK:
    """Health-check engine stub reporting healthy."""

    async def health(self) -> bool:
        """Report healthy."""
        return True


class _FakeHealthUnhealthy:
    """Health-check engine stub reporting unhealthy."""

    async def health(self) -> bool:
        """Report unhealthy."""
        return False


class _FakeHealthEngineError:
    """Health-check engine stub raising EngineError."""

    async def health(self) -> bool:
        """Raise EngineError."""
        raise EngineError("timeout")


class _FakeHealthUnexpected:
    """Health-check engine stub raising a generic exception."""

    async def health(self) -> bool:
        """Raise a plain exception."""
        raise RuntimeError("boom")


async def _make_endpoint(real_dal: AsyncDB, tenant: str, name: str, region: str = "us-east") -> str:
    """Create a c2c endpoint and return its id."""
    mgr = EndpointManager(real_dal, tenant)
    endpoint, _key = await mgr.create_endpoint(
        region=region,
        name=name,
        engine_url="http://engine.local:8080",
        target="target.local",
    )
    return endpoint["id"]


# ---------------------------------------------------------------------------
# _execute_pair
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_pair_source_not_found(real_dal: AsyncDB) -> None:
    """Missing source endpoint records a failed pair result."""
    tenant = "t-pair-src"
    dest_id = await _make_endpoint(real_dal, tenant, "dest")

    result = await c2c_tasks._execute_pair(
        run_id="run-1",
        tenant=tenant,
        source_id="ghost-src",
        dest_id=dest_id,
        test_type="http",
        db=real_dal,
        engine_factory=lambda s: _FakeEngineOK(),
    )
    assert result["status"] == "failed"
    assert "source" in result["test_output"].lower()


@pytest.mark.asyncio
async def test_execute_pair_dest_not_found(real_dal: AsyncDB) -> None:
    """Missing dest endpoint records a failed pair result."""
    tenant = "t-pair-dst"
    source_id = await _make_endpoint(real_dal, tenant, "source")

    result = await c2c_tasks._execute_pair(
        run_id="run-2",
        tenant=tenant,
        source_id=source_id,
        dest_id="ghost-dst",
        test_type="http",
        db=real_dal,
        engine_factory=lambda s: _FakeEngineOK(),
    )
    assert result["status"] == "failed"
    assert "destination" in result["test_output"].lower()


@pytest.mark.asyncio
async def test_execute_pair_engine_factory_error(real_dal: AsyncDB) -> None:
    """A failing engine_factory records a failed pair result."""
    tenant = "t-pair-factory-err"
    source_id = await _make_endpoint(real_dal, tenant, "source")
    dest_id = await _make_endpoint(real_dal, tenant, "dest")

    def _boom_factory(source: dict[str, Any]) -> Any:
        raise RuntimeError("cannot build client")

    result = await c2c_tasks._execute_pair(
        run_id="run-3",
        tenant=tenant,
        source_id=source_id,
        dest_id=dest_id,
        test_type="http",
        db=real_dal,
        engine_factory=_boom_factory,
    )
    assert result["status"] == "failed"
    assert "engine client" in result["test_output"].lower()


@pytest.mark.asyncio
async def test_execute_pair_success(real_dal: AsyncDB) -> None:
    """A successful engine run records a success pair result with metrics."""
    tenant = "t-pair-ok"
    source_id = await _make_endpoint(real_dal, tenant, "source")
    dest_id = await _make_endpoint(real_dal, tenant, "dest")

    result = await c2c_tasks._execute_pair(
        run_id="run-4",
        tenant=tenant,
        source_id=source_id,
        dest_id=dest_id,
        test_type="http",
        db=real_dal,
        engine_factory=lambda s: _FakeEngineOK(),
    )
    assert result["status"] == "success"
    assert result["latency_ms"] == 5.0


@pytest.mark.asyncio
async def test_execute_pair_engine_error_during_run(real_dal: AsyncDB) -> None:
    """An EngineError during run_test records a failed pair result."""
    tenant = "t-pair-run-engineerr"
    source_id = await _make_endpoint(real_dal, tenant, "source")
    dest_id = await _make_endpoint(real_dal, tenant, "dest")

    result = await c2c_tasks._execute_pair(
        run_id="run-5",
        tenant=tenant,
        source_id=source_id,
        dest_id=dest_id,
        test_type="http",
        db=real_dal,
        engine_factory=lambda s: _FakeEngineError(),
    )
    assert result["status"] == "failed"
    assert "engine error" in result["test_output"].lower()


@pytest.mark.asyncio
async def test_execute_pair_unexpected_error_during_run(real_dal: AsyncDB) -> None:
    """A generic exception during run_test records a failed pair result."""
    tenant = "t-pair-run-unexpected"
    source_id = await _make_endpoint(real_dal, tenant, "source")
    dest_id = await _make_endpoint(real_dal, tenant, "dest")

    result = await c2c_tasks._execute_pair(
        run_id="run-6",
        tenant=tenant,
        source_id=source_id,
        dest_id=dest_id,
        test_type="http",
        db=real_dal,
        engine_factory=lambda s: _FakeEngineUnexpected(),
    )
    assert result["status"] == "failed"
    assert "unexpected error" in result["test_output"].lower()


@pytest.mark.asyncio
async def test_execute_pair_unhandled_error_reraises_and_records(
    real_dal: AsyncDB, monkeypatch: Any
) -> None:
    """An exception raised outside the inner try blocks is recorded then re-raised."""
    tenant = "t-pair-unhandled"
    source_id = await _make_endpoint(real_dal, tenant, "source")
    dest_id = await _make_endpoint(real_dal, tenant, "dest")

    async def _boom(self: Any, endpoint_id: str) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(EndpointManager, "get_endpoint", _boom)

    with pytest.raises(RuntimeError, match="db exploded"):
        await c2c_tasks._execute_pair(
            run_id="run-7",
            tenant=tenant,
            source_id=source_id,
            dest_id=dest_id,
            test_type="http",
            db=real_dal,
            engine_factory=lambda s: _FakeEngineOK(),
        )

    results = await real_dal(real_dal.c2c_pair_results.tenant == tenant).select()
    assert any(r["status"] == "failed" for r in results)


@pytest.mark.asyncio
async def test_execute_pair_db_creation_failure(monkeypatch: Any) -> None:
    """When db=None and AsyncDB construction fails, the exception propagates."""
    monkeypatch.setattr(c2c_tasks, "build_db_uri", lambda cfg: "sqlite:///:memory:")
    monkeypatch.setattr(
        c2c_tasks.AsyncDB,
        "__init__",
        lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("cannot connect")),
    )
    with pytest.raises(RuntimeError, match="cannot connect"):
        await c2c_tasks._execute_pair(
            run_id="r",
            tenant="t",
            source_id="s",
            dest_id="d",
            test_type="http",
            db=None,
        )


def test_run_pair_celery_wrapper(monkeypatch: Any) -> None:
    """The sync run_pair Celery task delegates to asyncio.run(_execute_pair(...))."""
    captured: dict[str, Any] = {}

    def fake_run(coro: Any) -> dict[str, Any]:
        captured["called"] = True
        coro.close()
        return {"status": "success"}

    monkeypatch.setattr(c2c_tasks.asyncio, "run", fake_run)

    result = c2c_tasks.run_pair(
        run_id="r",
        tenant="t",
        source_id="s",
        dest_id="d",
        test_type="http",
    )
    assert captured.get("called") is True
    assert result == {"status": "success"}


# ---------------------------------------------------------------------------
# _start_recurring_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_recurring_run_success(real_dal: AsyncDB) -> None:
    """A valid recurring-run job creates and enqueues a matrix run."""
    tenant = "t-recurring-ok"
    await _make_endpoint(real_dal, tenant, "ep-1")
    await _make_endpoint(real_dal, tenant, "ep-2")

    dispatched: list[dict[str, Any]] = []

    def _dispatch(**kwargs: Any) -> None:
        dispatched.append(kwargs)

    result = await c2c_tasks._start_recurring_run(
        job_id="job-r1",
        tenant=tenant,
        module="perftest_c2c",
        job_type="matrix_run",
        payload={"endpoint_ids": None, "interval_seconds": 60},
        db=real_dal,
        dispatch=_dispatch,
    )
    assert result is not None
    assert result["status"] == "running"
    # 2 endpoints -> 2 directed pairs, crossed with default test_types ["icmp", "http"] = 4
    assert result["pairs_count"] == 4
    assert len(dispatched) == 4


@pytest.mark.asyncio
async def test_start_recurring_run_insufficient_endpoints_returns_none(
    real_dal: AsyncDB,
) -> None:
    """Fewer than 2 enabled endpoints causes RunManager.create_run to raise, caught -> None."""
    tenant = "t-recurring-insufficient"
    result = await c2c_tasks._start_recurring_run(
        job_id="job-r2",
        tenant=tenant,
        module="perftest_c2c",
        job_type="matrix_run",
        payload={"endpoint_ids": None, "interval_seconds": 60},
        db=real_dal,
    )
    assert result is None


@pytest.mark.asyncio
async def test_start_recurring_run_enqueue_failure_returns_none(
    real_dal: AsyncDB,
) -> None:
    """A dispatch failure during enqueue is caught, logged, and returns None."""
    tenant = "t-recurring-enqueue-fail"
    await _make_endpoint(real_dal, tenant, "ep-1")
    await _make_endpoint(real_dal, tenant, "ep-2")

    def _boom_dispatch(**kwargs: Any) -> None:
        raise RuntimeError("broker down")

    result = await c2c_tasks._start_recurring_run(
        job_id="job-r3",
        tenant=tenant,
        module="perftest_c2c",
        job_type="matrix_run",
        payload={"endpoint_ids": None, "interval_seconds": 60},
        db=real_dal,
        dispatch=_boom_dispatch,
    )
    assert result is None


@pytest.mark.asyncio
async def test_start_recurring_run_db_creation_failure(monkeypatch: Any) -> None:
    """When db=None and AsyncDB construction fails, returns None."""
    monkeypatch.setattr(c2c_tasks, "build_db_uri", lambda cfg: "sqlite:///:memory:")
    monkeypatch.setattr(
        c2c_tasks.AsyncDB,
        "__init__",
        lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("cannot connect")),
    )
    result = await c2c_tasks._start_recurring_run(
        job_id="j",
        tenant="t",
        module="perftest_c2c",
        job_type="matrix_run",
        payload={"endpoint_ids": None, "interval_seconds": 60},
        db=None,
    )
    assert result is None


def test_start_recurring_run_celery_wrapper(monkeypatch: Any) -> None:
    """The sync start_recurring_run Celery task delegates to asyncio.run(...)."""
    captured: dict[str, Any] = {}

    def fake_run(coro: Any) -> dict[str, Any]:
        captured["called"] = True
        coro.close()
        return {"status": "running"}

    monkeypatch.setattr(c2c_tasks.asyncio, "run", fake_run)

    result = c2c_tasks.start_recurring_run(
        job_id="j",
        tenant="t",
        module="perftest_c2c",
        job_type="matrix_run",
        payload={"endpoint_ids": None, "interval_seconds": 60},
    )
    assert captured.get("called") is True
    assert result == {"status": "running"}


# ---------------------------------------------------------------------------
# _node_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_health_healthy_and_unhealthy(real_dal: AsyncDB) -> None:
    """Endpoints reporting healthy/unhealthy get their status updated accordingly."""
    tenant = "t-health"
    healthy_id = await _make_endpoint(real_dal, tenant, "healthy-ep")
    unhealthy_id = await _make_endpoint(real_dal, tenant, "unhealthy-ep")

    def _factory(endpoint: dict[str, Any]) -> Any:
        return _FakeHealthOK() if endpoint["id"] == healthy_id else _FakeHealthUnhealthy()

    await c2c_tasks._node_health(
        job_id="job-h1",
        tenant=tenant,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
        engine_factory=_factory,
    )

    healthy_row = (await real_dal(real_dal.c2c_endpoints.id == healthy_id).select()).first()
    unhealthy_row = (await real_dal(real_dal.c2c_endpoints.id == unhealthy_id).select()).first()
    assert healthy_row["health_status"] == "healthy"
    assert unhealthy_row["health_status"] == "unhealthy"
    assert healthy_row["last_health_check"] is not None


@pytest.mark.asyncio
async def test_node_health_engine_error_marks_unhealthy(real_dal: AsyncDB) -> None:
    """An EngineError during a health check marks the endpoint unhealthy."""
    tenant = "t-health-engineerr"
    ep_id = await _make_endpoint(real_dal, tenant, "flaky-ep")

    await c2c_tasks._node_health(
        job_id="job-h2",
        tenant=tenant,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
        engine_factory=lambda e: _FakeHealthEngineError(),
    )

    row = (await real_dal(real_dal.c2c_endpoints.id == ep_id).select()).first()
    assert row["health_status"] == "unhealthy"


@pytest.mark.asyncio
async def test_node_health_unexpected_error_marks_unhealthy(real_dal: AsyncDB) -> None:
    """A generic exception during a health check marks the endpoint unhealthy."""
    tenant = "t-health-unexpected"
    ep_id = await _make_endpoint(real_dal, tenant, "broken-ep")

    await c2c_tasks._node_health(
        job_id="job-h3",
        tenant=tenant,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
        engine_factory=lambda e: _FakeHealthUnexpected(),
    )

    row = (await real_dal(real_dal.c2c_endpoints.id == ep_id).select()).first()
    assert row["health_status"] == "unhealthy"


@pytest.mark.asyncio
async def test_node_health_default_engine_factory(real_dal: AsyncDB) -> None:
    """With no engine_factory given, the default factory is used (network call, EngineError)."""
    tenant = "t-health-default-factory"
    await _make_endpoint(real_dal, tenant, "real-ep")

    # No live testserver is running; default factory will raise EngineError on
    # health() (connection refused) which is caught and marks unhealthy.
    await c2c_tasks._node_health(
        job_id="job-h4",
        tenant=tenant,
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
    )
    rows = await real_dal(real_dal.c2c_endpoints.tenant == tenant).select()
    assert rows.first()["health_status"] == "unhealthy"


@pytest.mark.asyncio
async def test_node_health_no_endpoints_completes_cleanly(real_dal: AsyncDB) -> None:
    """A tenant with zero endpoints completes the sweep with no errors."""
    await c2c_tasks._node_health(
        job_id="job-h5",
        tenant="t-health-empty",
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=real_dal,
    )


@pytest.mark.asyncio
async def test_node_health_db_creation_failure(monkeypatch: Any) -> None:
    """When db=None and AsyncDB construction fails, the function returns without raising."""
    monkeypatch.setattr(c2c_tasks, "build_db_uri", lambda cfg: "sqlite:///:memory:")
    monkeypatch.setattr(
        c2c_tasks.AsyncDB,
        "__init__",
        lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("cannot connect")),
    )
    await c2c_tasks._node_health(
        job_id="j",
        tenant="t",
        module="perftest_c2c",
        job_type="node_health",
        payload={},
        db=None,
    )


def test_node_health_celery_wrapper(monkeypatch: Any) -> None:
    """The sync node_health Celery task delegates to asyncio.run(_node_health(...))."""
    captured: dict[str, Any] = {}

    def fake_run(coro: Any) -> None:
        captured["called"] = True
        coro.close()

    monkeypatch.setattr(c2c_tasks.asyncio, "run", fake_run)

    c2c_tasks.node_health(
        job_id="j",
        tenant="t",
        module="perftest_c2c",
        job_type="node_health",
        payload={},
    )
    assert captured.get("called") is True
