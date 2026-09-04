"""Celery application for scheduler sweep tasks.

Provides a Celery instance safe to import without a live broker.
Implements beat schedule for recurring sweep execution.
"""
from __future__ import annotations

import os
from typing import Any

# Guard Celery import; if not available, provide a minimal stand-in
try:
    from celery import Celery
except ImportError:
    # Celery not installed; provide a stub so imports don't fail

    class _StubConfig:
        """Stub for Celery.conf."""

        def update(self, **kwargs: Any) -> None:
            """Stub update method."""
            pass

    class _CeleryStub:
        """Stand-in for Celery when package is missing."""

        def __init__(self, app_name: str, **kwargs: Any) -> None:
            """Initialize stub."""
            self.app_name = app_name
            self.conf = _StubConfig()

        def task(
            self, *args: Any, **kwargs: Any
        ) -> Any:
            """Provide stub task decorator."""

            def decorator(func: Any) -> Any:
                """Return a wrapped function with .delay() that raises."""

                def wrapper(*a: Any, **kw: Any) -> Any:
                    """Call original function."""
                    return func(*a, **kw)

                def delay_stub(*a: Any, **kw: Any) -> None:
                    """Raise when .delay() is called without Celery."""
                    raise RuntimeError(
                        "Celery task enqueue attempted, but Celery is not installed. "
                        "Install with: pip install celery"
                    )

                wrapper.delay = delay_stub  # type: ignore[attr-defined]
                wrapper.apply_async = delay_stub  # type: ignore[attr-defined]
                return wrapper

            return decorator

    Celery = _CeleryStub


# Create Celery instance
# Broker and result backend from environment; Valkey (redis-compatible) by default
broker_url = os.environ.get(
    "CELERY_BROKER_URL", "redis://localhost:6379/0"
)
result_backend = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
)

celery_app = Celery(
    "tobogganing_scheduler",
    broker=broker_url,
    backend=result_backend,
)

# Configure Celery with sensible defaults
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_queue="tobogganing_scheduler",
    task_track_started=True,
    result_expires=3600,  # 1 hour expiry
    beat_schedule={
        "scheduler-sweep": {
            "task": "hub_api.scheduler.tasks.sweep",
            "schedule": float(os.getenv("SCHEDULER_SWEEP_SECONDS", "30")),
        },
    },
)

__all__ = ["celery_app"]
