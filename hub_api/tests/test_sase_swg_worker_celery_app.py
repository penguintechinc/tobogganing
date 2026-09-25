"""Coverage tests for the SWG Celery app module, including its import-guard fallback.

`celery` is installed in this environment, so the normal `import celery`
path is what naturally executes; the `except ImportError` stub-class
fallback (used when Celery is genuinely unavailable) is exercised by
temporarily blocking the `celery` import via sys.modules and reloading the
module, then restoring real Celery afterward so later tests are unaffected.
"""

from __future__ import annotations

import importlib
import sys

import pytest


class TestCeleryAppRealInstance:
    """Covers the normal (Celery installed) instantiation + conf.update path."""

    def test_celery_app_instance_configured(self) -> None:
        """celery_app is a real Celery instance with the expected config applied."""
        from hub_api.modules.sase.security.swg.worker import celery_app as mod

        assert mod.celery_app is not None
        assert mod.celery_app.conf.task_default_queue == "tobogganing_swg"
        assert mod.celery_app.conf.result_expires == 3600


class TestCeleryAppStubFallback:
    """Covers the ImportError fallback stub used when `celery` isn't installed."""

    def test_stub_used_when_celery_import_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Blocking `import celery` forces the _CeleryStub fallback path to run."""
        import hub_api.modules.sase.security.swg.worker.celery_app as mod

        monkeypatch.setitem(sys.modules, "celery", None)
        try:
            importlib.reload(mod)

            # The stub class stands in for Celery
            assert mod.celery_app.app_name == "tobogganing_swg_worker"
            assert mod.celery_app.conf.update(foo="bar") is None  # stub no-op

            # NOTE: the stub decorator (unlike real Celery) does not implement
            # bind=True's self-injection -- it just wraps the function as-is.
            @mod.celery_app.task(bind=True, name="stub.task")
            def dummy_task(x: int) -> int:
                return x * 2

            # Direct call still runs the wrapped function
            assert dummy_task(21) == 42

            # .delay()/.apply_async() raise since there's no real broker
            with pytest.raises(RuntimeError, match="Celery is not installed"):
                dummy_task.delay(21)
            with pytest.raises(RuntimeError, match="Celery is not installed"):
                dummy_task.apply_async((21,))
        finally:
            # Restore the real Celery-backed module for every other test/module
            monkeypatch.undo()
            importlib.reload(mod)
