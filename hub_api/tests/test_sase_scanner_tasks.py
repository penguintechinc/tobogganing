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


async def _add_user(db: Any, tenant: str) -> None:
    """Insert a minimal users row for ``tenant`` into the real DAL."""
    from datetime import datetime
    from uuid import uuid4

    uid = uuid4().hex
    await db.users.async_insert(
        id=uid,
        username=f"u{uid[:8]}",
        email=f"{uid[:8]}@example.invalid",
        password_hash="x",
        role="reporter",
        tenant=tenant,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        mfa_enabled=False,
    )


async def _scan_jobs(db: Any, tenant: str) -> list[dict[str, Any]]:
    """List scanner jobs for a tenant via the real JobManager."""
    from hub_api.scheduler.job_manager import JobManager

    return await JobManager(db).list_jobs(tenant, module=tasks.SCANNER_MODULE)


@pytest.mark.asyncio
async def test_ensure_security_scan_job_idempotent_real_dal(real_dal: Any) -> None:
    """Second ensure for the same tenant creates nothing; exactly one job persists."""
    assert await tasks.ensure_security_scan_job(real_dal, "t1") is True
    assert await tasks.ensure_security_scan_job(real_dal, "t1") is False
    jobs = await _scan_jobs(real_dal, "t1")
    assert len(jobs) == 1 and jobs[0]["job_type"] == tasks.SCANNER_JOB_TYPE


@pytest.mark.asyncio
async def test_ensure_all_tenants_backfills_once_real_dal(real_dal: Any) -> None:
    """Sweep creates one job per distinct users.tenant and is a no-op on re-run."""
    for tenant in ("ta", "ta", "tb"):
        await _add_user(real_dal, tenant)
    assert await tasks.ensure_scan_jobs_for_all_tenants(real_dal) == 2
    assert await tasks.ensure_scan_jobs_for_all_tenants(real_dal) == 0
    assert len(await _scan_jobs(real_dal, "ta")) == 1
    assert len(await _scan_jobs(real_dal, "tb")) == 1


@pytest.mark.asyncio
async def test_ensure_security_scan_job_requires_tenant() -> None:
    """Empty tenant is rejected."""
    with pytest.raises(ValueError):
        await tasks.ensure_security_scan_job(object(), "")


@pytest.mark.asyncio
async def test_create_user_onboards_tenant_scan_job_real_dal(real_dal: Any) -> None:
    """Creating a user in a new tenant creates that tenant's scan job (once)."""
    from hub_api.core.auth import UserManager

    mgr = UserManager.__new__(UserManager)
    mgr.db = real_dal
    await mgr.create_user("alice", "a@example.invalid", "pw-Long-1234", "tn")
    await mgr.create_user("bob", "b@example.invalid", "pw-Long-1234", "tn")
    assert len(await _scan_jobs(real_dal, "tn")) == 1


@pytest.mark.asyncio
async def test_onboarding_failure_logged_not_raised() -> None:
    """Onboarding hook failure is logged at ERROR, user creation is not aborted."""
    from hub_api.core import auth

    mgr = auth.UserManager.__new__(auth.UserManager)
    mgr.db = object()
    with (
        patch(
            "hub_api.modules.sase.security.scanner.tasks.ensure_security_scan_job",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ),
        patch.object(auth, "logger") as log,
    ):
        await mgr._ensure_tenant_onboarded("t1")
    assert log.error.call_args.args[0] == "tenant_scan_job_onboarding_failed"


def test_ensure_sweep_task_runs_async_path() -> None:
    """Beat task delegates to the async ensure path."""
    run = AsyncMock(return_value=3)
    with patch.object(tasks, "_ensure_scan_jobs_async", new=run):
        assert tasks.ensure_scan_jobs_sweep() == 3


def test_celery_worker_includes_task_modules() -> None:
    """Worker include list and beat schedule cover scanner, backup and sweep tasks."""
    import importlib

    from hub_api.scheduler.celery_app import celery_app

    include = list(celery_app.conf.include or [])
    for mod in (
        "hub_api.scheduler.tasks",
        "hub_api.core.backup.tasks",
        "hub_api.modules.sase.security.scanner.tasks",
    ):
        assert mod in include
        importlib.import_module(mod)
    for name in (tasks.SCANNER_TASK_NAME, tasks.ENSURE_JOBS_TASK_NAME):
        assert name in celery_app.tasks
    beat = celery_app.conf.beat_schedule
    assert beat["sase-scanner-ensure-jobs"]["task"] == tasks.ENSURE_JOBS_TASK_NAME
