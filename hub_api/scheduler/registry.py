"""Handler registry for scheduled job dispatching.

Maps (module, job_type) tuples to Celery task names for dynamic dispatch.
"""
from __future__ import annotations

# Module-level handler registry: (module, job_type) -> task_name
_handlers: dict[tuple[str, str], str] = {}


def register_job_handler(module: str, job_type: str, task_name: str) -> None:
    """Register a handler task for a (module, job_type) pair.

    Args:
        module: Module name (e.g., "perftest_cluster").
        job_type: Job type identifier (e.g., "server_test").
        task_name: Fully-qualified Celery task name (e.g.,
            "hub_api.modules.perftest_cluster.worker.tasks.run_server_test").
    """
    key = (module, job_type)
    _handlers[key] = task_name


def handler_for(module: str, job_type: str) -> str | None:
    """Look up the handler task name for a (module, job_type) pair.

    Args:
        module: Module name.
        job_type: Job type identifier.

    Returns:
        Fully-qualified task name, or None if not registered.
    """
    key = (module, job_type)
    return _handlers.get(key)


def clear_handlers() -> None:
    """Clear all registered handlers.

    Used in tests to isolate handler state between test cases.
    """
    _handlers.clear()
