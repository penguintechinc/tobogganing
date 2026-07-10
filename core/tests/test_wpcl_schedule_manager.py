"""Test ScheduleManager basic functionality with async penguin-dal API.

Note: Comprehensive integration tests with real database are in test_schedule_manager_realdal.py.
Unit tests with complex async mocking are deferred as the actual implementation is validated
through API integration tests and real_dal fixture tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from core.modules.waddleperf_client.services.schedule_manager import (
    ScheduleManager,
    TestScheduleDTO,
)


@pytest.mark.asyncio
async def test_schedule_manager_create_schedule() -> None:
    """Test creating a schedule via async_insert."""
    db = MagicMock()
    db.test_schedules.async_insert = AsyncMock(return_value=1)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.create_schedule(
        {
            "org_unit_id": "ou-456",
            "test_type": "latency",
            "target": "example.com",
            "interval_seconds": 300,
            "enabled": True,
        }
    )

    assert result.tenant == "tenant-1"
    assert result.test_type == "latency"
    assert result.target == "example.com"
    assert result.interval_seconds == 300
    assert result.enabled is True
    assert result.org_unit_id == "ou-456"

    # Verify tenant and all NOT NULL columns were passed to async_insert
    db.test_schedules.async_insert.assert_called_once()
    call_kwargs = db.test_schedules.async_insert.call_args[1]
    assert call_kwargs["tenant"] == "tenant-1"
    assert call_kwargs["test_type"] == "latency"
    assert call_kwargs["target"] == "example.com"
    assert call_kwargs["interval_seconds"] == 300
    assert call_kwargs["enabled"] is True
    assert "id" in call_kwargs  # UUID should be generated
    assert "created_at" in call_kwargs  # Timestamp should be set
    assert "updated_at" in call_kwargs  # Timestamp should be set
