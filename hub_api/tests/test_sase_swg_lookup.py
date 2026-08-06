"""Tests for SASE SWG domain lookup and enforcement action resolution."""
from __future__ import annotations

import pytest

from hub_api.modules.sase.security.enforcement import EnforcementAction
from hub_api.modules.sase.security.swg.lookup import SwgLookup
from hub_api.modules.sase.security.swg.radix import RadixTree
from hub_api.modules.sase.security.swg.policy import CategoryPolicyManager
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
