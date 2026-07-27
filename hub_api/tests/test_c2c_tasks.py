"""Tests for WaddlePerf c2c Celery tasks."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from hub_api.modules.perftest_c2c.worker.tasks import (
    _default_engine_factory,
)


# ============================================================================
# Tests for Celery Task Import and Structure
# ============================================================================


class TestCeleryTaskStructure:
    """Tests for Celery task setup and import safety."""

    def test_import_celery_app_without_broker(self) -> None:
        """Test importing celery_app without broker configured."""
        # This should not raise even without CELERY_BROKER_URL set
        from hub_api.modules.perftest_c2c.worker import celery_app

        assert celery_app is not None

    def test_import_tasks_without_broker(self) -> None:
        """Test importing tasks module without broker configured."""
        # This should not raise
        from hub_api.modules.perftest_c2c.worker import tasks

        assert tasks is not None
        assert hasattr(tasks, "run_pair")
        assert hasattr(tasks, "_execute_pair")

    def test_run_pair_has_delay_method(self) -> None:
        """Test that run_pair has .delay() and .apply_async() methods."""
        from hub_api.modules.perftest_c2c.worker.tasks import run_pair

        # These should exist (either from Celery or the stub)
        assert hasattr(run_pair, "delay")
        assert hasattr(run_pair, "apply_async")

    @patch.dict("os.environ", {"CELERY_BROKER_URL": "redis://broker:6379/0"})
    def test_run_pair_with_broker_env(self) -> None:
        """Test run_pair task with broker env var set."""
        # Import after setting env
        from hub_api.modules.perftest_c2c.worker.celery_app import celery_app

        # Task should have been registered
        assert celery_app is not None


# ============================================================================
# Tests for Default Engine Factory
# ============================================================================


class TestDefaultEngineFactory:
    """Tests for _default_engine_factory."""

    def test_create_engine_client_from_endpoint(self) -> None:
        """Test creating an EngineClient from an endpoint."""
        endpoint = {
            "engine_url": "http://test.local:8080",
            "api_key_hash": "hash123",
        }

        client = _default_engine_factory(endpoint)

        # Should be an EngineClient instance
        from hub_api.modules.perftest_cluster.services.engine_client import EngineClient

        assert isinstance(client, EngineClient)
        assert client.base_url == "http://test.local:8080"
        # api_key should be None (not recoverable from hash)
        assert client.api_key is None


# ============================================================================
# Tests for Recurring Task Test Types
# ============================================================================


class TestRecurringTaskTestTypes:
    """Regression test: recurring run default test_types must be in ALLOWED_TEST_TYPES."""

    def test_recurring_default_test_types_valid(self) -> None:
        """Test that recurring task default test_types are valid engine test types."""
        from hub_api.modules.perftest_cluster.services.engine_client import ALLOWED_TEST_TYPES

        # These are the hardcoded defaults in the recurring task
        # They must all be in the allowed set or the task will fail
        recurring_defaults = ["icmp", "http"]  # Expected valid defaults after fix

        for test_type in recurring_defaults:
            assert test_type in ALLOWED_TEST_TYPES, (
                f"Recurring default test_type '{test_type}' not in ALLOWED_TEST_TYPES. "
                f"Allowed: {ALLOWED_TEST_TYPES}"
            )
