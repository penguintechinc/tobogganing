"""Coverage backfill for perftest_c2c/worker/celery_app.py.

The module's ``except ImportError`` branch (the ``_CeleryStub``/``_StubConfig``
fallback used when the ``celery`` package isn't installed) is unreachable in
this environment since celery IS installed. It is reachable, though, by
forcing the import to fail and reloading the module -- exactly the scenario
the fallback exists to handle in a minimal/no-celery deployment. Import state
is fully restored in a ``finally`` block so this doesn't leak into other tests.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest


def test_celery_app_normal_import_configures_broker_and_backend(
    monkeypatch: Any,
) -> None:
    """With celery installed (the normal case), broker/backend/conf come from env."""
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://broker-host:6379/3")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://backend-host:6379/4")

    import hub_api.modules.perftest_c2c.worker.celery_app as celery_app_mod

    reloaded = importlib.reload(celery_app_mod)
    try:
        assert reloaded.broker_url == "redis://broker-host:6379/3"
        assert reloaded.result_backend == "redis://backend-host:6379/4"
        assert reloaded.celery_app.conf.task_default_queue == "perftest_c2c"
    finally:
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
        importlib.reload(reloaded)


def test_celery_app_stub_fallback_when_celery_unavailable() -> None:
    """When ``celery`` cannot be imported, the module falls back to a local stub.

    Forces ``from celery import Celery`` to raise ImportError by clobbering
    ``sys.modules['celery']`` with ``None`` (the documented mechanism for
    forcing an ImportError on a specific module), reloads celery_app.py so it
    executes the ``except ImportError`` branch, then exercises the stub's
    ``.task()`` decorator and ``.delay()`` guard.
    """
    mod_name = "hub_api.modules.perftest_c2c.worker.celery_app"
    original_celery = sys.modules.get("celery")
    original_celery_app_mod = sys.modules.get(mod_name)

    sys.modules["celery"] = None  # type: ignore[assignment]
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    try:
        stub_mod = importlib.import_module(mod_name)

        # The stub Celery class stood in for the real one.
        assert stub_mod.celery_app.app_name == "perftest_c2c"
        assert hasattr(stub_mod.celery_app, "conf")

        # conf.update() is a no-op stub; must not raise.
        stub_mod.celery_app.conf.update(task_acks_late=True)

        # The stub task() decorator wraps a function; calling it directly
        # still executes the original function body.
        @stub_mod.celery_app.task(name="stub.example")
        def _example(x: int) -> int:
            return x * 2

        assert _example(21) == 42

        # .delay()/.apply_async() must raise since there's no real broker.
        with pytest.raises(RuntimeError, match="Celery is not installed"):
            _example.delay(21)
        with pytest.raises(RuntimeError, match="Celery is not installed"):
            _example.apply_async((21,))

    finally:
        # Restore the real celery module and re-import celery_app cleanly so
        # subsequent tests (and any already-imported references) see the
        # genuine Celery-backed module again.
        if original_celery is not None:
            sys.modules["celery"] = original_celery
        else:
            sys.modules.pop("celery", None)

        if mod_name in sys.modules:
            del sys.modules[mod_name]
        importlib.import_module(mod_name)
        if original_celery_app_mod is not None:
            sys.modules[mod_name] = original_celery_app_mod
