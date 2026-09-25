# W2 — Auto Check-ins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-facing `AutoCheckIn` configuration entity (tenant-scoped CRUD + admin UI) that compiles down to the existing scheduler/probe/tier-cascade primitives — schema, manager, `auto_checkin_cycle` job handler, REST API, and portal page — so admins can configure per-tier (1/2/3) check-ins with jitter, multi-sample std-dev thresholds, and cascading tier-2/3 execution, without touching the generic scheduler or the pre-existing `AutoPerfPolicy` feature.

**Architecture:** `AutoCheckIn` is a new table (`auto_checkins`) + a lightweight cascade-state table (`auto_checkin_state`, tracks `last_breached`/`last_mean_latency_ms`/`last_stddev_latency_ms` per check-in). Each `AutoCheckIn` materializes exactly one `scheduled_jobs` row (`job_type="auto_checkin"`, reusing the existing Celery Beat sweep — no new scheduler) via the same "scan `list_jobs` by `payload.checkin_id`" pattern `AutoPerfManager` already uses (no stored job-id FK). Tier is a **static, admin-set column** on each row (not a computed escalation state like `AutoPerfPolicy.current_tier`): a tier-2/3 check-in points at its tier-(N-1) parent via `parent_checkin_id`, and its `auto_checkin_cycle` job handler skips probe execution (but still reschedules with jitter) unless the parent's `auto_checkin_state.last_breached` is `True`. This is a **different cascade mechanism from `AutoPerfManager.record_cycle()`'s single-row auto-escalating state machine** (see "Resolved ambiguities" below for why) — the *already-merged* `_test_types_for_tier()` default-set helper and `ThroughputBackend` seam ARE reused (for the default `test_types` value and transparently via `EngineClient.run_test`). Each cycle runs `samples_per_run` probes per configured `test_type`, computes mean/population-stddev across all collected latencies, and evaluates the three optional threshold columns; a breach writes an `auto_checkin_state` row, an `alert_events` row (reusing the existing table/shape `autoperf_cycle` already reads), and fires `NotificationService.notify()` (best-effort, never raises).

**Tech Stack:** Python 3.13, Quart (async blueprints, no quart-schema in this module — manual dict validation matching `scheduled_tests.py`/`autoperf.py`), penguin-dal AsyncDB (runtime queries), SQLAlchemy + Alembic (schema authority), structlog, Celery Beat (existing sweep, unmodified), React + TypeScript + `@tanstack/react-query` (portal), Jest + Testing Library (portal tests), pytest + pytest-asyncio + `real_dal` (migrated temp-sqlite) fixture (backend tests).

**Spec:** `docs/superpowers/specs/2026-08-21-perftest-probe-suite-design.md` — "Core data model — the Auto Check-in" table, Phases table row W2.

## Global Constraints

- Python 3.13; Quart async routes only; penguin-dal for all runtime queries, SQLAlchemy/Alembic for schema; structlog for all logging (no `print`).
- 90% coverage floor, `make test-cov` runs `pytest hub_api/tests/ --cov=hub_api --cov-report=term-missing --cov-fail-under=90` — builds fail below threshold. Portal: `portal/jest.config.js` `coverageThreshold` (90%).
- Every feature behind a PostHog flag defaulted OFF (`tobogganing.perftest.cluster.auto_checkins`) + license gate via `@require_feature("perftest.cluster", "auto_checkins")` — entitlement tier **professional** (see "Resolved ambiguities").
- Tenant-scoped at the query layer via the validated JWT claim (`current_claims()["tenant"]`) — never from request body/params.
- Migration revision `"0027"`, `down_revision = "0026"` (current head, confirmed via `ls hub_api/migrations/versions/`).
- No new scheduler — reuse the existing Celery Beat sweep (`hub_api/scheduler/tasks.py::sweep`) and `register_job_handler` registry; supercronic/no-cron rule already satisfied by Celery.
- Every endpoint's response is an explicit dict projection (never a raw DAL row / `**row.__dict__`) — `AutoCheckInManager` methods already return hand-built dicts; API handlers spread only those.
- `engines/testserver` schema/migration-ownership mismatch flagged in the W1 plan is pre-existing and out of scope here.

## Resolved ambiguities (from the spec / task brief)

1. **AutoCheckIn tiers do NOT reuse `autoperf_policies`/`autoperf_state`/`record_cycle()`.** The design spec models tier 1/2/3 as three *separately admin-configured* rows, each with its own `test_types`/`interval_minutes`/`jitter_pct`/`samples_per_run`/thresholds — `AutoPerfPolicy`'s tier model is the opposite: ONE row whose `current_tier` is a computed, auto-escalating/de-escalating derived state, with test types hardcoded per tier via `_test_types_for_tier()`. Overloading `AutoPerfPolicy` to carry per-tier admin-configurable test_types/thresholds would require bolting exactly the columns this task instructs us not to add to it. AutoCheckIn instead reuses the *concept* (tier cascade, escalation-on-breach) and the *already-merged* `_test_types_for_tier()` (as the default `test_types` value at creation) + `ThroughputBackend` seam (transitively, via `EngineClient.run_test`), via a new, much simpler binary breach-cascade: `parent_checkin_id` + `auto_checkin_state.last_breached`.
2. **`source_client` (spec) = `device_id` column.** The `devices` table already covers both "server" and "end-user client" enrollments (per spec: "source client... a server or an end-user client (the agent that runs the probes)"), and `autoperf_policies.device_id` already established this FK-by-convention (no DB-level FK constraint, matching the rest of this module). Reusing the name keeps `DeviceManager.get_device()` reuse obvious.
3. **`threshold_stddev_min/max/mean` semantics.** The spec table says only "acceptable std-dev ranges: min / max / mean", which is underspecified. Resolved as three independent, independently-optional bounds evaluated against the cycle's collected latency samples: `threshold_stddev_min` = minimum acceptable population stddev (breach if computed stddev is *below* it — guards against suspiciously invariant/cached responses), `threshold_stddev_max` = maximum acceptable population stddev (the primary jitter/instability guard), `threshold_mean` = maximum acceptable mean latency in ms (a simple SLA-style ceiling, independent of spread). Breach = any configured bound is violated (OR, not AND). All three `None` (no thresholds configured) ⇒ never breaches — the check-in just collects history.
4. **Samples aggregation scope.** `samples_per_run` (1-5) samples are collected for *each* configured `test_type` and then **flattened into one list** for the mean/stddev computation (not computed per-test-type) — the spec's threshold triple is singular ("std-dev ranges: min/max/mean"), not per-protocol, so one aggregate stat per cycle is the direct reading.
5. **Jitter is applied by the `auto_checkin_cycle` task itself, not `JobManager`.** The generic sweep (`hub_api/scheduler/tasks.py::_sweep_async`) calls `JobManager.mark_ran()` immediately after dispatching (fire-and-forget, before the Celery task body runs), which sets `next_run_at = now + interval_seconds` with no jitter. Rather than change `JobManager`'s shared signature (used by every scheduled job type, including `AutoPerfPolicy`/`server_test`), `auto_checkin_cycle` does a **second, targeted `scheduled_jobs.next_run_at` write** at the end of its own run, nudging it by ±`jitter_pct`% via an injectable RNG. This keeps the generic scheduler untouched, matching "no new scheduler."
6. **Structural fields are immutable after creation.** `device_id`, `target_kind`, `tier`, `parent_checkin_id` cannot be changed via `PATCH` — changing them would require re-validating the tier chain and any children pointing at this row; callers create a new check-in instead. `PATCH` supports `name`/`target`/`test_types`/`interval_minutes`/`jitter_pct`/`samples_per_run`/the three threshold fields/`enabled`.
7. **Entitlement tier: professional.** AutoCheckIn's tier cascade is the productized version of `AutoPerfPolicy`'s escalation logic (already gated `professional`); gating AutoCheckIn at the same tier keeps the two escalation features consistent.
8. **Deleting a check-in with dependents is rejected (409),** not cascaded — avoids silently orphaning `parent_checkin_id` references on tier-2/3 rows. Caller deletes children first.

## File Structure

| File | Responsibility |
|---|---|
| `hub_api/migrations/versions/0027_auto_checkins.py` | Create `auto_checkins` + `auto_checkin_state` tables |
| `hub_api/db/models.py` | Add `AutoCheckIn`, `AutoCheckInState` SQLAlchemy models (schema authority) |
| `hub_api/tests/test_migrations_head.py` | Register the two new tables/models in the coverage assertions |
| `hub_api/modules/perftest_cluster/services/auto_checkin_manager.py` | `AutoCheckInManager` — CRUD, tier/parent validation, scheduler job wiring |
| `hub_api/tests/test_auto_checkin_manager.py` | Manager unit tests (real_dal) |
| `hub_api/modules/perftest_cluster/worker/tasks.py` | Add `_jittered_interval_seconds`, `_apply_jitter`, `_compute_sample_stats`, `_evaluate_threshold_breach`, `_execute_auto_checkin_sample`, `_run_auto_checkin_samples`, `_auto_checkin_cycle_async`, `auto_checkin_cycle` Celery task |
| `hub_api/tests/perftest/test_auto_checkin_worker_tasks.py` | Worker task unit tests (fake engines + real_dal) |
| `hub_api/modules/perftest_cluster/api/auto_checkins.py` | REST blueprint: CRUD + state |
| `hub_api/tests/test_auto_checkins_api.py` | HTTP-level API tests (flag/license gating + CRUD) |
| `hub_api/modules/perftest_cluster/api/__init__.py` | Register the new blueprint |
| `hub_api/modules/perftest_cluster/__init__.py` | Nav entry, feature flag, entitlement, migration id, job handler registration |
| `hub_api/tests/perftest/conftest.py` | Patch `get_db` in the new API module for the shared `app_all_perftest_realdal` fixture |
| `portal/src/api/wpcOps.ts` | `AutoCheckIn`/`AutoCheckInState` interfaces + CRUD functions |
| `portal/src/pages/waddleperf/AutoCheckInsPage.tsx` | Admin CRUD page |
| `portal/src/pages/waddleperf/AutoCheckInsPage.test.tsx` | Page tests |
| `portal/src/routes/wpcViews.ts` | Register `auto-checkins` view slug |
| `openapi/v1.yaml` | Regenerated (`make openapi`) to include the new routes |

---

## Task 0 — Baseline verification (already run, documented here)

Ran the five salvaged test files against a fresh worktree venv before planning any further:

```bash
cd hub_api && uv venv -p 3.13 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
python3 -m pytest tests/test_wpc_engine_client.py tests/test_autoperf_tier_types.py \
  tests/perftest/test_wpc_worker_tasks.py tests/perftest/test_live_test_gaps.py \
  tests/test_autoperf_manager.py -v
```

**Result: 91 passed in 91.42s.** (Note: `test_wpc_worker_tasks.py` lives at `hub_api/tests/perftest/test_wpc_worker_tasks.py`, not the top-level `hub_api/tests/` the task brief listed — path corrected here.) Baseline is green — proceed.

---

## Task 1: AutoCheckIn schema + manager

**Files:**
- Create: `hub_api/migrations/versions/0027_auto_checkins.py`
- Modify: `hub_api/db/models.py` (append `AutoCheckIn`, `AutoCheckInState` after `AutoPerfState`, before `DNSZone`)
- Modify: `hub_api/tests/test_migrations_head.py` (register new tables + models)
- Create: `hub_api/modules/perftest_cluster/services/auto_checkin_manager.py`
- Create: `hub_api/tests/test_auto_checkin_manager.py`

**Interfaces:**
- `AutoCheckInManager(db: Any)` — raises `ValueError` if `db is None`.
- `async def create_checkin(tenant: str, name: str, device_id: str, target_kind: str, target: str, test_types: list[str], interval_minutes: int = 5, jitter_pct: int = 0, samples_per_run: int = 1, threshold_stddev_min: float | None = None, threshold_stddev_max: float | None = None, threshold_mean: float | None = None, tier: int = 1, parent_checkin_id: str | None = None, enabled: bool = True) -> dict[str, Any]` — raises `ValueError` on any bound/parent violation.
- `async def list_checkins(tenant: str) -> list[dict[str, Any]]`
- `async def get_checkin(tenant: str, checkin_id: str) -> dict[str, Any] | None`
- `async def get_state(tenant: str, checkin_id: str) -> dict[str, Any] | None`
- `async def update_checkin(tenant: str, checkin_id: str, **fields: Any) -> dict[str, Any] | None`
- `async def delete_checkin(tenant: str, checkin_id: str) -> bool` — raises `ValueError` if the check-in has dependents.
- Produces (consumed by Task 2/3): the `auto_checkins` row dict shape — `id, tenant, name, device_id, target_kind, target, test_types (list[str]), interval_minutes, jitter_pct, samples_per_run, threshold_stddev_min, threshold_stddev_max, threshold_mean, tier, parent_checkin_id, enabled, created_at, updated_at` — and the `auto_checkin_state` row dict shape — `checkin_id, last_breached, last_mean_latency_ms, last_stddev_latency_ms, last_run_at, updated_at`.
- Consumes: `hub_api.scheduler.job_manager.JobManager` (`create_job`, `list_jobs`, `set_enabled`, `delete_job` — all already exist, unmodified), `hub_api.modules.perftest_cluster.services.engine_client.ALLOWED_TEST_TYPES`.

### Step 1: Write the failing test

`hub_api/tests/test_auto_checkin_manager.py`:

```python
"""Tests for AutoCheckInManager: CRUD, tier/parent validation, scheduler wiring."""
from __future__ import annotations

from typing import Any

import pytest

from hub_api.modules.perftest_cluster.services.auto_checkin_manager import (
    AutoCheckInManager,
)
from hub_api.scheduler.job_manager import JobManager


@pytest.mark.asyncio
async def test_create_checkin_round_trip(real_dal: Any) -> None:
    """Create a tier-1 check-in; verify row, state, and scheduler job."""
    manager = AutoCheckInManager(real_dal)
    jm = JobManager(real_dal)

    created = await manager.create_checkin(
        tenant="tenant1",
        name="Edge Wifi Baseline",
        device_id="dev-1",
        target_kind="external",
        target="example.com",
        test_types=["http_trace", "traceroute", "udp", "http2"],
        interval_minutes=5,
        jitter_pct=10,
        samples_per_run=3,
        threshold_stddev_max=50.0,
        tier=1,
    )

    assert created["id"]
    assert created["tenant"] == "tenant1"
    assert created["test_types"] == ["http_trace", "traceroute", "udp", "http2"]
    assert created["interval_minutes"] == 5
    assert created["jitter_pct"] == 10
    assert created["samples_per_run"] == 3
    assert created["threshold_stddev_max"] == 50.0
    assert created["tier"] == 1
    assert created["parent_checkin_id"] is None
    assert created["enabled"] is True

    state = await manager.get_state("tenant1", created["id"])
    assert state is not None
    assert state["last_breached"] is False
    assert state["last_run_at"] is None

    jobs = await jm.list_jobs("tenant1", "perftest_cluster")
    assert len(jobs) == 1
    assert jobs[0]["job_type"] == "auto_checkin"
    assert jobs[0]["payload"]["checkin_id"] == created["id"]
    assert jobs[0]["interval_seconds"] == 300


@pytest.mark.asyncio
async def test_create_checkin_bound_validation(real_dal: Any) -> None:
    """interval_minutes/jitter_pct/samples_per_run/tier/target_kind/test_types bounds."""
    manager = AutoCheckInManager(real_dal)

    with pytest.raises(ValueError, match="interval_minutes"):
        await manager.create_checkin(
            "t1", "bad", "dev1", "external", "example.com",
            ["icmp"], interval_minutes=61,
        )
    with pytest.raises(ValueError, match="jitter_pct"):
        await manager.create_checkin(
            "t1", "bad", "dev1", "external", "example.com",
            ["icmp"], jitter_pct=11,
        )
    with pytest.raises(ValueError, match="samples_per_run"):
        await manager.create_checkin(
            "t1", "bad", "dev1", "external", "example.com",
            ["icmp"], samples_per_run=6,
        )
    with pytest.raises(ValueError, match="target_kind"):
        await manager.create_checkin(
            "t1", "bad", "dev1", "bogus", "example.com", ["icmp"],
        )
    with pytest.raises(ValueError, match="test_types"):
        await manager.create_checkin(
            "t1", "bad", "dev1", "external", "example.com", ["not_a_real_type"],
        )


@pytest.mark.asyncio
async def test_create_checkin_tier2_requires_valid_parent(real_dal: Any) -> None:
    """tier=2 requires parent_checkin_id pointing at an existing tier-1 row."""
    manager = AutoCheckInManager(real_dal)

    with pytest.raises(ValueError, match="parent_checkin_id"):
        await manager.create_checkin(
            "t1", "orphan-tier2", "dev1", "external", "example.com",
            ["throughput"], tier=2,
        )

    tier1 = await manager.create_checkin(
        "t1", "tier1", "dev1", "external", "example.com", ["icmp"], tier=1,
    )

    with pytest.raises(ValueError, match="tier 1"):
        await manager.create_checkin(
            "t1", "wrong-parent-tier", "dev1", "external", "example.com",
            ["throughput"], tier=3, parent_checkin_id=tier1["id"],
        )

    tier2 = await manager.create_checkin(
        "t1", "tier2", "dev1", "external", "example.com",
        ["throughput"], tier=2, parent_checkin_id=tier1["id"],
    )
    assert tier2["parent_checkin_id"] == tier1["id"]

    with pytest.raises(ValueError, match="must not set parent_checkin_id"):
        await manager.create_checkin(
            "t1", "tier1-with-parent", "dev1", "external", "example.com",
            ["icmp"], tier=1, parent_checkin_id=tier1["id"],
        )


@pytest.mark.asyncio
async def test_update_checkin_interval_retunes_job(real_dal: Any) -> None:
    """Updating interval_minutes updates the scheduled job's interval_seconds."""
    manager = AutoCheckInManager(real_dal)
    jm = JobManager(real_dal)

    created = await manager.create_checkin(
        "t1", "retune", "dev1", "external", "example.com", ["icmp"], interval_minutes=5,
    )
    updated = await manager.update_checkin("t1", created["id"], interval_minutes=30)
    assert updated["interval_minutes"] == 30

    jobs = await jm.list_jobs("t1", "perftest_cluster")
    assert jobs[0]["interval_seconds"] == 1800


@pytest.mark.asyncio
async def test_delete_checkin_rejects_when_dependents_exist(real_dal: Any) -> None:
    """Deleting a check-in with tier-dependent children raises ValueError."""
    manager = AutoCheckInManager(real_dal)

    tier1 = await manager.create_checkin(
        "t1", "parent", "dev1", "external", "example.com", ["icmp"], tier=1,
    )
    await manager.create_checkin(
        "t1", "child", "dev1", "external", "example.com",
        ["throughput"], tier=2, parent_checkin_id=tier1["id"],
    )

    with pytest.raises(ValueError, match="tier dependency"):
        await manager.delete_checkin("t1", tier1["id"])


@pytest.mark.asyncio
async def test_delete_checkin_removes_state_and_job(real_dal: Any) -> None:
    """Deleting a leaf check-in removes its row, state, and scheduler job."""
    manager = AutoCheckInManager(real_dal)
    jm = JobManager(real_dal)

    created = await manager.create_checkin(
        "t1", "leaf", "dev1", "external", "example.com", ["icmp"], tier=1,
    )
    deleted = await manager.delete_checkin("t1", created["id"])
    assert deleted is True

    assert await manager.get_checkin("t1", created["id"]) is None
    assert await manager.get_state("t1", created["id"]) is None
    assert await jm.list_jobs("t1", "perftest_cluster") == []


@pytest.mark.asyncio
async def test_tenant_isolation(real_dal: Any) -> None:
    """Cross-tenant reads/deletes are invisible."""
    manager = AutoCheckInManager(real_dal)
    created = await manager.create_checkin(
        "tenant-a", "iso", "dev1", "external", "example.com", ["icmp"],
    )
    assert await manager.get_checkin("tenant-b", created["id"]) is None
    assert await manager.delete_checkin("tenant-b", created["id"]) is False
```

### Step 2: Run to verify it fails

`cd hub_api && source .venv/bin/activate && python3 -m pytest tests/test_auto_checkin_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub_api.modules.perftest_cluster.services.auto_checkin_manager'` (and, once that import exists, `no such table: auto_checkins` from the `real_dal` fixture's `alembic upgrade head`).

### Step 3: Migration

`hub_api/migrations/versions/0027_auto_checkins.py`:

```python
"""Create auto_checkins and auto_checkin_state tables.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create auto_checkins and auto_checkin_state tables."""
    op.create_table(
        "auto_checkins",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("test_types", sa.Text(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("jitter_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("samples_per_run", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("threshold_stddev_min", sa.Float(), nullable=True),
        sa.Column("threshold_stddev_max", sa.Float(), nullable=True),
        sa.Column("threshold_mean", sa.Float(), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_checkin_id", sa.String(36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_auto_checkins"),
    )
    op.create_index(
        "ix_auto_checkins_tenant", "auto_checkins", ["tenant"], unique=False,
    )
    op.create_index(
        "ix_auto_checkins_parent", "auto_checkins", ["parent_checkin_id"], unique=False,
    )

    op.create_table(
        "auto_checkin_state",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("checkin_id", sa.String(36), nullable=False, unique=True),
        sa.Column("last_breached", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_mean_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_stddev_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_auto_checkin_state"),
    )


def downgrade() -> None:
    """Drop auto_checkin_state and auto_checkins tables."""
    op.drop_table("auto_checkin_state")
    op.drop_index("ix_auto_checkins_parent", table_name="auto_checkins")
    op.drop_index("ix_auto_checkins_tenant", table_name="auto_checkins")
    op.drop_table("auto_checkins")
```

### Step 4: Models

Append to `hub_api/db/models.py` (after `AutoPerfState`, before `DNSZone`; `Boolean, Column, DateTime, Float, Integer, String, Text` already imported):

```python
class AutoCheckIn(Base):
    """Admin-configured Auto Check-in: compiles down to a scheduled_jobs row."""

    __tablename__ = "auto_checkins"

    id: Column[str] = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(36), nullable=False, index=True)
    name: Column[str] = Column(String(128), nullable=False)
    device_id: Column[str] = Column(String(36), nullable=False)
    target_kind: Column[str] = Column(String(16), nullable=False)
    target: Column[str] = Column(String(500), nullable=False)
    test_types: Column[str] = Column(Text, nullable=False)
    interval_minutes: Column[int] = Column(Integer, nullable=False, server_default="5")
    jitter_pct: Column[int] = Column(Integer, nullable=False, server_default="0")
    samples_per_run: Column[int] = Column(Integer, nullable=False, server_default="1")
    threshold_stddev_min: Column[float | None] = Column(Float, nullable=True)
    threshold_stddev_max: Column[float | None] = Column(Float, nullable=True)
    threshold_mean: Column[float | None] = Column(Float, nullable=True)
    tier: Column[int] = Column(Integer, nullable=False, server_default="1")
    parent_checkin_id: Column[str | None] = Column(String(36), nullable=True)
    enabled: Column[bool] = Column(Boolean, nullable=False, server_default="true")
    created_at: Column[datetime] = Column(DateTime, nullable=False)
    updated_at: Column[datetime] = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<AutoCheckIn(id={self.id}, tenant={self.tenant}, tier={self.tier})>"


class AutoCheckInState(Base):
    """Cascade breach-tracking state for an AutoCheckIn (tier-2/3 gate)."""

    __tablename__ = "auto_checkin_state"

    id: Column[str] = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(36), nullable=False, index=True)
    checkin_id: Column[str] = Column(String(36), nullable=False, unique=True)
    last_breached: Column[bool] = Column(Boolean, nullable=False, server_default="false")
    last_mean_latency_ms: Column[float | None] = Column(Float, nullable=True)
    last_stddev_latency_ms: Column[float | None] = Column(Float, nullable=True)
    last_run_at: Column[datetime | None] = Column(DateTime, nullable=True)
    updated_at: Column[datetime] = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<AutoCheckInState(checkin_id={self.checkin_id}, last_breached={self.last_breached})>"
```

### Step 5: `test_migrations_head.py` updates

- Add `AutoCheckIn, AutoCheckInState` to the `from hub_api.db.models import (...)` block, alphabetically between `AlertRule` and `AutoPerfPolicy`.
- Add a new set and fold it into `all_migration_tables`:

```python
    # Tables created by migration 0027 (Auto Check-in tier cascade — W2)
    created_by_migration_0027 = {
        "auto_checkins",
        "auto_checkin_state",
    }
```

  and add `| created_by_migration_0027` to the `all_migration_tables` union, plus a docstring line `Migration 0027: auto_checkins, auto_checkin_state`.
- Add `AutoCheckIn, AutoCheckInState` to `test_base_metadata_models_imported`'s `expected_models` list (after `AutoPerfState`) — closing the same "model added but not registered here" gap the 0026 regression comment already flags for `threatintel_feed_sources`' model.

### Step 6: Manager implementation

`hub_api/modules/perftest_cluster/services/auto_checkin_manager.py`:

```python
"""AutoCheckIn configuration manager: CRUD + tier/parent validation + scheduler wiring."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from hub_api.modules.perftest_cluster.services.engine_client import ALLOWED_TEST_TYPES
from hub_api.scheduler.job_manager import JobManager

log = structlog.get_logger(__name__)

VALID_TARGET_KINDS = {"ours", "external"}
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 60
MIN_JITTER_PCT = 0
MAX_JITTER_PCT = 10
MIN_SAMPLES_PER_RUN = 1
MAX_SAMPLES_PER_RUN = 5
VALID_TIERS = {1, 2, 3}


class AutoCheckInManager:
    """Manage AutoCheckIn configurations: CRUD, tier/parent validation, scheduler job wiring.

    Compiles each AutoCheckIn down to a `scheduled_jobs` row (job_type
    "auto_checkin") so the existing Celery Beat sweep drives it -- no new
    scheduler. Tier cascade is expressed via `parent_checkin_id` (validated
    here) and evaluated at cycle time by the `auto_checkin_cycle` worker task
    against `auto_checkin_state.last_breached`.
    """

    def __init__(self, db: Any) -> None:
        """Initialize manager with DAL instance.

        Args:
            db: penguin-dal AsyncDB instance.

        Raises:
            ValueError: If db is None.
        """
        if db is None:
            raise ValueError("Database instance cannot be None")
        self.db = db
        self.job_manager = JobManager(db)

    async def create_checkin(
        self,
        tenant: str,
        name: str,
        device_id: str,
        target_kind: str,
        target: str,
        test_types: list[str],
        interval_minutes: int = 5,
        jitter_pct: int = 0,
        samples_per_run: int = 1,
        threshold_stddev_min: float | None = None,
        threshold_stddev_max: float | None = None,
        threshold_mean: float | None = None,
        tier: int = 1,
        parent_checkin_id: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create an AutoCheckIn, its cascade-state row, and its scheduler job.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            name: Human-readable check-in name.
            device_id: Source client (server or end-user client) device ID.
            target_kind: "ours" (internal service) or "external" (URL/host:port).
            target: Test target.
            test_types: Non-empty list of probe types, each in ALLOWED_TEST_TYPES.
            interval_minutes: 1-60 (default 5).
            jitter_pct: 0-10, applied as +/- percent of interval (default 0).
            samples_per_run: 1-5 probe executions per test_type per cycle (default 1).
            threshold_stddev_min: Optional min acceptable stddev (ms) of cycle samples.
            threshold_stddev_max: Optional max acceptable stddev (ms) of cycle samples.
            threshold_mean: Optional max acceptable mean latency (ms) of cycle samples.
            tier: 1 (always runs), 2 (runs only when its tier-1 parent breaches), or 3
                (runs only when its tier-2 parent breaches).
            parent_checkin_id: Required when tier > 1 (must reference an existing
                tenant-owned check-in at tier - 1); forbidden when tier == 1.
            enabled: Whether the check-in starts enabled (default True).

        Returns:
            Created check-in row dict.

        Raises:
            ValueError: On any validation failure.
        """
        self._validate_bounds(
            target_kind, test_types, interval_minutes, jitter_pct, samples_per_run, tier
        )
        await self._validate_parent(tenant, tier, parent_checkin_id)

        now = datetime.now(timezone.utc)
        checkin_id = str(uuid4())
        test_types_json = json.dumps(test_types)

        await self.db.auto_checkins.async_insert(
            id=checkin_id,
            tenant=tenant,
            name=name,
            device_id=device_id,
            target_kind=target_kind,
            target=target,
            test_types=test_types_json,
            interval_minutes=interval_minutes,
            jitter_pct=jitter_pct,
            samples_per_run=samples_per_run,
            threshold_stddev_min=threshold_stddev_min,
            threshold_stddev_max=threshold_stddev_max,
            threshold_mean=threshold_mean,
            tier=tier,
            parent_checkin_id=parent_checkin_id,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

        await self.db.auto_checkin_state.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            checkin_id=checkin_id,
            last_breached=False,
            last_mean_latency_ms=None,
            last_stddev_latency_ms=None,
            last_run_at=None,
            updated_at=now,
        )

        await self.job_manager.create_job(
            tenant=tenant,
            module="perftest_cluster",
            job_type="auto_checkin",
            payload={"checkin_id": checkin_id},
            interval_seconds=interval_minutes * 60,
            enabled=enabled,
        )

        return {
            "id": checkin_id,
            "tenant": tenant,
            "name": name,
            "device_id": device_id,
            "target_kind": target_kind,
            "target": target,
            "test_types": test_types,
            "interval_minutes": interval_minutes,
            "jitter_pct": jitter_pct,
            "samples_per_run": samples_per_run,
            "threshold_stddev_min": threshold_stddev_min,
            "threshold_stddev_max": threshold_stddev_max,
            "threshold_mean": threshold_mean,
            "tier": tier,
            "parent_checkin_id": parent_checkin_id,
            "enabled": enabled,
            "created_at": now,
            "updated_at": now,
        }

    async def list_checkins(self, tenant: str) -> list[dict[str, Any]]:
        """List all AutoCheckIns for a tenant.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.

        Returns:
            List of check-in row dicts.
        """
        rowset = await self.db(self.db.auto_checkins.tenant == tenant).select()
        return [self._row_to_dict(row) for row in rowset]

    async def get_checkin(self, tenant: str, checkin_id: str) -> dict[str, Any] | None:
        """Get a single AutoCheckIn, tenant-scoped.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to retrieve.

        Returns:
            Check-in row dict, or None if not found/cross-tenant.
        """
        rowset = await self.db(
            (self.db.auto_checkins.tenant == tenant) & (self.db.auto_checkins.id == checkin_id)
        ).select()
        row = rowset.first()
        return self._row_to_dict(row) if row else None

    async def get_state(self, tenant: str, checkin_id: str) -> dict[str, Any] | None:
        """Get cascade state for a check-in, tenant-scoped.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to retrieve state for.

        Returns:
            State row dict, or None if not found/cross-tenant.
        """
        rowset = await self.db(
            (self.db.auto_checkin_state.tenant == tenant)
            & (self.db.auto_checkin_state.checkin_id == checkin_id)
        ).select()
        row = rowset.first()
        if not row:
            return None
        return {
            "checkin_id": row.checkin_id,
            "last_breached": row.last_breached,
            "last_mean_latency_ms": row.last_mean_latency_ms,
            "last_stddev_latency_ms": row.last_stddev_latency_ms,
            "last_run_at": row.last_run_at,
            "updated_at": row.updated_at,
        }

    async def update_checkin(
        self, tenant: str, checkin_id: str, **fields: Any
    ) -> dict[str, Any] | None:
        """Update mutable fields of an AutoCheckIn.

        Structural fields (device_id, target_kind, tier, parent_checkin_id) are
        immutable after creation -- changing them would require re-validating
        the tier chain and any children pointing at this row; create a new
        check-in instead. Unrecognized/None-valued keys in `fields` are ignored
        (this method is called with `**data` from the API's PATCH handler,
        which may include unrelated keys).

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to update.
            **fields: Any of name/target/test_types/interval_minutes/jitter_pct/
                samples_per_run/threshold_stddev_min/threshold_stddev_max/
                threshold_mean/enabled.

        Returns:
            Updated check-in row dict, or None if not found/cross-tenant.

        Raises:
            ValueError: On bound violations for the fields being updated.
        """
        existing = await self.get_checkin(tenant, checkin_id)
        if existing is None:
            return None

        allowed = {
            "name", "target", "test_types", "interval_minutes", "jitter_pct",
            "samples_per_run", "threshold_stddev_min", "threshold_stddev_max",
            "threshold_mean", "enabled",
        }
        updates: dict[str, Any] = {
            k: v for k, v in fields.items() if k in allowed and v is not None
        }

        if "test_types" in updates:
            unsupported = set(updates["test_types"]) - ALLOWED_TEST_TYPES
            if unsupported:
                raise ValueError(f"Unsupported test_types: {sorted(unsupported)}")
            updates["test_types"] = json.dumps(updates["test_types"])

        if "interval_minutes" in updates:
            iv = updates["interval_minutes"]
            if not (MIN_INTERVAL_MINUTES <= iv <= MAX_INTERVAL_MINUTES):
                raise ValueError(
                    f"interval_minutes must be {MIN_INTERVAL_MINUTES}-{MAX_INTERVAL_MINUTES}"
                )
        if "jitter_pct" in updates:
            jp = updates["jitter_pct"]
            if not (MIN_JITTER_PCT <= jp <= MAX_JITTER_PCT):
                raise ValueError(f"jitter_pct must be {MIN_JITTER_PCT}-{MAX_JITTER_PCT}")
        if "samples_per_run" in updates:
            sp = updates["samples_per_run"]
            if not (MIN_SAMPLES_PER_RUN <= sp <= MAX_SAMPLES_PER_RUN):
                raise ValueError(
                    f"samples_per_run must be {MIN_SAMPLES_PER_RUN}-{MAX_SAMPLES_PER_RUN}"
                )

        now = datetime.now(timezone.utc)
        updates["updated_at"] = now
        await self.db(
            (self.db.auto_checkins.tenant == tenant) & (self.db.auto_checkins.id == checkin_id)
        ).update(**updates)

        job = await self._find_job(tenant, checkin_id)
        if job:
            if "interval_minutes" in updates:
                await self.db(self.db.scheduled_jobs.id == job["id"]).update(
                    interval_seconds=updates["interval_minutes"] * 60, updated_at=now
                )
            if "enabled" in updates:
                await self.job_manager.set_enabled(tenant, job["id"], updates["enabled"])

        return await self.get_checkin(tenant, checkin_id)

    async def delete_checkin(self, tenant: str, checkin_id: str) -> bool:
        """Delete a check-in, its state, and its scheduler job.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to delete.

        Returns:
            True if deleted, False if not found/cross-tenant.

        Raises:
            ValueError: If another check-in references this one as its tier
                parent (dependents must be deleted first).
        """
        existing = await self.get_checkin(tenant, checkin_id)
        if existing is None:
            return False

        dependents = await self.db(
            (self.db.auto_checkins.tenant == tenant)
            & (self.db.auto_checkins.parent_checkin_id == checkin_id)
        ).select()
        if len(dependents) > 0:
            raise ValueError(
                "Cannot delete a check-in that is a tier dependency for other check-ins"
            )

        job = await self._find_job(tenant, checkin_id)
        if job:
            await self.job_manager.delete_job(tenant, job["id"])

        await self.db(self.db.auto_checkin_state.checkin_id == checkin_id).delete()
        count = await self.db(
            (self.db.auto_checkins.tenant == tenant) & (self.db.auto_checkins.id == checkin_id)
        ).delete()
        return count > 0

    async def _find_job(self, tenant: str, checkin_id: str) -> dict[str, Any] | None:
        """Find the scheduled_jobs row for a check-in via payload.checkin_id.

        Mirrors AutoPerfManager's `_update_job_interval` lookup pattern -- no
        stored job-id FK, scan-and-match on payload instead.
        """
        jobs = await self.job_manager.list_jobs(tenant, "perftest_cluster")
        for job in jobs:
            if job["job_type"] == "auto_checkin" and job["payload"].get("checkin_id") == checkin_id:
                return job
        return None

    def _validate_bounds(
        self,
        target_kind: str,
        test_types: list[str],
        interval_minutes: int,
        jitter_pct: int,
        samples_per_run: int,
        tier: int,
    ) -> None:
        """Validate all scalar/enum bounds. Raises ValueError on the first violation."""
        if target_kind not in VALID_TARGET_KINDS:
            raise ValueError(f"target_kind must be one of {sorted(VALID_TARGET_KINDS)}")
        if not test_types:
            raise ValueError("test_types must be a non-empty list")
        unsupported = set(test_types) - ALLOWED_TEST_TYPES
        if unsupported:
            raise ValueError(f"Unsupported test_types: {sorted(unsupported)}")
        if not (MIN_INTERVAL_MINUTES <= interval_minutes <= MAX_INTERVAL_MINUTES):
            raise ValueError(
                f"interval_minutes must be {MIN_INTERVAL_MINUTES}-{MAX_INTERVAL_MINUTES}"
            )
        if not (MIN_JITTER_PCT <= jitter_pct <= MAX_JITTER_PCT):
            raise ValueError(f"jitter_pct must be {MIN_JITTER_PCT}-{MAX_JITTER_PCT}")
        if not (MIN_SAMPLES_PER_RUN <= samples_per_run <= MAX_SAMPLES_PER_RUN):
            raise ValueError(
                f"samples_per_run must be {MIN_SAMPLES_PER_RUN}-{MAX_SAMPLES_PER_RUN}"
            )
        if tier not in VALID_TIERS:
            raise ValueError(f"tier must be one of {sorted(VALID_TIERS)}")

    async def _validate_parent(
        self, tenant: str, tier: int, parent_checkin_id: str | None
    ) -> None:
        """Validate the parent_checkin_id / tier relationship.

        Raises ValueError if tier==1 has a parent set, tier>1 is missing a
        parent, the parent doesn't exist/cross-tenant, or the parent's tier
        isn't exactly tier - 1.
        """
        if tier == 1:
            if parent_checkin_id is not None:
                raise ValueError("tier 1 check-ins must not set parent_checkin_id")
            return

        if not parent_checkin_id:
            raise ValueError(f"tier {tier} check-ins require parent_checkin_id")

        parent = await self.get_checkin(tenant, parent_checkin_id)
        if parent is None:
            raise ValueError("parent_checkin_id not found or cross-tenant")
        if parent["tier"] != tier - 1:
            raise ValueError(
                f"parent_checkin_id must reference a tier {tier - 1} check-in, "
                f"got tier {parent['tier']}"
            )

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        """Project a DAL row into the explicit response dict shape."""
        return {
            "id": row.id,
            "tenant": row.tenant,
            "name": row.name,
            "device_id": row.device_id,
            "target_kind": row.target_kind,
            "target": row.target,
            "test_types": json.loads(row.test_types),
            "interval_minutes": row.interval_minutes,
            "jitter_pct": row.jitter_pct,
            "samples_per_run": row.samples_per_run,
            "threshold_stddev_min": row.threshold_stddev_min,
            "threshold_stddev_max": row.threshold_stddev_max,
            "threshold_mean": row.threshold_mean,
            "tier": row.tier,
            "parent_checkin_id": row.parent_checkin_id,
            "enabled": row.enabled,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
```

### Step 7: Run to verify it passes

`cd hub_api && source .venv/bin/activate && python3 -m pytest tests/test_auto_checkin_manager.py -v`
Expected: PASS (7 tests).

### Step 8: Commit

```bash
git add hub_api/migrations/versions/0027_auto_checkins.py hub_api/db/models.py \
  hub_api/tests/test_migrations_head.py \
  hub_api/modules/perftest_cluster/services/auto_checkin_manager.py \
  hub_api/tests/test_auto_checkin_manager.py
git commit -m "feat(perftest_cluster): AutoCheckIn schema + manager (tier cascade config, no scheduler change)"
```

---

## Task 2: AutoCheckIn worker cycle (jitter + cascade gate + threshold breach)

**Files:**
- Modify: `hub_api/modules/perftest_cluster/worker/tasks.py`
- Create: `hub_api/tests/perftest/test_auto_checkin_worker_tasks.py`

**Interfaces:**
- Consumes: `AutoCheckInManager` row/state shapes (Task 1); `EngineClient.run_test` / `ALLOWED_TEST_TYPES` / `EngineError` (already merged, `hub_api/modules/perftest_cluster/services/engine_client.py`); `_test_types_for_tier` (already merged, this file, line 40); `DeviceManager.get_device`, `TestManager.create_test` (already merged); `NotificationService.notify` (`hub_api.notifications.service`, signature `(tenant: str, subject: str, body: str, channel_ids: list[str] | None = None) -> dict[str, int]`).
- Produces (consumed by Task 3's `register_job_handler` call): Celery task name `"hub_api.modules.perftest_cluster.worker.tasks.auto_checkin_cycle"`, task payload shape `{"checkin_id": str}`.
- Produces (pure helpers, directly unit-testable):
  - `_jittered_interval_seconds(base_interval_seconds: int, jitter_pct: int, rng: Callable[[], float] = random.random) -> int`
  - `_compute_sample_stats(latencies: list[float]) -> tuple[float, float] | None`
  - `_evaluate_threshold_breach(mean_latency_ms: float, stddev_latency_ms: float, threshold_stddev_min: float | None, threshold_stddev_max: float | None, threshold_mean: float | None) -> bool`

### Step 1: Write the failing tests

`hub_api/tests/perftest/test_auto_checkin_worker_tasks.py`:

```python
"""Tests for the AutoCheckIn worker cycle: jitter, stats, cascade gate, breach."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.auto_checkin_manager import (
    AutoCheckInManager,
)
from hub_api.modules.perftest_cluster.services.engine_client import EngineError
from hub_api.modules.perftest_cluster.worker import tasks as wpc_tasks


class _FakeEngineFixedLatency:
    """Engine stub returning a fixed latency for every sample."""

    def __init__(self, latency_ms: float) -> None:
        self.latency_ms = latency_ms
        self.calls: list[str] = []

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(test_type)
        return {"latency_ms": self.latency_ms, "throughput": None, "output": "ok"}


class _FakeEngineSequence:
    """Engine stub returning successive latencies from a fixed list."""

    def __init__(self, latencies: list[float]) -> None:
        self._latencies = iter(latencies)

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        return {"latency_ms": next(self._latencies), "throughput": None, "output": "ok"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_jittered_interval_zero_pct_returns_base() -> None:
    """jitter_pct=0 always returns the base interval, regardless of rng."""
    assert wpc_tasks._jittered_interval_seconds(300, 0, rng=lambda: 0.99) == 300


def test_jittered_interval_bounds() -> None:
    """rng=0.0 -> lower bound (base * (1 - pct/100)); rng=1.0 -> upper bound."""
    assert wpc_tasks._jittered_interval_seconds(300, 10, rng=lambda: 0.0) == 270
    assert wpc_tasks._jittered_interval_seconds(300, 10, rng=lambda: 1.0) == 330
    assert wpc_tasks._jittered_interval_seconds(300, 10, rng=lambda: 0.5) == 300


def test_compute_sample_stats_empty_returns_none() -> None:
    """No samples collected -> no stats to evaluate."""
    assert wpc_tasks._compute_sample_stats([]) is None


def test_compute_sample_stats_single_sample_zero_stddev() -> None:
    """A single sample has population stddev 0.0 (not a StatisticsError)."""
    mean, stddev = wpc_tasks._compute_sample_stats([42.0])
    assert mean == 42.0
    assert stddev == 0.0


def test_compute_sample_stats_mean_and_stddev() -> None:
    """Known population mean/stddev for [10, 20, 30]."""
    mean, stddev = wpc_tasks._compute_sample_stats([10.0, 20.0, 30.0])
    assert mean == pytest.approx(20.0)
    assert stddev == pytest.approx(8.16496580927726)


def test_evaluate_threshold_breach_no_thresholds_never_breaches() -> None:
    """All three thresholds None -> never breaches."""
    assert wpc_tasks._evaluate_threshold_breach(999.0, 999.0, None, None, None) is False


def test_evaluate_threshold_breach_max_exceeded() -> None:
    assert wpc_tasks._evaluate_threshold_breach(10.0, 60.0, None, 50.0, None) is True


def test_evaluate_threshold_breach_min_undershoot() -> None:
    assert wpc_tasks._evaluate_threshold_breach(10.0, 1.0, 5.0, None, None) is True


def test_evaluate_threshold_breach_mean_exceeded() -> None:
    assert wpc_tasks._evaluate_threshold_breach(500.0, 5.0, None, None, 200.0) is True


def test_evaluate_threshold_breach_within_bounds() -> None:
    assert wpc_tasks._evaluate_threshold_breach(50.0, 10.0, 5.0, 50.0, 100.0) is False


# ---------------------------------------------------------------------------
# _apply_jitter (DB-touching)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_jitter_updates_next_run_at(real_dal: AsyncDB) -> None:
    """_apply_jitter writes a new next_run_at within the jittered bound."""
    from hub_api.scheduler.job_manager import JobManager

    jm = JobManager(real_dal)
    job = await jm.create_job(
        tenant="t1", module="perftest_cluster", job_type="auto_checkin",
        payload={"checkin_id": "c1"}, interval_seconds=300,
    )
    before = job["next_run_at"]

    await wpc_tasks._apply_jitter(real_dal, job["id"], 300, 10, rng=lambda: 1.0)

    updated = await jm.get_job("t1", job["id"])
    assert updated["next_run_at"] > before


# ---------------------------------------------------------------------------
# _auto_checkin_cycle_async (full cycle, real_dal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_checkin_cycle_tier1_runs_samples_and_records_state(
    real_dal: AsyncDB,
) -> None:
    """Tier-1 always runs; samples_per_run * len(test_types) probes executed."""
    manager = AutoCheckInManager(real_dal)
    checkin = await manager.create_checkin(
        tenant="t1", name="baseline", device_id="dev1", target_kind="external",
        target="example.com", test_types=["icmp", "http"], samples_per_run=3,
        threshold_stddev_max=100.0,
    )

    engine = _FakeEngineFixedLatency(12.5)
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1", tenant="t1", module="perftest_cluster", job_type="auto_checkin",
        payload={"checkin_id": checkin["id"]}, db=real_dal,
        engine_factory=lambda device: engine,
    )

    assert len(engine.calls) == 6  # 2 test_types * 3 samples

    state = await manager.get_state("t1", checkin["id"])
    assert state["last_breached"] is False
    assert state["last_mean_latency_ms"] == pytest.approx(12.5)
    assert state["last_stddev_latency_ms"] == pytest.approx(0.0)
    assert state["last_run_at"] is not None


@pytest.mark.asyncio
async def test_auto_checkin_cycle_breach_writes_alert_event(real_dal: AsyncDB) -> None:
    """A stddev-max breach writes an alert_events row keyed by the check-in id."""
    manager = AutoCheckInManager(real_dal)
    checkin = await manager.create_checkin(
        tenant="t1", name="jittery", device_id="dev1", target_kind="external",
        target="example.com", test_types=["icmp"], samples_per_run=3,
        threshold_stddev_max=1.0,
    )

    engine = _FakeEngineSequence([1.0, 50.0, 100.0])
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1", tenant="t1", module="perftest_cluster", job_type="auto_checkin",
        payload={"checkin_id": checkin["id"]}, db=real_dal,
        engine_factory=lambda device: engine,
    )

    state = await manager.get_state("t1", checkin["id"])
    assert state["last_breached"] is True

    events = await real_dal(
        (real_dal.alert_events.tenant == "t1")
        & (real_dal.alert_events.rule_id == checkin["id"])
    ).select()
    assert len(events) == 1
    assert events[0].device_id == "dev1"


@pytest.mark.asyncio
async def test_auto_checkin_cycle_tier2_skipped_when_parent_not_breached(
    real_dal: AsyncDB,
) -> None:
    """A tier-2 check-in whose parent hasn't breached runs no probes."""
    manager = AutoCheckInManager(real_dal)
    tier1 = await manager.create_checkin(
        tenant="t1", name="t1", device_id="dev1", target_kind="external",
        target="example.com", test_types=["icmp"], tier=1,
    )
    tier2 = await manager.create_checkin(
        tenant="t1", name="t2", device_id="dev1", target_kind="external",
        target="example.com", test_types=["throughput"], tier=2,
        parent_checkin_id=tier1["id"],
    )

    engine = _FakeEngineFixedLatency(5.0)
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job2", tenant="t1", module="perftest_cluster", job_type="auto_checkin",
        payload={"checkin_id": tier2["id"]}, db=real_dal,
        engine_factory=lambda device: engine,
    )

    assert engine.calls == []
    state = await manager.get_state("t1", tier2["id"])
    assert state["last_run_at"] is None  # untouched: cycle was a no-op


@pytest.mark.asyncio
async def test_auto_checkin_cycle_tier2_runs_when_parent_breached(
    real_dal: AsyncDB,
) -> None:
    """A tier-2 check-in runs its probes once its parent's state is breached."""
    manager = AutoCheckInManager(real_dal)
    tier1 = await manager.create_checkin(
        tenant="t1", name="t1", device_id="dev1", target_kind="external",
        target="example.com", test_types=["icmp"], tier=1,
    )
    tier2 = await manager.create_checkin(
        tenant="t1", name="t2", device_id="dev1", target_kind="external",
        target="example.com", test_types=["throughput"], tier=2,
        parent_checkin_id=tier1["id"],
    )

    now = datetime.now(timezone.utc)
    await real_dal(real_dal.auto_checkin_state.checkin_id == tier1["id"]).update(
        last_breached=True, last_run_at=now, updated_at=now,
    )

    engine = _FakeEngineFixedLatency(5.0)
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job2", tenant="t1", module="perftest_cluster", job_type="auto_checkin",
        payload={"checkin_id": tier2["id"]}, db=real_dal,
        engine_factory=lambda device: engine,
    )

    assert engine.calls == ["throughput"]
    state = await manager.get_state("t1", tier2["id"])
    assert state["last_run_at"] is not None


@pytest.mark.asyncio
async def test_auto_checkin_cycle_missing_checkin_returns_early(real_dal: AsyncDB) -> None:
    """Unknown checkin_id logs a warning and returns without raising."""
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1", tenant="t1", module="perftest_cluster", job_type="auto_checkin",
        payload={"checkin_id": "ghost"}, db=real_dal,
    )  # must not raise


@pytest.mark.asyncio
async def test_auto_checkin_cycle_engine_error_recorded_as_failed_sample(
    real_dal: AsyncDB,
) -> None:
    """EngineError during a sample is recorded as a failed PerfTestResult, not raised."""
    manager = AutoCheckInManager(real_dal)
    checkin = await manager.create_checkin(
        tenant="t1", name="flaky", device_id="dev1", target_kind="external",
        target="example.com", test_types=["icmp"], samples_per_run=1,
    )

    class _FakeEngineError:
        async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
            raise EngineError("engine unreachable")

    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1", tenant="t1", module="perftest_cluster", job_type="auto_checkin",
        payload={"checkin_id": checkin["id"]}, db=real_dal,
        engine_factory=lambda device: _FakeEngineError(),
    )  # must not raise

    state = await manager.get_state("t1", checkin["id"])
    assert state["last_mean_latency_ms"] is None  # no successful samples collected


def test_auto_checkin_cycle_celery_wrapper_invokes_asyncio_run(monkeypatch) -> None:
    """The sync Celery task wrapper delegates to asyncio.run with the async core."""
    called = {}

    def fake_run(coro: Any) -> None:
        called["coro"] = coro
        coro.close()

    monkeypatch.setattr(wpc_tasks.asyncio, "run", fake_run)
    wpc_tasks.auto_checkin_cycle("job1", "t1", "perftest_cluster", "auto_checkin", {"checkin_id": "c1"})
    assert "coro" in called
```

### Step 2: Run to verify it fails

`cd hub_api && source .venv/bin/activate && python3 -m pytest tests/perftest/test_auto_checkin_worker_tasks.py -v`
Expected: FAIL — `AttributeError: module 'hub_api.modules.perftest_cluster.worker.tasks' has no attribute '_jittered_interval_seconds'`.

### Step 3: Implementation

In `hub_api/modules/perftest_cluster/worker/tasks.py`:

1. Update the top-of-file imports:

```python
import asyncio
import json
import random
import statistics
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from hub_api.config import Config, build_db_uri
from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.engine_client import EngineClient, EngineError
from hub_api.modules.perftest_cluster.services.test_manager import TestManager
from hub_api.modules.perftest_cluster.services.autoperf_manager import AutoPerfManager
from hub_api.scheduler.celery_app import celery_app
from penguin_dal import AsyncDB
```

   (Adds `json`, `random`, `statistics`, `timedelta`, `uuid4` -- everything else already present. `AutoCheckInManager` is deliberately NOT imported here: `_auto_checkin_cycle_async` reads `auto_checkins`/`auto_checkin_state` rows directly via `db(...)`, matching `_autoperf_cycle_async`'s existing direct-row-read style rather than going through the manager.)

2. Append after `_test_types_for_tier` (after line 66, before `_execute_and_store_test`):

```python
def _jittered_interval_seconds(
    base_interval_seconds: int,
    jitter_pct: int,
    rng: Callable[[], float] = random.random,
) -> int:
    """Compute a jittered interval, +/- jitter_pct percent of the base.

    Args:
        base_interval_seconds: The check-in's configured interval in seconds.
        jitter_pct: 0-10, the maximum +/- percentage swing.
        rng: Random source returning a float in [0, 1) (default random.random;
            injectable for deterministic tests).

    Returns:
        Jittered interval in seconds, floored at 1 second.
    """
    if jitter_pct <= 0:
        return base_interval_seconds
    delta_fraction = (rng() * 2 - 1) * (jitter_pct / 100)
    jittered = base_interval_seconds * (1 + delta_fraction)
    return max(1, round(jittered))


async def _apply_jitter(
    db: Any,
    job_id: str,
    base_interval_seconds: int,
    jitter_pct: int,
    rng: Callable[[], float] = random.random,
) -> None:
    """Nudge a scheduled_jobs row's next_run_at by +/- jitter_pct percent.

    The generic sweep (hub_api/scheduler/tasks.py::_sweep_async) already
    advanced next_run_at to now + interval_seconds via JobManager.mark_ran()
    before this task's body ran (fire-and-forget dispatch). This is a second,
    targeted write that layers jitter on top -- JobManager's shared mark_ran
    signature (used by every job type) is intentionally left untouched.

    Args:
        db: AsyncDB instance.
        job_id: The auto_checkin's scheduled_jobs row id.
        base_interval_seconds: The check-in's configured interval in seconds.
        jitter_pct: 0-10.
        rng: Injectable random source (see _jittered_interval_seconds).
    """
    jittered_seconds = _jittered_interval_seconds(base_interval_seconds, jitter_pct, rng)
    next_run_at = datetime.now(timezone.utc) + timedelta(seconds=jittered_seconds)
    await db(db.scheduled_jobs.id == job_id).update(next_run_at=next_run_at)


def _compute_sample_stats(latencies: list[float]) -> tuple[float, float] | None:
    """Compute (mean, population stddev) across a cycle's collected latencies.

    Population stddev (not sample stddev) is used because the N samples
    collected this cycle ARE the entire population being measured for this
    cycle, not an estimate of a larger unknown population -- this also
    handles samples_per_run == 1 (stddev 0.0) without raising, unlike
    statistics.stdev which requires at least 2 data points.

    Args:
        latencies: Flat list of latency_ms values across all (test_type,
            sample) executions that returned a numeric result this cycle.

    Returns:
        (mean, stddev) tuple, or None if latencies is empty (no successful
        samples this cycle -- nothing to evaluate).
    """
    if not latencies:
        return None
    return (statistics.fmean(latencies), statistics.pstdev(latencies))


def _evaluate_threshold_breach(
    mean_latency_ms: float,
    stddev_latency_ms: float,
    threshold_stddev_min: float | None,
    threshold_stddev_max: float | None,
    threshold_mean: float | None,
) -> bool:
    """Evaluate a cycle's aggregate stats against the check-in's thresholds.

    Each of the three threshold fields is independently optional; breach is
    an OR across whichever are configured. All three None means the check-in
    has no failure condition configured (it only collects history).

    Args:
        mean_latency_ms: Cycle's aggregate mean latency.
        stddev_latency_ms: Cycle's aggregate population stddev.
        threshold_stddev_min: Optional min acceptable stddev.
        threshold_stddev_max: Optional max acceptable stddev.
        threshold_mean: Optional max acceptable mean latency.

    Returns:
        True if any configured threshold is violated.
    """
    if threshold_stddev_min is not None and stddev_latency_ms < threshold_stddev_min:
        return True
    if threshold_stddev_max is not None and stddev_latency_ms > threshold_stddev_max:
        return True
    if threshold_mean is not None and mean_latency_ms > threshold_mean:
        return True
    return False


async def _execute_auto_checkin_sample(
    db: Any,
    tenant: str,
    device_id: str,
    test_type: str,
    target: str,
    engine_factory: EngineFactory,
) -> float | None:
    """Execute one AutoCheckIn probe sample, store it, and return its latency.

    Mirrors _execute_and_store_test's device-lookup/engine-call/error-handling
    shape (same TestManager storage, same EngineError/generic-exception
    handling) but returns the sample's latency_ms instead of a bool, since
    AutoCheckIn's std-dev threshold evaluation needs the numeric samples, not
    just pass/fail. _execute_and_store_test keeps its existing bool-only
    contract untouched -- it is covered by baseline tests
    (run_server_test/autoperf_cycle) this task must not break.

    Args:
        db: AsyncDB instance.
        tenant: Tenant ID.
        device_id: Device to test.
        test_type: Type of test.
        target: Test target.
        engine_factory: Callable to create EngineClient for the device.

    Returns:
        The sample's latency_ms, or None on device-not-found/engine error/
        unexpected error (each still recorded as a failed PerfTestResult row).
    """
    device_mgr = DeviceManager(db, tenant)
    device_row = await device_mgr.get_device(device_id)
    test_mgr = TestManager(db, tenant)

    if not device_row:
        logger.warning(
            "device_not_found_for_auto_checkin_sample",
            device_id=device_id, tenant=tenant, test_type=test_type,
        )
        await test_mgr.create_test({
            "device_id": device_id, "test_type": test_type, "target": target,
            "status": "failed", "latency_ms": None, "throughput": None,
            "test_output": "Device not found", "completed_at": datetime.now(timezone.utc),
        })
        return None

    engine = engine_factory(device_row)
    try:
        result = await engine.run_test(test_type, target)
        latency = result.get("latency_ms")
        await test_mgr.create_test({
            "device_id": device_id, "test_type": test_type, "target": target,
            "status": "completed", "latency_ms": latency,
            "throughput": result.get("throughput"), "test_output": result.get("output"),
            "completed_at": datetime.now(timezone.utc),
        })
        return float(latency) if latency is not None else None
    except EngineError as e:
        logger.warning(
            "engine_error_during_auto_checkin_sample",
            device_id=device_id, test_type=test_type, error=str(e),
        )
        await test_mgr.create_test({
            "device_id": device_id, "test_type": test_type, "target": target,
            "status": "failed", "latency_ms": None, "throughput": None,
            "test_output": f"Engine error: {str(e)}", "completed_at": datetime.now(timezone.utc),
        })
        return None
    except Exception as e:
        logger.error(
            "unexpected_error_during_auto_checkin_sample",
            device_id=device_id, test_type=test_type, error=str(e),
        )
        await test_mgr.create_test({
            "device_id": device_id, "test_type": test_type, "target": target,
            "status": "failed", "latency_ms": None, "throughput": None,
            "test_output": f"Error: {str(e)}", "completed_at": datetime.now(timezone.utc),
        })
        return None


async def _run_auto_checkin_samples(
    db: Any,
    tenant: str,
    device_id: str,
    test_types: list[str],
    target: str,
    samples_per_run: int,
    engine_factory: EngineFactory,
) -> list[float]:
    """Run samples_per_run executions of each test_type and collect latencies.

    Args:
        db: AsyncDB instance.
        tenant: Tenant ID.
        device_id: Device to test.
        test_types: Probe types to run this cycle.
        target: Test target.
        samples_per_run: Executions per test_type (1-5).
        engine_factory: Callable to create EngineClient for the device.

    Returns:
        Flat list of latency_ms values across all (test_type, sample)
        executions that returned a numeric latency -- failed/None samples are
        skipped (already recorded as failed PerfTestResult rows).
    """
    latencies: list[float] = []
    for test_type in test_types:
        for _ in range(samples_per_run):
            latency = await _execute_auto_checkin_sample(
                db, tenant, device_id, test_type, target, engine_factory
            )
            if latency is not None:
                latencies.append(latency)
    return latencies


async def _auto_checkin_cycle_async(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
    *,
    db: Any | None = None,
    engine_factory: EngineFactory | None = None,
) -> None:
    """Execute an AutoCheckIn cycle: cascade-gate, run samples, evaluate breach, reschedule.

    Tier 1 always runs. Tier 2/3 only run their probes when the parent
    check-in's most recent cycle breached (auto_checkin_state.last_breached);
    otherwise the cycle is a no-op except for jitter rescheduling. Never
    raises -- errors are logged and swallowed, matching run_server_test/
    autoperf_cycle.

    Args:
        job_id: The scheduled_jobs row id (used for the jitter reschedule write).
        tenant: Tenant identifier.
        module: Module name (should be "perftest_cluster").
        job_type: Job type (should be "auto_checkin").
        payload: Job payload dict with checkin_id.
        db: penguin-dal AsyncDB instance (created fresh if None).
        engine_factory: Callable to create EngineClient (default: _default_engine_factory).
    """
    engine_factory = engine_factory or _default_engine_factory

    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error(
                "failed_to_create_dal_auto_checkin", job_id=job_id, tenant=tenant, error=str(e),
            )
            return

    try:
        checkin_id = payload.get("checkin_id")
        if not checkin_id:
            logger.warning(
                "invalid_auto_checkin_payload", job_id=job_id, tenant=tenant, payload=payload,
            )
            return

        checkin_rowset = await db(
            (db.auto_checkins.tenant == tenant) & (db.auto_checkins.id == checkin_id)
        ).select()
        checkin = checkin_rowset.first()
        if not checkin:
            logger.warning(
                "auto_checkin_not_found", job_id=job_id, checkin_id=checkin_id, tenant=tenant,
            )
            return

        if not checkin.enabled:
            return

        base_interval_seconds = checkin.interval_minutes * 60

        if checkin.tier > 1:
            if not checkin.parent_checkin_id:
                logger.error(
                    "auto_checkin_tier_missing_parent", checkin_id=checkin_id, tenant=tenant,
                )
                await _apply_jitter(db, job_id, base_interval_seconds, checkin.jitter_pct)
                return

            parent_state_rowset = await db(
                (db.auto_checkin_state.tenant == tenant)
                & (db.auto_checkin_state.checkin_id == checkin.parent_checkin_id)
            ).select()
            parent_state = parent_state_rowset.first()

            if not parent_state or not parent_state.last_breached:
                logger.info(
                    "auto_checkin_skipped_parent_not_breached",
                    checkin_id=checkin_id, tenant=tenant, tier=checkin.tier,
                )
                await _apply_jitter(db, job_id, base_interval_seconds, checkin.jitter_pct)
                return

        test_types = json.loads(checkin.test_types)
        latencies = await _run_auto_checkin_samples(
            db, tenant, checkin.device_id, test_types, checkin.target,
            checkin.samples_per_run, engine_factory,
        )

        stats = _compute_sample_stats(latencies)
        mean_latency_ms, stddev_latency_ms = stats if stats else (None, None)

        breached = False
        if stats is not None:
            breached = _evaluate_threshold_breach(
                mean_latency_ms, stddev_latency_ms,
                checkin.threshold_stddev_min, checkin.threshold_stddev_max, checkin.threshold_mean,
            )

        now = datetime.now(timezone.utc)
        state_rowset = await db(
            (db.auto_checkin_state.tenant == tenant)
            & (db.auto_checkin_state.checkin_id == checkin_id)
        ).select()
        if state_rowset.first():
            await db(
                (db.auto_checkin_state.tenant == tenant)
                & (db.auto_checkin_state.checkin_id == checkin_id)
            ).update(
                last_breached=breached, last_mean_latency_ms=mean_latency_ms,
                last_stddev_latency_ms=stddev_latency_ms, last_run_at=now, updated_at=now,
            )
        else:
            await db.auto_checkin_state.async_insert(
                id=str(uuid4()), tenant=tenant, checkin_id=checkin_id,
                last_breached=breached, last_mean_latency_ms=mean_latency_ms,
                last_stddev_latency_ms=stddev_latency_ms, last_run_at=now, updated_at=now,
            )

        if breached:
            stddev_breached = (
                (checkin.threshold_stddev_max is not None and stddev_latency_ms > checkin.threshold_stddev_max)
                or (checkin.threshold_stddev_min is not None and stddev_latency_ms < checkin.threshold_stddev_min)
            )
            observed_value = stddev_latency_ms if stddev_breached else mean_latency_ms

            await db.alert_events.async_insert(
                id=str(uuid4()), tenant=tenant, rule_id=checkin_id, device_id=checkin.device_id,
                observed_value=observed_value, fired_at=now, notified=False,
            )
            try:
                from hub_api.notifications.service import NotificationService

                notifications = NotificationService(db)
                await notifications.notify(
                    tenant,
                    subject=f"AutoCheckIn breach: {checkin.name}",
                    body=(
                        f"AutoCheckIn '{checkin.name}' (tier {checkin.tier}) breached its "
                        f"threshold: mean={mean_latency_ms:.2f}ms stddev={stddev_latency_ms:.2f}ms "
                        f"target={checkin.target}"
                    ),
                )
            except Exception as e:
                logger.error(
                    "auto_checkin_notify_failed", checkin_id=checkin_id, tenant=tenant, error=str(e),
                )

        logger.info(
            "auto_checkin_cycle_completed", job_id=job_id, checkin_id=checkin_id, tenant=tenant,
            tier=checkin.tier, breached=breached, sample_count=len(latencies),
        )

        await _apply_jitter(db, job_id, base_interval_seconds, checkin.jitter_pct)

    except Exception as e:
        logger.error("auto_checkin_cycle_failed", job_id=job_id, tenant=tenant, error=str(e))


@celery_app.task(name="hub_api.modules.perftest_cluster.worker.tasks.auto_checkin_cycle")
def auto_checkin_cycle(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
) -> None:
    """Celery task to run an AutoCheckIn cycle (cascade-gated probes + jitter reschedule).

    Args:
        job_id: Job ID.
        tenant: Tenant identifier.
        module: Module name.
        job_type: Job type.
        payload: Job payload dict with checkin_id.
    """
    asyncio.run(
        _auto_checkin_cycle_async(
            job_id=job_id, tenant=tenant, module=module, job_type=job_type, payload=payload,
        )
    )
```

### Step 4: Run to verify it passes

`cd hub_api && source .venv/bin/activate && python3 -m pytest tests/perftest/test_auto_checkin_worker_tasks.py -v`
Expected: PASS (17 tests). Then rerun Task 0's baseline set to confirm no regression:
`python3 -m pytest tests/test_wpc_engine_client.py tests/test_autoperf_tier_types.py tests/perftest/test_wpc_worker_tasks.py tests/perftest/test_live_test_gaps.py tests/test_autoperf_manager.py -v`
Expected: PASS (91 tests, unchanged).

### Step 5: Commit

```bash
git add hub_api/modules/perftest_cluster/worker/tasks.py \
  hub_api/tests/perftest/test_auto_checkin_worker_tasks.py
git commit -m "feat(perftest_cluster): AutoCheckIn cycle -- jitter reschedule, tier cascade gate, std-dev breach"
```

---

## Task 3: AutoCheckIn REST API

**Files:**
- Create: `hub_api/modules/perftest_cluster/api/auto_checkins.py`
- Create: `hub_api/tests/test_auto_checkins_api.py`
- Modify: `hub_api/tests/perftest/conftest.py` (add `"hub_api.modules.perftest_cluster.api.auto_checkins"` to `api_modules_with_get_db`)

**Interfaces:**
- Consumes: `AutoCheckInManager` (Task 1), `_test_types_for_tier` (worker/tasks.py, already merged), `ALLOWED_TEST_TYPES` (engine_client.py, already merged), `current_claims`/`require_scope`/`require_tenant` (`hub_api.auth.middleware`), `require_feature` (`hub_api.entitlements.gate`), `get_db` (`hub_api.db`).
- Produces (consumed by Task 4's blueprint registration): `auto_checkins_bp = Blueprint("wpc_auto_checkins", __name__, url_prefix="/auto-checkins")` with routes `POST /`, `GET /`, `GET /<checkin_id>`, `GET /<checkin_id>/state`, `PATCH /<checkin_id>`, `DELETE /<checkin_id>`, all under `@require_feature("perftest.cluster", "auto_checkins")`.

### Step 1: Write the failing test

`hub_api/tests/test_auto_checkins_api.py`:

```python
"""Test AutoCheckIn REST API: flag/license gating, CRUD, tier validation."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB


@pytest_asyncio.fixture
async def auto_checkins_app(real_dal: AsyncDB, monkeypatch: pytest.MonkeyPatch):
    """Quart app with perftest_cluster mounted on a real DAL; flags off by default."""
    from hub_api.app import create_app
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext
    import hub_api.db
    import hub_api.app as app_module
    import shared.licensing.entitlements

    test_app = create_app()
    test_app.config["TESTING"] = True

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    test_app.config["KEY_PROVIDER"] = provider

    monkeypatch.setattr(hub_api.db, "get_db", lambda: real_dal)
    monkeypatch.setattr(app_module, "get_db", lambda: real_dal)
    import hub_api.modules.perftest_cluster.api.auto_checkins as auto_checkins_api

    monkeypatch.setattr(auto_checkins_api, "get_db", lambda: real_dal)

    enabled_flags: set[str] = set()

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        return flag_key in enabled_flags

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    from hub_api.modules.perftest_cluster import module as wpc_module

    test_app.registry.register(wpc_module())
    ctx = ModuleContext(config=test_app.config_obj, db=real_dal, key_provider=provider)
    test_app.registry.apply_to(test_app, ctx)

    test_app._test_enabled_flags = enabled_flags  # type: ignore[attr-defined]
    return test_app


async def _token(app) -> str:
    from hub_api.auth.jwt import encode_access_token

    return await encode_access_token(
        {
            "sub": "checkin-tester", "iss": "test-app", "aud": "test-app",
            "tenant": "tenant-checkin", "scope": "*:*",
        },
        app.config["KEY_PROVIDER"],
    )


@pytest.mark.asyncio
async def test_create_flag_off_returns_402(auto_checkins_app) -> None:
    """With the flag off, create must 402 before touching the DB."""
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={"name": "x", "device_id": str(uuid4()), "target_kind": "external", "target": "example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_create_unlicensed_402_professional(auto_checkins_app) -> None:
    """Entitlement-key trap: flag ON but license unset -> 402 professional."""
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={"name": "x", "device_id": str(uuid4()), "target_kind": "external", "target": "example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402
    body = await resp.get_json()
    assert body["tier"] == "professional"


@pytest.mark.asyncio
async def test_licensed_crud_roundtrip(auto_checkins_app, monkeypatch: pytest.MonkeyPatch) -> None:
    """Licensed Professional tier: create, list, get, patch, delete over HTTP."""
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "wifi-baseline", "device_id": str(uuid4()), "target_kind": "external",
            "target": "example.com", "interval_minutes": 5, "jitter_pct": 10, "samples_per_run": 2,
            "threshold_stddev_max": 50.0,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    created = await resp.get_json()
    assert created["name"] == "wifi-baseline"
    assert created["test_types"] == ["http_trace", "traceroute", "udp", "http2"]  # tier-1 default
    checkin_id = created["id"]

    resp = await client.get("/api/v1/perftest_cluster/auto-checkins", headers=headers)
    assert resp.status_code == 200
    listed = await resp.get_json()
    assert len(listed["checkins"]) == 1

    resp = await client.get(f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", headers=headers)
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}/state", headers=headers)
    assert resp.status_code == 200
    state = await resp.get_json()
    assert state["last_breached"] is False

    resp = await client.patch(
        f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}",
        json={"interval_minutes": 15},
        headers=headers,
    )
    assert resp.status_code == 200
    assert (await resp.get_json())["interval_minutes"] == 15

    resp = await client.delete(f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", headers=headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/perftest_cluster/auto-checkins/{checkin_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_missing_required_fields_400(auto_checkins_app, monkeypatch) -> None:
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={"name": "incomplete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_tier2_without_parent_400(auto_checkins_app, monkeypatch) -> None:
    """Manager ValueError (missing parent_checkin_id) surfaces as 400."""
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "orphan-tier2", "device_id": str(uuid4()), "target_kind": "external",
            "target": "example.com", "tier": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_with_dependents_409(auto_checkins_app, monkeypatch) -> None:
    auto_checkins_app._test_enabled_flags.add("tobogganing.perftest.cluster.auto_checkins")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _token(auto_checkins_app)
    client = auto_checkins_app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    device_id = str(uuid4())

    resp = await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={"name": "parent", "device_id": device_id, "target_kind": "external", "target": "example.com"},
        headers=headers,
    )
    parent_id = (await resp.get_json())["id"]

    await client.post(
        "/api/v1/perftest_cluster/auto-checkins",
        json={
            "name": "child", "device_id": device_id, "target_kind": "external",
            "target": "example.com", "tier": 2, "parent_checkin_id": parent_id,
            "test_types": ["throughput"],
        },
        headers=headers,
    )

    resp = await client.delete(f"/api/v1/perftest_cluster/auto-checkins/{parent_id}", headers=headers)
    assert resp.status_code == 409
```

### Step 2: Run to verify it fails

`cd hub_api && source .venv/bin/activate && python3 -m pytest tests/test_auto_checkins_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub_api.modules.perftest_cluster.api.auto_checkins'`.

### Step 3: Implementation

`hub_api/modules/perftest_cluster/api/auto_checkins.py`:

```python
"""AutoCheckIn configuration REST API (CRUD + tier cascade state)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_cluster.services.auto_checkin_manager import AutoCheckInManager
from hub_api.modules.perftest_cluster.services.engine_client import ALLOWED_TEST_TYPES
from hub_api.modules.perftest_cluster.worker.tasks import _test_types_for_tier

log = structlog.get_logger(__name__)

auto_checkins_bp = Blueprint("wpc_auto_checkins", __name__, url_prefix="/auto-checkins")

_REQUIRED_FIELDS = ("name", "device_id", "target_kind", "target")


def _meta() -> dict[str, Any]:
    """Standard response metadata block."""
    return {"version": 1, "timestamp": datetime.now(timezone.utc).isoformat()}


@auto_checkins_bp.route("", methods=["POST"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "auto_checkins")
async def create_auto_checkin() -> tuple[dict[str, Any], int]:
    """Create an AutoCheckIn.

    Required scope: tests:write
    Required feature: perftest_cluster.auto_checkins

    JSON body:
        name, device_id, target_kind ("ours"|"external"), target: required strings
        test_types: optional list[str] subset of ALLOWED_TEST_TYPES (defaults to
            the tier's standard set via _test_types_for_tier)
        interval_minutes: int 1-60 (default 5)
        jitter_pct: int 0-10 (default 0)
        samples_per_run: int 1-5 (default 1)
        threshold_stddev_min/threshold_stddev_max/threshold_mean: optional floats
        tier: int 1-3 (default 1)
        parent_checkin_id: required if tier > 1, forbidden if tier == 1
        enabled: bool (default true)

    Returns:
        JSON response with created check-in (201).
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()
        if not data:
            return {"error": "Request body is required"}, 400

        missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
        if missing:
            return {"error": f"Missing required fields: {', '.join(missing)}"}, 400

        for f in _REQUIRED_FIELDS:
            if not isinstance(data[f], str) or not data[f].strip():
                return {"error": f"{f} must be a non-empty string"}, 400

        tier = data.get("tier", 1)
        if not isinstance(tier, int):
            return {"error": "tier must be an integer"}, 400

        test_types = data.get("test_types") or _test_types_for_tier(tier)
        if not isinstance(test_types, list) or not all(isinstance(t, str) for t in test_types):
            return {"error": "test_types must be a list of strings"}, 400

        db = get_db()
        manager = AutoCheckInManager(db)

        checkin = await manager.create_checkin(
            tenant=tenant_id,
            name=data["name"].strip(),
            device_id=data["device_id"].strip(),
            target_kind=data["target_kind"].strip(),
            target=data["target"].strip(),
            test_types=test_types,
            interval_minutes=data.get("interval_minutes", 5),
            jitter_pct=data.get("jitter_pct", 0),
            samples_per_run=data.get("samples_per_run", 1),
            threshold_stddev_min=data.get("threshold_stddev_min"),
            threshold_stddev_max=data.get("threshold_stddev_max"),
            threshold_mean=data.get("threshold_mean"),
            tier=tier,
            parent_checkin_id=data.get("parent_checkin_id"),
            enabled=data.get("enabled", True),
        )

        log.info(
            "auto_checkin_created", checkin_id=checkin["id"], tenant=tenant_id,
            name=checkin["name"], tier=tier,
        )

        return {**checkin, "meta": _meta()}, 201

    except ValueError as e:
        log.warning("auto_checkin_validation_error", error=str(e))
        return {"error": str(e)}, 400
    except Exception as e:
        log.error("auto_checkin_creation_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("perftest.cluster", "auto_checkins")
async def list_auto_checkins() -> tuple[dict[str, Any], int]:
    """List AutoCheckIns for the tenant.

    Required scope: tests:read
    Required feature: perftest_cluster.auto_checkins

    Returns:
        JSON response with checkins list (200).
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)
        checkins = await manager.list_checkins(tenant_id)

        return {"checkins": checkins, "meta": _meta()}, 200

    except Exception as e:
        log.error("auto_checkin_list_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("perftest.cluster", "auto_checkins")
async def get_auto_checkin(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Get a single AutoCheckIn.

    Required scope: tests:read
    Required feature: perftest_cluster.auto_checkins

    Returns:
        JSON response with check-in (200) or 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)
        checkin = await manager.get_checkin(tenant_id, checkin_id)

        if not checkin:
            return {"error": "Check-in not found"}, 404

        return {**checkin, "meta": _meta()}, 200

    except Exception as e:
        log.error("auto_checkin_get_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>/state", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("perftest.cluster", "auto_checkins")
async def get_auto_checkin_state(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Get cascade state (last_breached, last mean/stddev, last_run_at) for a check-in.

    Required scope: tests:read
    Required feature: perftest_cluster.auto_checkins

    Returns:
        JSON response with state (200) or 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)
        state = await manager.get_state(tenant_id, checkin_id)

        if not state:
            return {"error": "State not found"}, 404

        return state, 200

    except Exception as e:
        log.error("auto_checkin_state_get_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>", methods=["PATCH"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "auto_checkins")
async def update_auto_checkin(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Update mutable AutoCheckIn fields.

    Required scope: tests:write
    Required feature: perftest_cluster.auto_checkins

    JSON body (all optional): name, target, test_types, interval_minutes,
        jitter_pct, samples_per_run, threshold_stddev_min, threshold_stddev_max,
        threshold_mean, enabled. Structural fields (device_id, target_kind,
        tier, parent_checkin_id) are immutable -- create a new check-in instead.

    Returns:
        JSON response with updated check-in (200) or 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()
        if not data:
            return {"error": "Request body is required"}, 400

        if "test_types" in data:
            tt = data["test_types"]
            if not isinstance(tt, list) or not all(isinstance(t, str) for t in tt):
                return {"error": "test_types must be a list of strings"}, 400
            unsupported = set(tt) - ALLOWED_TEST_TYPES
            if unsupported:
                return {"error": f"Unsupported test_types: {sorted(unsupported)}"}, 400

        db = get_db()
        manager = AutoCheckInManager(db)

        existing = await manager.get_checkin(tenant_id, checkin_id)
        if not existing:
            return {"error": "Check-in not found"}, 404

        updated = await manager.update_checkin(tenant_id, checkin_id, **data)
        if not updated:
            return {"error": "Check-in not found"}, 404

        log.info("auto_checkin_updated", checkin_id=checkin_id, tenant=tenant_id)

        return {**updated, "meta": _meta()}, 200

    except ValueError as e:
        log.warning("auto_checkin_update_validation_error", checkin_id=checkin_id, error=str(e))
        return {"error": str(e)}, 400
    except Exception as e:
        log.error("auto_checkin_update_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>", methods=["DELETE"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "auto_checkins")
async def delete_auto_checkin(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Delete an AutoCheckIn (must have no tier-dependent children).

    Required scope: tests:write
    Required feature: perftest_cluster.auto_checkins

    Returns:
        Empty response (204), 404 if not found, or 409 if it has dependents.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)

        deleted = await manager.delete_checkin(tenant_id, checkin_id)
        if not deleted:
            return {"error": "Check-in not found"}, 404

        log.info("auto_checkin_deleted", checkin_id=checkin_id, tenant=tenant_id)

        return {}, 204

    except ValueError as e:
        log.warning("auto_checkin_delete_conflict", checkin_id=checkin_id, error=str(e))
        return {"error": str(e)}, 409
    except Exception as e:
        log.error("auto_checkin_delete_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500
```

Also add `"hub_api.modules.perftest_cluster.api.auto_checkins"` to the `api_modules_with_get_db` list in `hub_api/tests/perftest/conftest.py` (after `"hub_api.modules.perftest_cluster.api.autoperf"`), so the shared `app_all_perftest_realdal` fixture (used by future W3+ tests that mount the whole module) patches `get_db` in this new file too.

### Step 4: Run to verify it passes

`cd hub_api && source .venv/bin/activate && python3 -m pytest tests/test_auto_checkins_api.py -v`
Expected: FAIL still — the blueprint isn't registered in `api/__init__.py`/`blueprints` yet, so routes 404 rather than gate. This is expected; Task 4 wires registration. Do not consider Task 3 complete until Task 4's registration step, then rerun this file to confirm PASS (7 tests).

### Step 5: Commit

Commit together with Task 4 (module wiring) since the blueprint isn't reachable without registration — see Task 4 Step 4.

---

## Task 4: Module wiring (blueprint registration, nav, flag, entitlement, job handler)

**Files:**
- Modify: `hub_api/modules/perftest_cluster/api/__init__.py`
- Modify: `hub_api/modules/perftest_cluster/__init__.py`

**Interfaces:**
- Consumes: `auto_checkins_bp` (Task 3), `register_job_handler` (`hub_api.scheduler.registry`, already exists), `Entitlement`/`NavEntry`/`ModuleContract` (`hub_api.registry`, already exists).
- Produces: flag key `tobogganing.perftest.cluster.auto_checkins`; entitlement key `perftest.cluster.auto_checkins` at `"professional"`; job handler `("perftest_cluster", "auto_checkin") -> "hub_api.modules.perftest_cluster.worker.tasks.auto_checkin_cycle"`.

### Step 1: `api/__init__.py`

```python
"""WaddlePerf cluster API blueprints."""
from __future__ import annotations

from hub_api.modules.perftest_cluster.api.alerts import alerts_bp as alerts_blueprint
from hub_api.modules.perftest_cluster.api.auto_checkins import (
    auto_checkins_bp as auto_checkins_blueprint,
)
from hub_api.modules.perftest_cluster.api.autoperf import autoperf_bp as autoperf_blueprint
from hub_api.modules.perftest_cluster.api.devices import blueprint as devices_blueprint
from hub_api.modules.perftest_cluster.api.enrollment import blueprint as enrollment_blueprint
from hub_api.modules.perftest_cluster.api.live_test import blueprint as live_test_blueprint
from hub_api.modules.perftest_cluster.api.org_units import blueprint as org_units_blueprint
from hub_api.modules.perftest_cluster.api.scheduled_tests import (
    blueprint as scheduled_tests_blueprint,
)
from hub_api.modules.perftest_cluster.api.stats import blueprint as stats_blueprint
from hub_api.modules.perftest_cluster.api.tests import blueprint as tests_blueprint

blueprints = [
    org_units_blueprint,
    devices_blueprint,
    enrollment_blueprint,
    tests_blueprint,
    scheduled_tests_blueprint,
    stats_blueprint,
    live_test_blueprint,
    alerts_blueprint,
    autoperf_blueprint,
    auto_checkins_blueprint,
]

__all__ = ["blueprints"]
```

### Step 2: `__init__.py` (module contract)

Add to `nav` (after the `AutoPerf` entry): `NavEntry("Auto Check-ins", "/api/v1/perftest_cluster/auto-checkins", "check-circle"),`
Add to `flags`: `"tobogganing.perftest.cluster.auto_checkins",`
Add to `entitlements`: `Entitlement("perftest.cluster.auto_checkins", "professional"),`
Add `"0027"` to `migrations=["0010", "0011", "0012", "0027"]` (kept as-is otherwise; this list is documentation-only per the existing pattern — earlier migrations 0016-0019 that this module also depends on were never added either, so `"0027"` here follows the established convention of listing only the newest).
Add job handler registration (after the `autoperf_cycle` registration):

```python
    # Register handler for AutoCheckIn cycle
    register_job_handler(
        "perftest_cluster",
        "auto_checkin",
        "hub_api.modules.perftest_cluster.worker.tasks.auto_checkin_cycle",
    )
```

### Step 3: Run full perftest suite + regenerate OpenAPI

```bash
cd hub_api && source .venv/bin/activate
python3 -m pytest tests/test_auto_checkins_api.py tests/test_auto_checkin_manager.py \
  tests/perftest/test_auto_checkin_worker_tasks.py -v
# Expected: all PASS now that the blueprint is registered (7 + 7 + 17 = 31 tests)

python3 -m pytest tests/ -v
# Expected: full suite green, no regressions

cd .. && make openapi && make openapi-lint
# Expected: openapi/v1.yaml regenerated with the six new /auto-checkins routes; spectral clean
```

### Step 4: Commit (Tasks 3 + 4 together — the blueprint isn't reachable without registration)

```bash
git add hub_api/modules/perftest_cluster/api/auto_checkins.py \
  hub_api/tests/test_auto_checkins_api.py hub_api/tests/perftest/conftest.py \
  hub_api/modules/perftest_cluster/api/__init__.py hub_api/modules/perftest_cluster/__init__.py \
  openapi/v1.yaml
git commit -m "feat(perftest_cluster): AutoCheckIn REST API + module wiring (flag, entitlement, job handler)"
```

---

## Task 5: Portal Admin UI

**Files:**
- Modify: `portal/src/api/wpcOps.ts`
- Create: `portal/src/pages/waddleperf/AutoCheckInsPage.tsx`
- Create: `portal/src/pages/waddleperf/AutoCheckInsPage.test.tsx`
- Modify: `portal/src/routes/wpcViews.ts`

**Interfaces:**
- Consumes: `apiClient` (`portal/src/api/client.ts`), `DataTable`/`ColumnConfig` (`portal/src/components/DataTable.tsx`), `useRole` (`portal/src/hooks/useRole.ts`).
- Produces: `wpcOps.AutoCheckIn`, `wpcOps.AutoCheckInState` types; `listAutoCheckIns()`, `createAutoCheckIn(payload)`, `updateAutoCheckIn(id, payload)`, `deleteAutoCheckIn(id)`, `getAutoCheckInState(id)`; view slug `"auto-checkins"` resolving to `AutoCheckInsPage` via `resolveView("perftest_cluster", "auto-checkins")`.

### Step 1: Write the failing test

`portal/src/pages/waddleperf/AutoCheckInsPage.test.tsx`:

```typescript
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AutoCheckInsPage } from './AutoCheckInsPage';
import * as wpcOps from '../../api/wpcOps';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mockCheckins: wpcOps.AutoCheckIn[] = [
  {
    id: 'checkin-1',
    tenant: 'tenant-1',
    name: 'Wifi Baseline',
    device_id: 'dev-1',
    target_kind: 'external',
    target: 'example.com',
    test_types: ['http_trace', 'traceroute', 'udp', 'http2'],
    interval_minutes: 5,
    jitter_pct: 10,
    samples_per_run: 2,
    threshold_stddev_min: null,
    threshold_stddev_max: 50,
    threshold_mean: null,
    tier: 1,
    parent_checkin_id: null,
    enabled: true,
    created_at: '2026-08-28T00:00:00Z',
    updated_at: '2026-08-28T00:00:00Z',
  },
];

const mockState: wpcOps.AutoCheckInState = {
  checkin_id: 'checkin-1',
  last_breached: false,
  last_mean_latency_ms: 12.5,
  last_stddev_latency_ms: 1.2,
  last_run_at: '2026-08-28T00:05:00Z',
  updated_at: '2026-08-28T00:05:00Z',
};

describe('AutoCheckInsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listAutoCheckIns as jest.Mock).mockResolvedValue(mockCheckins);
    (wpcOps.getAutoCheckInState as jest.Mock).mockResolvedValue(mockState);
    mockUseRole.mockReturnValue({ role: 'admin', canWrite: () => true });
  });

  it('renders the page title', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    expect(await screen.findByText('Auto Check-ins')).toBeInTheDocument();
  });

  it('lists check-ins with their tier badge', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    expect(await screen.findByText('Wifi Baseline')).toBeInTheDocument();
    expect(screen.getByText('T1')).toBeInTheDocument();
  });

  it('creates a check-in via the form', async () => {
    (wpcOps.createAutoCheckIn as jest.Mock).mockResolvedValue({
      ...mockCheckins[0],
      id: 'checkin-2',
      name: 'New Checkin',
    });
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByText('Create Check-in'));
    await userEvent.type(screen.getByPlaceholderText('Check-in name'), 'New Checkin');
    await userEvent.type(screen.getByPlaceholderText('Source device ID'), 'dev-2');
    await userEvent.type(screen.getByPlaceholderText('Target (URL/host:port)'), 'test.example.com');
    await userEvent.click(screen.getByText('Create'));

    await waitFor(() => expect(wpcOps.createAutoCheckIn).toHaveBeenCalled());
  });

  it('deletes a check-in', async () => {
    (wpcOps.deleteAutoCheckIn as jest.Mock).mockResolvedValue(undefined);
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByText('Delete'));
    await waitFor(() =>
      expect(wpcOps.deleteAutoCheckIn).toHaveBeenCalledWith('checkin-1')
    );
  });

  it('shows cascade state when expanded', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByText('State'));
    expect(await screen.findByText(/Last Breached/)).toBeInTheDocument();
  });

  it('hides create/delete controls for read-only role', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await screen.findByText('Wifi Baseline');
    expect(screen.queryByText('Create Check-in')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
  });
});
```

### Step 2: Run to verify it fails

`cd portal && npx jest AutoCheckInsPage --no-coverage`
Expected: FAIL — `Cannot find module './AutoCheckInsPage'`.

### Step 3: Implementation

Add to `portal/src/api/wpcOps.ts` (after the `AutoPerfState` interface / before the `/** API Functions - Alerts */` comment):

```typescript
/** AutoCheckIn */
export interface AutoCheckIn {
  id: string;
  tenant: string;
  name: string;
  device_id: string;
  target_kind: 'ours' | 'external';
  target: string;
  test_types: string[];
  interval_minutes: number;
  jitter_pct: number;
  samples_per_run: number;
  threshold_stddev_min: number | null;
  threshold_stddev_max: number | null;
  threshold_mean: number | null;
  tier: number;
  parent_checkin_id: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutoCheckInState {
  checkin_id: string;
  last_breached: boolean;
  last_mean_latency_ms: number | null;
  last_stddev_latency_ms: number | null;
  last_run_at: string | null;
  updated_at: string;
}
```

Add to the end of the file:

```typescript
/** API Functions - AutoCheckIn */
export async function listAutoCheckIns(): Promise<AutoCheckIn[]> {
  console.log('[wpcOps] listAutoCheckIns');
  const response = await apiClient.get<{ checkins: AutoCheckIn[] }>(
    '/perftest_cluster/auto-checkins'
  );
  return response.data.checkins;
}

export async function createAutoCheckIn(payload: {
  name: string;
  device_id: string;
  target_kind: 'ours' | 'external';
  target: string;
  test_types?: string[];
  interval_minutes?: number;
  jitter_pct?: number;
  samples_per_run?: number;
  threshold_stddev_min?: number;
  threshold_stddev_max?: number;
  threshold_mean?: number;
  tier?: number;
  parent_checkin_id?: string;
  enabled?: boolean;
}): Promise<AutoCheckIn> {
  console.log('[wpcOps] createAutoCheckIn { name:', payload.name, '}');
  const response = await apiClient.post<AutoCheckIn>('/perftest_cluster/auto-checkins', payload);
  return response.data;
}

export async function updateAutoCheckIn(
  checkinId: string,
  payload: Partial<
    Pick<
      AutoCheckIn,
      | 'name'
      | 'target'
      | 'test_types'
      | 'interval_minutes'
      | 'jitter_pct'
      | 'samples_per_run'
      | 'threshold_stddev_min'
      | 'threshold_stddev_max'
      | 'threshold_mean'
      | 'enabled'
    >
  >
): Promise<AutoCheckIn> {
  console.log('[wpcOps] updateAutoCheckIn { checkin_id:', checkinId.slice(0, 8), '}');
  const response = await apiClient.patch<AutoCheckIn>(
    `/perftest_cluster/auto-checkins/${checkinId}`,
    payload
  );
  return response.data;
}

export async function deleteAutoCheckIn(checkinId: string): Promise<void> {
  console.log('[wpcOps] deleteAutoCheckIn { checkin_id:', checkinId.slice(0, 8), '}');
  await apiClient.delete(`/perftest_cluster/auto-checkins/${checkinId}`);
}

export async function getAutoCheckInState(checkinId: string): Promise<AutoCheckInState> {
  console.log('[wpcOps] getAutoCheckInState { checkin_id:', checkinId.slice(0, 8), '}');
  const response = await apiClient.get<AutoCheckInState>(
    `/perftest_cluster/auto-checkins/${checkinId}/state`
  );
  return response.data;
}
```

`portal/src/pages/waddleperf/AutoCheckInsPage.tsx`:

```typescript
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import {
  AutoCheckIn,
  listAutoCheckIns,
  createAutoCheckIn,
  deleteAutoCheckIn,
  getAutoCheckInState,
} from '../../api/wpcOps';

function TierBadge({ tier }: { tier: number }) {
  const colors: Record<number, string> = {
    1: 'bg-blue-900 text-blue-200',
    2: 'bg-yellow-900 text-yellow-200',
    3: 'bg-red-900 text-red-200',
  };
  return (
    <span className={`px-2 py-1 rounded text-sm ${colors[tier] || 'bg-slate-700 text-slate-300'}`}>
      T{tier}
    </span>
  );
}

function CheckinStatePanel({ checkinId }: { checkinId: string }) {
  const { data: state, isLoading } = useQuery({
    queryKey: ['auto-checkins', checkinId, 'state'],
    queryFn: () => getAutoCheckInState(checkinId),
    staleTime: 60 * 1000,
  });

  if (isLoading) return <div className="text-slate-400 text-sm">Loading state...</div>;
  if (!state) return <div className="text-slate-400 text-sm">No state available</div>;

  return (
    <div className="bg-slate-800 rounded p-3 space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-slate-400">Last Breached:</span>
        <span className={state.last_breached ? 'text-red-400' : 'text-green-400'}>
          {state.last_breached ? 'Yes' : 'No'}
        </span>
      </div>
      {state.last_mean_latency_ms !== null && (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Mean Latency:</span>
          <span className="text-amber-300">{state.last_mean_latency_ms.toFixed(2)} ms</span>
        </div>
      )}
      {state.last_stddev_latency_ms !== null && (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Std Dev:</span>
          <span className="text-amber-300">{state.last_stddev_latency_ms.toFixed(2)} ms</span>
        </div>
      )}
      {state.last_run_at && (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Last Run:</span>
          <span className="text-slate-300">{new Date(state.last_run_at).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}

export function AutoCheckInsPage() {
  const { canWrite } = useRole();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [expandedCheckin, setExpandedCheckin] = useState<string | null>(null);

  const {
    data: checkins = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['auto-checkins'],
    queryFn: listAutoCheckIns,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createAutoCheckIn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-checkins'] });
      setShowForm(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAutoCheckIn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-checkins'] });
    },
  });

  const baseColumns: ColumnConfig<AutoCheckIn>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'device_id', label: 'Source Device', sortable: true },
    { key: 'target', label: 'Target', sortable: true },
    {
      key: 'tier' as keyof AutoCheckIn,
      label: 'Tier',
      render: (tier) => <TierBadge tier={tier as number} />,
    },
    {
      key: 'enabled',
      label: 'Status',
      render: (enabled) => (
        <span className={enabled ? 'text-green-400' : 'text-slate-400'}>
          {enabled ? 'Active' : 'Inactive'}
        </span>
      ),
    },
  ];

  const columns: ColumnConfig<AutoCheckIn>[] = canWrite()
    ? [
        ...baseColumns,
        {
          key: 'id' as keyof AutoCheckIn,
          label: 'Actions',
          render: (id) => (
            <div className="flex gap-2">
              <button
                onClick={() =>
                  setExpandedCheckin(expandedCheckin === (id as string) ? null : (id as string))
                }
                className="px-2 py-1 bg-sky-900 hover:bg-sky-800 text-sky-200 rounded text-sm"
              >
                {expandedCheckin === id ? 'Hide' : 'State'}
              </button>
              <button
                onClick={() => deleteMutation.mutate(id as string)}
                disabled={deleteMutation.isPending}
                className="px-2 py-1 bg-red-900 hover:bg-red-800 disabled:opacity-50 text-red-200 rounded text-sm"
              >
                Delete
              </button>
            </div>
          ),
        },
      ]
    : [
        ...baseColumns,
        {
          key: 'id' as keyof AutoCheckIn,
          label: 'State',
          render: (id) => (
            <button
              onClick={() =>
                setExpandedCheckin(expandedCheckin === (id as string) ? null : (id as string))
              }
              className="px-2 py-1 bg-sky-900 hover:bg-sky-800 text-sky-200 rounded text-sm"
            >
              {expandedCheckin === id ? 'Hide' : 'State'}
            </button>
          ),
        },
      ];

  console.log('[AutoCheckInsPage] Render { checkins:', checkins.length, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">Auto Check-ins</h1>
        <p className="text-slate-400 text-sm mt-1">
          Configure tiered, jittered, std-dev-thresholded probe check-ins
        </p>
      </div>

      {canWrite() && (
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded"
        >
          {showForm ? 'Cancel' : 'Create Check-in'}
        </button>
      )}

      {showForm && canWrite() && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            const thresholdMax = formData.get('threshold_stddev_max') as string;
            createMutation.mutate({
              name: formData.get('name') as string,
              device_id: formData.get('device_id') as string,
              target_kind: formData.get('target_kind') as 'ours' | 'external',
              target: formData.get('target') as string,
              interval_minutes: parseInt(formData.get('interval_minutes') as string, 10),
              jitter_pct: parseInt(formData.get('jitter_pct') as string, 10),
              samples_per_run: parseInt(formData.get('samples_per_run') as string, 10),
              tier: parseInt(formData.get('tier') as string, 10),
              threshold_stddev_max: thresholdMax ? parseFloat(thresholdMax) : undefined,
            });
          }}
          className="bg-slate-800 p-4 rounded space-y-3"
        >
          <input
            name="name"
            placeholder="Check-in name"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="device_id"
            placeholder="Source device ID"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <select
            name="target_kind"
            defaultValue="external"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          >
            <option value="ours">Ours (internal service)</option>
            <option value="external">External (URL/host:port)</option>
          </select>
          <input
            name="target"
            placeholder="Target (URL/host:port)"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="interval_minutes"
            type="number"
            placeholder="Interval (minutes, 1-60, default 5)"
            defaultValue="5"
            min="1"
            max="60"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="jitter_pct"
            type="number"
            placeholder="Jitter (%, 0-10, default 0)"
            defaultValue="0"
            min="0"
            max="10"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="samples_per_run"
            type="number"
            placeholder="Samples per run (1-5, default 1)"
            defaultValue="1"
            min="1"
            max="5"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="threshold_stddev_max"
            type="number"
            step="0.1"
            placeholder="Max acceptable std-dev (ms, optional)"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <select
            name="tier"
            defaultValue="1"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          >
            <option value="1">Tier 1 (always runs)</option>
            <option value="2">Tier 2 (runs when its Tier-1 parent breaches)</option>
            <option value="3">Tier 3 (runs when its Tier-2 parent breaches)</option>
          </select>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded"
          >
            Create
          </button>
        </form>
      )}

      <DataTable
        columns={columns}
        data={checkins}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />

      {expandedCheckin && (
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <h3 className="text-amber-400 font-semibold mb-3">
            State for {checkins.find((c) => c.id === expandedCheckin)?.name}
          </h3>
          <CheckinStatePanel checkinId={expandedCheckin} />
        </div>
      )}
    </div>
  );
}
```

Add to `portal/src/routes/wpcViews.ts`:

```typescript
import type { ComponentType } from 'react';
import { DevicesPage } from '../pages/waddleperf/DevicesPage';
import { TestsPage } from '../pages/waddleperf/TestsPage';
import { StatsPage } from '../pages/waddleperf/StatsPage';
import { AlertsPage } from '../pages/waddleperf/AlertsPage';
import { ScheduledTestsPage } from '../pages/waddleperf/ScheduledTestsPage';
import { AutoPerfPage } from '../pages/waddleperf/AutoPerfPage';
import { AutoCheckInsPage } from '../pages/waddleperf/AutoCheckInsPage';
import { LiveTestPage } from '../pages/waddleperf/LiveTestPage';

/** View-slug -> page map for the perftest_cluster module. */
export const wpcViews: Record<string, ComponentType> = {
  devices: DevicesPage,
  tests: TestsPage,
  stats: StatsPage,
  alerts: AlertsPage,
  'scheduled-tests': ScheduledTestsPage,
  autoperf: AutoPerfPage,
  'auto-checkins': AutoCheckInsPage,
  'live-test': LiveTestPage,
};
```

(`viewRegistry.ts` needs no change — it already resolves through the `wpcViews` map generically.)

### Step 4: Run to verify it passes

```bash
cd portal
npx jest AutoCheckInsPage --no-coverage
# Expected: PASS (6 tests)
npm test
# Expected: full suite green, coverageThreshold (90%) still met
```

### Step 5: Commit

```bash
git add portal/src/api/wpcOps.ts portal/src/pages/waddleperf/AutoCheckInsPage.tsx \
  portal/src/pages/waddleperf/AutoCheckInsPage.test.tsx portal/src/routes/wpcViews.ts
git commit -m "feat(portal): Auto Check-ins admin page (tier cascade CRUD + cascade state view)"
```

---

## Task 6: Final verification, docs, and PR

- Full backend suite with coverage: `cd hub_api && source .venv/bin/activate && python3 -m pytest ../hub_api/tests/ --cov=hub_api --cov-report=term-missing --cov-fail-under=90` (run from repo root per the `make test-cov` Makefile target, or `cd` to repo root first) — must show a real "N passed" count and ≥90% total coverage; report the number, not "clean."
- Portal: `cd portal && npm test` — must show a real pass count and the configured `coverageThreshold` met.
- Security scans on touched files: `bandit -r hub_api/modules/perftest_cluster/services/auto_checkin_manager.py hub_api/modules/perftest_cluster/worker/tasks.py hub_api/modules/perftest_cluster/api/auto_checkins.py -ll`; `ruff check hub_api/modules/perftest_cluster/ hub_api/tests/test_auto_checkin_manager.py hub_api/tests/test_auto_checkins_api.py hub_api/tests/perftest/test_auto_checkin_worker_tasks.py`; `pip-audit` (or the repo's `make test-security` target if present).
- `make openapi-lint` (spectral) must already be clean from Task 4 — re-run to confirm no drift from Task 5/6 edits (none expected; portal changes don't touch the spec).
- Update `docs/superpowers/specs/2026-08-21-perftest-probe-suite-design.md`'s Phases table: mark **W2 — Check-in model** deliverable status if the spec doc tracks completion elsewhere (check current convention before editing; do not invent a status column that doesn't exist).
- `git push -u origin feature/perftest-w2-checkins` (branch backup — standing pre-authorization per `devops.md` Branch Backups; does NOT open a PR).
- Do not open a PR or merge — user reviews first per the task's explicit instruction.

## Self-Review Notes

- **Spec coverage:** tenant scoping ✔ (Task 1 manager, Task 3 API via `current_claims()["tenant"]`); source_client/target_kind/target ✔ (Task 1 schema); test_types multi-select ✔ (JSON column + `_test_types_for_tier` default); interval 1-60 + jitter ±10% ✔ (Task 1 bounds + Task 2 `_jittered_interval_seconds`); samples 1-5 ✔ (Task 1 bounds + Task 2 `_run_auto_checkin_samples`); std-dev min/max/mean thresholds ✔ (Task 2 `_evaluate_threshold_breach`, semantics resolved in "Resolved ambiguities" #3); tier 1/2/3 cascade ✔ (Task 1 `parent_checkin_id` validation + Task 2 cascade gate); results feed alerting ✔ (Task 2 `alert_events` insert + `NotificationService.notify`); admin UI ✔ (Task 5); no new scheduler ✔ (Task 1/2 compile down to `scheduled_jobs` + existing sweep); reuse of already-merged `_test_types_for_tier`/`ThroughputBackend` ✔ (Task 2/3, explicitly not reinvented).
- **Placeholder scan:** no "TBD"/"add validation"/"handle edge cases" — every validation branch has its exact condition and error message; every test has real assertions.
- **Type consistency:** `AutoCheckInManager` row-dict shape (Task 1) is the exact shape read by `_auto_checkin_cycle_async` (Task 2, direct `db(...)` row access matching field names) and returned/spread by the API (Task 3) and consumed by `wpcOps.AutoCheckIn` (Task 5) — checked field-by-field across all four.
- **Baseline protection:** `_execute_and_store_test`'s bool-only return contract is explicitly left untouched (Task 2 implementation note) — the new `_execute_auto_checkin_sample` is a parallel, not a replacement, so `run_server_test`/`autoperf_cycle`/their existing tests are unaffected. Task 2 Step 4 reruns the Task 0 baseline set to confirm.
