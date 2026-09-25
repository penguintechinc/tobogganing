"""Tests for hub_api.scheduler.celery_app, including the no-Celery stub fallback.

Celery is installed in this environment, so `_CeleryStub` is normally dead
code; this file forces the ImportError branch via sys.modules injection and
a module reload to exercise the fallback stand-in directly.
"""

from __future__ import annotations

import importlib
import sys

import pytest

import hub_api.scheduler.celery_app as celery_app_module


def test_real_celery_app_configured() -> None:
    """The module-level celery_app is a real Celery instance with our config."""
    from celery import Celery

    assert isinstance(celery_app_module.celery_app, Celery)
    assert "scheduler-sweep" in celery_app_module.celery_app.conf.beat_schedule


def test_module_exports_celery_app() -> None:
    """__all__ exposes celery_app."""
    assert celery_app_module.__all__ == ["celery_app"]


class TestCeleryStubFallback:
    """Exercises the `_CeleryStub` fallback used when celery isn't installed."""

    def test_stub_used_when_celery_unimportable(self) -> None:
        """Reloading the module with celery hidden constructs the stub instead.

        Restoration must happen only after sys.modules["celery"] is put back
        (mp.undo()), otherwise the restoring reload() would re-hit the stub.
        """
        mp = pytest.MonkeyPatch()
        mp.setitem(sys.modules, "celery", None)
        try:
            reloaded = importlib.reload(celery_app_module)

            # The stub's task decorator should still be usable.
            @reloaded.celery_app.task(name="stub.task")
            def sample_task(x: int) -> int:
                return x + 1

            assert sample_task(1) == 2

            with pytest.raises(RuntimeError, match="Celery is not installed"):
                sample_task.delay(1)
            with pytest.raises(RuntimeError, match="Celery is not installed"):
                sample_task.apply_async(args=[1])

            # conf.update() is a documented no-op on the stub.
            reloaded.celery_app.conf.update(some_setting=True)
        finally:
            mp.undo()
            importlib.reload(celery_app_module)

    def test_reloaded_real_module_restored(self) -> None:
        """After the stub test, reloading again restores the real Celery instance."""
        from celery import Celery

        assert isinstance(celery_app_module.celery_app, Celery)
