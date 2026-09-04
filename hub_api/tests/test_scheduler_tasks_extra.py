"""Additional coverage for hub_api.scheduler.tasks: sweep() wrapper and error paths.

test_scheduler_sweep.py exercises _sweep_async() dispatch logic against a real
DB with explicit db/dispatch/now args; this file covers the sweep() Celery
entrypoint, the default `now`/`db`/`dispatch` construction branches, and the
due_jobs()/mark_ran() exception handlers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.scheduler.registry import clear_handlers, register_job_handler
from hub_api.scheduler.tasks import _sweep_async, sweep


@pytest.fixture
def cleanup_handlers():
    """Clear job handlers before and after each test."""
    clear_handlers()
    yield
    clear_handlers()


def test_sweep_celery_wrapper_calls_async_impl() -> None:
    """sweep() runs _sweep_async() via asyncio.run and returns its result."""
    with patch("hub_api.scheduler.tasks._sweep_async", new=AsyncMock(return_value=3)):
        result = sweep()

    assert result == 3


@pytest.mark.asyncio
async def test_sweep_async_defaults_now_to_utcnow() -> None:
    """_sweep_async() defaults `now` to the current UTC time when not provided."""
    fake_db = MagicMock()
    job_mgr = AsyncMock()
    job_mgr.due_jobs.return_value = []

    with patch("hub_api.scheduler.tasks.JobManager", return_value=job_mgr):
        count = await _sweep_async(db=fake_db, dispatch=MagicMock())

    assert count == 0
    # Confirm due_jobs was called with a real, recent datetime
    called_now = job_mgr.due_jobs.call_args[0][0]
    assert isinstance(called_now, datetime)
    assert abs((datetime.now(timezone.utc) - called_now).total_seconds()) < 5


@pytest.mark.asyncio
async def test_sweep_async_builds_db_when_none(cleanup_handlers) -> None:
    """_sweep_async() constructs a fresh AsyncDB from Config when db=None."""
    fake_db = AsyncMock()
    job_mgr = AsyncMock()
    job_mgr.due_jobs.return_value = []

    with (
        patch("hub_api.scheduler.tasks.Config") as mock_config_cls,
        patch("hub_api.scheduler.tasks.build_db_uri", return_value="sqlite:///:memory:"),
        patch("hub_api.scheduler.tasks.AsyncDB", return_value=fake_db) as mock_asyncdb_cls,
        patch("hub_api.scheduler.tasks.JobManager", return_value=job_mgr),
    ):
        mock_config_cls.return_value = MagicMock(db_pool_size=5)
        count = await _sweep_async(dispatch=MagicMock())

    assert count == 0
    mock_asyncdb_cls.assert_called_once()
    fake_db.reflect.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_async_db_creation_failure_reraises() -> None:
    """_sweep_async() re-raises when fresh AsyncDB construction fails."""
    with patch("hub_api.scheduler.tasks.Config", side_effect=RuntimeError("bad config")):
        with pytest.raises(RuntimeError, match="bad config"):
            await _sweep_async(dispatch=MagicMock())


@pytest.mark.asyncio
async def test_sweep_async_due_jobs_failure_reraises() -> None:
    """_sweep_async() re-raises when JobManager.due_jobs() fails."""
    fake_db = MagicMock()
    job_mgr = AsyncMock()
    job_mgr.due_jobs.side_effect = RuntimeError("db query failed")

    with patch("hub_api.scheduler.tasks.JobManager", return_value=job_mgr):
        with pytest.raises(RuntimeError, match="db query failed"):
            await _sweep_async(db=fake_db, dispatch=MagicMock())


@pytest.mark.asyncio
async def test_sweep_async_default_dispatch_uses_celery_send_task(
    cleanup_handlers,
) -> None:
    """_sweep_async() with dispatch=None uses celery_app.send_task as the default."""
    fake_db = MagicMock()
    job_mgr = AsyncMock()
    now = datetime.now(timezone.utc)
    job_mgr.due_jobs.return_value = [
        {
            "id": "job-1",
            "tenant": "tenant-a",
            "module": "test_module",
            "job_type": "test_job",
            "payload": {"k": "v"},
        }
    ]
    job_mgr.mark_ran = AsyncMock()

    register_job_handler("test_module", "test_job", "test.tasks.run_job")

    with (
        patch("hub_api.scheduler.tasks.JobManager", return_value=job_mgr),
        patch("hub_api.scheduler.tasks.celery_app") as mock_celery_app,
    ):
        count = await _sweep_async(db=fake_db, now=now)

    assert count == 1
    mock_celery_app.send_task.assert_called_once_with(
        "test.tasks.run_job",
        kwargs={
            "job_id": "job-1",
            "tenant": "tenant-a",
            "module": "test_module",
            "job_type": "test_job",
            "payload": {"k": "v"},
        },
    )


@pytest.mark.asyncio
async def test_sweep_async_mark_ran_failure_after_unknown_handler_logged(
    cleanup_handlers,
) -> None:
    """_sweep_async() logs but does not raise when mark_ran fails post-unknown-handler."""
    fake_db = MagicMock()
    job_mgr = AsyncMock()
    now = datetime.now(timezone.utc)
    job_mgr.due_jobs.return_value = [
        {
            "id": "job-1",
            "tenant": "tenant-a",
            "module": "unregistered_module",
            "job_type": "unregistered_job",
            "payload": {},
        }
    ]
    job_mgr.mark_ran = AsyncMock(side_effect=RuntimeError("mark_ran failed"))

    with patch("hub_api.scheduler.tasks.JobManager", return_value=job_mgr):
        count = await _sweep_async(db=fake_db, dispatch=MagicMock(), now=now)

    assert count == 0
    job_mgr.mark_ran.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_async_mark_ran_failure_after_dispatch_logged(
    cleanup_handlers,
) -> None:
    """_sweep_async() logs but does not raise when mark_ran fails post-dispatch."""
    fake_db = MagicMock()
    job_mgr = AsyncMock()
    now = datetime.now(timezone.utc)
    job_mgr.due_jobs.return_value = [
        {
            "id": "job-1",
            "tenant": "tenant-a",
            "module": "test_module",
            "job_type": "test_job",
            "payload": {},
        }
    ]
    job_mgr.mark_ran = AsyncMock(side_effect=RuntimeError("mark_ran failed"))
    register_job_handler("test_module", "test_job", "test.tasks.run_job")

    with patch("hub_api.scheduler.tasks.JobManager", return_value=job_mgr):
        count = await _sweep_async(db=fake_db, dispatch=MagicMock(), now=now)

    assert count == 1
    job_mgr.mark_ran.assert_awaited_once()
