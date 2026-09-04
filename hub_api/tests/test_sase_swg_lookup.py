"""Tests for SASE SWG domain lookup and enforcement action resolution."""
from __future__ import annotations

import json
import pytest

from hub_api.modules.sase.security.enforcement import EnforcementAction
from hub_api.modules.sase.security.swg.lookup import SwgLookup
from hub_api.modules.sase.security.swg.radix import RadixTree
from hub_api.modules.sase.security.swg.policy import CategoryPolicyManager
from hub_api.cache.client import CacheClient
from unittest.mock import MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_lookup_categorized_domain() -> None:
    """Test lookup of a categorized domain."""
    # Setup mocks
    radix = RadixTree()
    radix.insert("badsite.com", ("gambling", "malware"))

    policy_mgr = MagicMock(spec=CategoryPolicyManager)
    policy_mgr.resolve = AsyncMock(
        return_value=(EnforcementAction.block, "tenant")
    )

    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)

    lookup = SwgLookup(radix, policy_mgr, cache)

    # Lookup
    result = await lookup.lookup(
        "a.b.badsite.com", tenant="acme", user_id="user1"
    )

    # Verify
    assert result.domain == "a.b.badsite.com"
    assert set(result.categories) == {"gambling", "malware"}
    assert result.action == EnforcementAction.block
    assert result.matched_scope == "tenant"
    assert not result.uncategorized


@pytest.mark.asyncio
async def test_lookup_uncategorized_domain() -> None:
    """Test lookup of an uncategorized domain."""
    radix = RadixTree()  # Empty

    policy_mgr = MagicMock(spec=CategoryPolicyManager)
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)

    lookup = SwgLookup(radix, policy_mgr, cache)

    result = await lookup.lookup("unknown.example", tenant="acme")

    # Uncategorized: default allow
    assert result.domain == "unknown.example"
    assert result.categories is None
    assert result.action == EnforcementAction.allow
    assert result.matched_scope == "default"
    assert result.uncategorized


@pytest.mark.asyncio
async def test_lookup_fails_open_on_cache_error() -> None:
    """Test that lookup fails open (returns allow) on cache error."""
    radix = RadixTree()

    policy_mgr = MagicMock(spec=CategoryPolicyManager)
    cache = MagicMock()
    cache.get = AsyncMock(side_effect=Exception("Cache down"))

    lookup = SwgLookup(radix, policy_mgr, cache)

    result = await lookup.lookup("x.com", tenant="acme")

    # Fail open: allow on error
    assert result.action == EnforcementAction.allow
    assert result.uncategorized


def test_radix_to_lookup_flow() -> None:
    """Test integration: radix insert → lookup."""
    radix = RadixTree()
    radix.insert("shop.com", ("shopping",))
    radix.insert("evil.shop.com", ("malware",))

    # Direct radix lookup
    result = radix.lookup("a.evil.shop.com")
    assert result == ("malware",)

    result = radix.lookup("a.shop.com")
    assert result == ("shopping",)


@pytest.mark.asyncio
async def test_lookup_catcache_hit_with_real_client() -> None:
    """Test lookup cache hit using real CacheClient with fallback.

    regression: swg catcache CacheClient signature (namespace-guard) — MagicMock hid the mismatch
    """
    radix = RadixTree()  # Empty radix, will fall through to cache

    policy_mgr = MagicMock(spec=CategoryPolicyManager)
    policy_mgr.resolve = AsyncMock(
        return_value=(EnforcementAction.block, "tenant")
    )

    # Use real CacheClient with unreachable port → in-memory fallback
    cache = CacheClient(host="127.0.0.1", port=6399, db=0)

    # Pre-populate cache with categories
    test_domain = "cached-example.com"
    test_categories = ["malware", "phishing"]
    cache_value = json.dumps(test_categories)
    await cache.set("sase:catcache", test_domain, value=cache_value, ttl_seconds=3600)

    lookup = SwgLookup(radix, policy_mgr, cache)

    # Lookup should hit the cache
    result = await lookup.lookup(test_domain, tenant="acme", user_id="user1")

    # Verify cache hit returned the categories
    assert result.domain == test_domain
    assert set(result.categories) == set(test_categories)
    assert result.action == EnforcementAction.block
    assert result.matched_scope == "tenant"
    assert not result.uncategorized
