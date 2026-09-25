"""Tests for netsvcs IOCChecker fail-open error handling.

IOCChecker.check_domain/check_ip must fail OPEN (blocked=False) on any
BlocklistStore error — this is an out-of-band security mandate: a blocklist
cache outage must never add latency or accidentally block legitimate traffic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hub_api.modules.netsvcs.ioc import IOCChecker
from hub_api.modules.threatintel.blocklist.store import BlocklistStore


@pytest.fixture
def checker_with_broken_store() -> IOCChecker:
    """IOCChecker whose underlying store.check() always raises.

    BlocklistStore is @dataclass(slots=True), so its `check` method cannot be
    monkeypatched on the instance directly; replace `checker.store` wholesale
    with a MagicMock spec'd to the same interface instead.
    """
    checker = IOCChecker(cache=AsyncMock())
    checker.store = MagicMock(spec=BlocklistStore)
    checker.store.check = AsyncMock(side_effect=RuntimeError("cache backend down"))
    return checker


@pytest.mark.asyncio
async def test_check_domain_fails_open_on_store_error(
    checker_with_broken_store: IOCChecker,
) -> None:
    """check_domain() returns blocked=False when BlocklistStore.check() raises."""
    result = await checker_with_broken_store.check_domain("evil.example.com")

    assert result == {
        "blocked": False,
        "reason": "",
        "feed_source": "",
        "severity": "",
    }


@pytest.mark.asyncio
async def test_check_ip_fails_open_on_store_error(
    checker_with_broken_store: IOCChecker,
) -> None:
    """check_ip() returns blocked=False when BlocklistStore.check() raises."""
    result = await checker_with_broken_store.check_ip("192.0.2.1")

    assert result == {
        "blocked": False,
        "reason": "",
        "feed_source": "",
        "severity": "",
    }


@pytest.mark.asyncio
async def test_check_domain_blocked_path() -> None:
    """check_domain() returns blocked=True with verdict details when found."""
    checker = IOCChecker(cache=AsyncMock())
    checker.store = MagicMock(spec=BlocklistStore)
    verdict = AsyncMock()
    verdict.source = "spamhaus"
    verdict.severity = "high"
    checker.store.check = AsyncMock(return_value=verdict)

    result = await checker.check_domain("malicious.example.com")

    assert result["blocked"] is True
    assert result["feed_source"] == "spamhaus"
    assert result["severity"] == "high"
    assert "spamhaus" in result["reason"]


@pytest.mark.asyncio
async def test_check_ip_blocked_path() -> None:
    """check_ip() returns blocked=True with verdict details when found."""
    checker = IOCChecker(cache=AsyncMock())
    checker.store = MagicMock(spec=BlocklistStore)
    verdict = AsyncMock()
    verdict.source = "urlhaus"
    verdict.severity = "critical"
    checker.store.check = AsyncMock(return_value=verdict)

    result = await checker.check_ip("198.51.100.1")

    assert result["blocked"] is True
    assert result["feed_source"] == "urlhaus"
    assert result["severity"] == "critical"


@pytest.mark.asyncio
async def test_check_domain_not_blocked() -> None:
    """check_domain() returns blocked=False when store returns no verdict."""
    checker = IOCChecker(cache=AsyncMock())
    checker.store = MagicMock(spec=BlocklistStore)
    checker.store.check = AsyncMock(return_value=None)

    result = await checker.check_domain("safe.example.com")

    assert result["blocked"] is False


@pytest.mark.asyncio
async def test_check_ip_not_blocked() -> None:
    """check_ip() returns blocked=False when store returns no verdict."""
    checker = IOCChecker(cache=AsyncMock())
    checker.store = MagicMock(spec=BlocklistStore)
    checker.store.check = AsyncMock(return_value=None)

    result = await checker.check_ip("203.0.113.1")

    assert result["blocked"] is False
