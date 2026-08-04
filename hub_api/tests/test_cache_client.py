"""Tests for CacheClient with namespace guards and fallback behavior."""

from __future__ import annotations

import pytest

from hub_api.cache.client import CacheClient, CacheUnavailable
from hub_api.cache.keys import NAMESPACES, NamespaceError, prefixed


def test_prefixed_builds_namespaced_key() -> None:
    """Test that prefixed() builds correct namespace:parts key format."""
    assert prefixed("auth", "refresh", "cluster:1") == "auth:refresh:cluster:1"
    assert prefixed("rl", "k") == "rl:k"
    assert prefixed("sase:blocklist", "ip", "1.2.3.4") == "sase:blocklist:ip:1.2.3.4"


def test_prefixed_rejects_unknown_namespace() -> None:
    """Test that prefixed() raises NamespaceError for unknown namespaces."""
    with pytest.raises(NamespaceError):
        prefixed("bogus", "x")
    with pytest.raises(NamespaceError):
        prefixed("invalid", "a", "b")


def test_namespaces_frozen_set() -> None:
    """Test that NAMESPACES is a frozenset with expected values."""
    assert isinstance(NAMESPACES, frozenset)
    assert "auth" in NAMESPACES
    assert "rl" in NAMESPACES
    assert "sase:blocklist" in NAMESPACES
    assert "sase:catcache" in NAMESPACES


@pytest.mark.asyncio
async def test_set_get_roundtrip_or_fallback() -> None:
    """Test set/get roundtrip with fallback to in-memory on unreachable backend."""
    # Unreachable port (6399) — should fall back to in-memory, no raise
    c = CacheClient(host="127.0.0.1", port=6399, db=0)

    # best-effort (default fail_closed=False): set/get degrade to in-memory fallback
    await c.set("rl", "k", value="v", ttl_seconds=5)
    assert await c.get("rl", "k") == "v"

    # exists should work via fallback
    assert await c.exists("rl", "k") is True

    # delete should work via fallback
    await c.delete("rl", "k")
    assert await c.get("rl", "k") is None


@pytest.mark.asyncio
async def test_fail_closed_raises_when_backend_down() -> None:
    """Test that fail_closed=True raises CacheUnavailable when backend is down."""
    c = CacheClient(host="127.0.0.1", port=6399, db=0)

    # fail_closed=True on an unreachable backend should raise
    with pytest.raises(CacheUnavailable):
        await c.get("auth", "x", fail_closed=True)

    # set with fail_closed=True should also raise
    with pytest.raises(CacheUnavailable):
        await c.set("auth", "x", value="v", fail_closed=True)
