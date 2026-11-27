"""Tests for SecurityScanner scheduler wiring (registration, job creation, fail-loud runs)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from hub_api.modules.sase import module as sase_module
from hub_api.modules.sase.security.scanner import tasks
from hub_api.modules.sase.security.scanner.core import ScanType, SecurityScanner
from hub_api.scheduler.registry import clear_handlers, handler_for


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """Isolate the global handler registry per test."""
    clear_handlers()
    yield
    clear_handlers()


def test_sase_module_registers_scanner_handler() -> None:
    """Loading the SASE module contract registers the scanner job handler."""
    sase_module()
    assert handler_for(tasks.SCANNER_MODULE, tasks.SCANNER_JOB_TYPE) == tasks.SCANNER_TASK_NAME


@pytest.mark.asyncio
async def test_schedule_security_scans_creates_tenant_job() -> None:
    """schedule_security_scans persists a tenant-scoped job and registers the handler."""
    create = AsyncMock(return_value={"id": "j1"})
    with patch("hub_api.scheduler.job_manager.JobManager.create_job", new=create):
        job = await tasks.schedule_security_scans(object(), "t1", interval_seconds=600)
    assert job == {"id": "j1"}
    create.assert_awaited_once_with(
        tenant="t1",
        module="sase_scanner",
        job_type="run_security_scans",
        payload={},
        interval_seconds=600,
    )
    assert handler_for(tasks.SCANNER_MODULE, tasks.SCANNER_JOB_TYPE)


@pytest.mark.asyncio
async def test_schedule_security_scans_requires_tenant() -> None:
    """No tenant -> ValueError, nothing persisted."""
    with pytest.raises(ValueError):
        await tasks.schedule_security_scans(object(), "")


@pytest.mark.asyncio
async def test_run_scheduled_scans_requires_tenant() -> None:
    """The task refuses to run without a tenant."""
    with pytest.raises(ValueError):
        await tasks._run_scheduled_scans_async("", db=object())


def _scanner(tenant: str | None) -> SecurityScanner:
    """Build a scanner without touching Docker."""
    with patch.dict("sys.modules", {"docker": None}):
        return SecurityScanner(db=object(), tenant_id=tenant)


@pytest.mark.asyncio
async def test_run_scheduled_scans_runs_scanner_for_tenant() -> None:
    """The async task builds a tenant-scoped scanner and returns its counts."""
    with patch.object(
        SecurityScanner, "run_due_scans", new=AsyncMock(return_value={"ran": 2, "failed": 0})
    ):
        assert await tasks._run_scheduled_scans_async("t1", db=object()) == {
            "ran": 2,
            "failed": 0,
        }


@pytest.mark.asyncio
async def test_run_due_scans_runs_only_due_enabled_scans() -> None:
    """Only enabled, due scans execute; success returns counts."""
    sc = _scanner("t1")
    sc.scan_configs[ScanType.PORT_SCAN]["enabled"] = False

    async def should(st: ScanType, _c: dict[str, Any]) -> bool:
        return st in (ScanType.THREAT_INTEL_SCAN, ScanType.PORT_SCAN)

    ex = AsyncMock(return_value=True)
    with (
        patch.object(sc, "_should_run_scan", side_effect=should),
        patch.object(sc, "_execute_scan", new=ex),
    ):
        assert await sc.run_due_scans() == {"ran": 1, "failed": 0}
    assert ex.await_args is not None
    assert ex.await_args.args[0] == ScanType.THREAT_INTEL_SCAN


@pytest.mark.asyncio
async def test_run_due_scans_fails_loudly() -> None:
    """Any failed scan raises RuntimeError naming it."""
    sc = _scanner("t1")
    with (
        patch.object(sc, "_should_run_scan", new=AsyncMock(return_value=True)),
        patch.object(sc, "_execute_scan", new=AsyncMock(return_value=False)),
        pytest.raises(RuntimeError, match="threat_intel"),
    ):
        await sc.run_due_scans()


@pytest.mark.asyncio
async def test_run_due_scans_requires_tenant() -> None:
    """Untenanted scanner refuses scheduled runs."""
    with pytest.raises(RuntimeError):
        await _scanner(None).run_due_scans()


@pytest.mark.asyncio
async def test_execute_scan_returns_false_on_failure() -> None:
    """_execute_scan records failure and returns False instead of hiding it."""
    sc = _scanner("t1")
    with patch(
        "hub_api.modules.sase.security.scanner.scans.execute_scan_by_type",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        assert await sc._execute_scan(ScanType.THREAT_INTEL_SCAN, {}) is False


def test_celery_task_dispatches_tenant() -> None:
    """The Celery entry point runs the async path with the job's tenant."""
    run = AsyncMock(return_value={"ran": 0, "failed": 0})
    with patch.object(tasks, "_run_scheduled_scans_async", new=run):
        assert tasks.run_scheduled_scans("job-123456789", "t1", "m", "j", {}) == {
            "ran": 0,
            "failed": 0,
        }
    run.assert_awaited_once_with("t1")
