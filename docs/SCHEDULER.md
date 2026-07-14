# Core Scheduler & Notifications

Server-side recurring jobs (`core/scheduler`) and per-tenant notification delivery (`core/notifications`) — the infrastructure behind server-initiated recurring tests, recurring c2c matrix runs, and threshold alerting.

## Architecture

- **`scheduled_jobs` table** (migration 0016): tenant-scoped dynamic schedules — `(module, job_type, payload, interval_seconds, next_run_at)`.
- **Sweep**: a Celery-beat static entry fires `core.scheduler.tasks.sweep` every `SCHEDULER_SWEEP_SECONDS` (default 30s). The sweep queries due rows and dispatches each to the Celery task registered for its `(module, job_type)`, then advances `next_run_at` by `interval_seconds` — unconditionally, so an unknown handler or failing dispatch never wedges the sweep.
- **Handler registry**: modules call `core.scheduler.registry.register_job_handler(module, job_type, task_name)` when their contract is built. The scheduler itself is ungated infrastructure; each *consumer* is gated by its own flag + entitlement.

## Running

```bash
# Worker (executes dispatched jobs) and beat (fires the sweep)
celery -A core.scheduler.celery_app worker --loglevel=info
celery -A core.scheduler.celery_app beat --loglevel=info
```

Broker/backend come from `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (Valkey). The module imports safely without Celery installed; enqueueing without a broker raises at call time.

## Consumers, flags, and tiers

| Feature | Module | Flag (PostHog) | Entitlement (bare key) | Tier |
|---|---|---|---|---|
| Server-initiated recurring tests | `waddleperf_cluster` | `tobogganing.waddleperf_cluster.scheduled_tests` | `waddleperf_cluster.scheduled_tests` | Community |
| Recurring matrix runs | `waddleperf_c2c` | `tobogganing.waddleperf_c2c.recurring_runs` | `waddleperf_c2c.recurring_runs` | Professional |
| Threshold alerts (rules, events, email channels) | `waddleperf_cluster` | `tobogganing.waddleperf_cluster.alerts` | `waddleperf_cluster.alerts` | Community |
| Webhook alert routing | `waddleperf_cluster` | `tobogganing.waddleperf_cluster.alert_routing` | `waddleperf_cluster.alert_routing` | Professional |

All flags default OFF. Note the entitlement keys are **bare** (`{module}.{feature}`, no `tobogganing.` prefix) — a prefixed entitlement key silently degrades the paid gate to Community.

## Job handler contract

A handler is a Celery task on `core.scheduler.celery_app` with the signature:

```python
def my_handler(job_id: str, tenant: str, module: str, job_type: str, payload: dict) -> None: ...
```

Handlers build a fresh `AsyncDB` per invocation (`asyncio.run` around an inner async function) and must never raise — log and record failure state instead.

## Notifications (`core/notifications`)

- **Channels** (migration 0017): per-tenant, `kind=email` (`{"to": [...]}` via SMTP env) or `kind=webhook` (`{"url": "https://...", "secret": ...}`).
- **Webhook signing**: POST body is JSON `{subject, body, timestamp}`; header `X-Tobogganing-Signature: sha256=<HMAC-SHA256(secret, raw_body)>`. https URLs only.
- **Delivery log**: one `notification_deliveries` row per attempt (`sent`/`failed` + error). `notify()` never raises transport errors and silently skips channel ids that belong to another tenant (fail-closed).
- Secrets are redacted (`****` + last 4) in every channel read API; SMTP credentials come from `SMTP_*` env vars.

## Alerting (`waddleperf_cluster`)

- **Rules** (migration 0018): `metric` + `comparator` (`gt|gte|lt|lte`) + `threshold`, optional `device_id`/`test_type` filters, `window_seconds` dedup, optional `channel_id` (default: all enabled channels).
- **Evaluation** runs in two places: inline on result ingest (flag-gated, wrapped so evaluator failures never fail the ingest response) and via the `alert_sweep` scheduler job.
- Breaches insert `alert_events` and deliver through `core/notifications`.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Valkey broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Result backend |
| `SCHEDULER_SWEEP_SECONDS` | `30` | Beat sweep interval |
| `SMTP_HOST/PORT/USER/PASS/FROM` | — | Email channel delivery |
