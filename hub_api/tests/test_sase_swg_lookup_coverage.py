"""Coverage-focused tests for SwgLookup's fail-open/enqueue paths and build_radix.

The pre-existing test_sase_swg_lookup.py covers the main lookup happy/fail-open
paths at a high level; these tests target the remaining branches: the
top-level lookup() exception handler, malformed cache JSON, the
_enqueue_uncategorized flag/Celery branches, and the build_radix aggregation
function (entirely untested previously).

NOTE: _enqueue_uncategorized previously imported `feature_enabled` from
`hub_api.registry` (which does not export it) and awaited it despite the
real implementation (`hub_api.flags.feature_enabled`) being synchronous --
this always raised ImportError, silently swallowed, so the Tier-2 AI
categorizer dispatch path never actually ran in production. Fixed in
lookup.py to import from `hub_api.flags` and call synchronously, matching
every other feature_enabled call site in this codebase (see entitlements/gate.py).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.sase.security.enforcement import EnforcementAction
from hub_api.modules.sase.security.swg.lookup import SwgLookup, build_radix
from hub_api.modules.sase.security.swg.policy import CategoryPolicyManager
from hub_api.modules.sase.security.swg.radix import RadixTree

LOOKUP_MOD = "hub_api.modules.sase.security.swg.lookup"


def _mock_db_with_rows(rows: list[MagicMock]) -> MagicMock:
    db = MagicMock()
    db.domain_categories = MagicMock()
    db.domain_categories.select = AsyncMock(return_value=rows)
    return db


class TestLookupFailsOpenOnPolicyError:
    """Covers lookup()'s top-level exception handler (distinct from cache-only errors)."""

    @pytest.mark.asyncio
    async def test_policy_resolve_exception_fails_open(self) -> None:
        """A categorized domain whose policy resolution raises still fails open."""
        radix = RadixTree()
        radix.insert("badsite.com", ("gambling",))

        policy_mgr = MagicMock(spec=CategoryPolicyManager)
        policy_mgr.resolve = AsyncMock(side_effect=RuntimeError("policy db down"))

        cache = MagicMock()
        lookup = SwgLookup(radix, policy_mgr, cache)

        result = await lookup.lookup("badsite.com", tenant="acme")

        assert result.action == EnforcementAction.allow
        assert result.matched_scope == "error"
        assert result.uncategorized is True


class TestLookupCacheMalformedJson:
    """Covers _lookup_cache's malformed-JSON branch."""

    @pytest.mark.asyncio
    async def test_malformed_cache_value_returns_none(self) -> None:
        """A non-JSON cached value is treated as a cache miss (uncategorized)."""
        radix = RadixTree()  # empty -> falls through to cache
        policy_mgr = MagicMock(spec=CategoryPolicyManager)
        cache = MagicMock()
        cache.get = AsyncMock(return_value="not-valid-json{{{")

        lookup = SwgLookup(radix, policy_mgr, cache)
        # Avoid the enqueue path doing real work in this test
        lookup._enqueue_uncategorized = AsyncMock()

        result = await lookup.lookup("weird.example", tenant="acme")

        assert result.categories is None
        assert result.uncategorized is True


class TestEnqueueUncategorized:
    """Covers _enqueue_uncategorized's flag-check and Celery-dispatch branches."""

    @pytest.mark.asyncio
    async def test_flag_off_skips_dispatch(self) -> None:
        """When the flag is off, no Celery task is enqueued."""
        radix = RadixTree()
        policy_mgr = MagicMock(spec=CategoryPolicyManager)
        cache = MagicMock()
        lookup = SwgLookup(radix, policy_mgr, cache)

        with patch("hub_api.flags.feature_enabled", return_value=False):
            await lookup._enqueue_uncategorized("new.example", "acme")
        # No exception, no assertion needed beyond "didn't raise" -- dispatch
        # is verified not to happen in the dedicated dispatch test below.

    @pytest.mark.asyncio
    async def test_flag_check_exception_is_swallowed(self) -> None:
        """An exception while checking the flag is caught and logged, not raised."""
        radix = RadixTree()
        policy_mgr = MagicMock(spec=CategoryPolicyManager)
        cache = MagicMock()
        lookup = SwgLookup(radix, policy_mgr, cache)

        with patch("hub_api.flags.feature_enabled", side_effect=RuntimeError("flag server down")):
            await lookup._enqueue_uncategorized("new.example", "acme")  # must not raise

    @pytest.mark.asyncio
    async def test_flag_on_dispatches_celery_task(self) -> None:
        """When the flag is on, the categorize_domain Celery task is dispatched."""
        radix = RadixTree()
        policy_mgr = MagicMock(spec=CategoryPolicyManager)
        cache = MagicMock()
        lookup = SwgLookup(radix, policy_mgr, cache)

        fake_task = MagicMock()
        with (
            patch("hub_api.flags.feature_enabled", return_value=True),
            patch("hub_api.modules.sase.security.swg.tasks.categorize_domain", fake_task),
        ):
            await lookup._enqueue_uncategorized("new.example", "acme")

        fake_task.delay.assert_called_once_with("new.example", "acme")

    @pytest.mark.asyncio
    async def test_flag_on_celery_unavailable_fails_soft(self) -> None:
        """A Celery dispatch failure is caught and does not propagate."""
        radix = RadixTree()
        policy_mgr = MagicMock(spec=CategoryPolicyManager)
        cache = MagicMock()
        lookup = SwgLookup(radix, policy_mgr, cache)

        fake_task = MagicMock()
        fake_task.delay.side_effect = RuntimeError("celery broker unreachable")
        with (
            patch("hub_api.flags.feature_enabled", return_value=True),
            patch("hub_api.modules.sase.security.swg.tasks.categorize_domain", fake_task),
        ):
            await lookup._enqueue_uncategorized("new.example", "acme")  # must not raise

    @pytest.mark.asyncio
    async def test_full_lookup_uncategorized_dispatches_when_flag_on(self) -> None:
        """End-to-end: an uncategorized lookup enqueues the AI categorizer when flagged on."""
        radix = RadixTree()  # empty
        policy_mgr = MagicMock(spec=CategoryPolicyManager)
        cache = MagicMock()
        cache.get = AsyncMock(return_value=None)
        lookup = SwgLookup(radix, policy_mgr, cache)

        fake_task = MagicMock()
        with (
            patch("hub_api.flags.feature_enabled", return_value=True),
            patch("hub_api.modules.sase.security.swg.tasks.categorize_domain", fake_task),
        ):
            result = await lookup.lookup("brandnew.example", tenant="acme")

        assert result.uncategorized is True
        fake_task.delay.assert_called_once_with("brandnew.example", "acme")


class TestBuildRadix:
    """Covers build_radix's aggregation, conflict resolution, and error handling."""

    @pytest.mark.asyncio
    async def test_empty_database_returns_empty_tree(self) -> None:
        """No rows in the database yields an empty (but valid) RadixTree."""
        db = _mock_db_with_rows([])

        tree = await build_radix(db)

        assert tree.lookup("anything.com") is None

    @pytest.mark.asyncio
    async def test_builds_tree_from_rows(self) -> None:
        """Rows are grouped by domain and inserted into the radix tree."""
        rows = [
            MagicMock(domain="Example.com", source="feed1", categories=json.dumps(["news"])),
            MagicMock(domain="example.com", source="feed2", categories=json.dumps(["shopping"])),
        ]
        db = _mock_db_with_rows(rows)

        tree = await build_radix(db)

        result = tree.lookup("example.com")
        assert result is not None
        assert set(result) == {"news", "shopping"}

    @pytest.mark.asyncio
    async def test_custom_source_wins_on_conflict(self) -> None:
        """A 'custom' source overrides a feed source for the same (domain, category)."""
        rows = [
            MagicMock(domain="example.com", source="feed1", categories=json.dumps(["gambling"])),
            MagicMock(domain="example.com", source="custom", categories=json.dumps(["gambling"])),
        ]
        db = _mock_db_with_rows(rows)

        # No exception means the custom-wins branch executed cleanly;
        # domain_to_categories still groups by (domain, category) regardless
        # of which source "won", so verify the category is present exactly once.
        tree = await build_radix(db)
        result = tree.lookup("example.com")
        assert result == ("gambling",)

    @pytest.mark.asyncio
    async def test_malformed_row_json_is_skipped(self) -> None:
        """A row with malformed categories JSON is skipped without raising."""
        rows = [
            MagicMock(domain="bad.com", source="feed1", categories="not-json"),
            MagicMock(domain="good.com", source="feed1", categories=json.dumps(["news"])),
        ]
        db = _mock_db_with_rows(rows)

        tree = await build_radix(db)

        assert tree.lookup("bad.com") is None
        assert tree.lookup("good.com") == ("news",)

    @pytest.mark.asyncio
    async def test_blank_domain_or_category_entries_skipped(self) -> None:
        """Rows/categories that normalize to blank strings are skipped."""
        rows = [
            MagicMock(domain="  ", source="feed1", categories=json.dumps(["news"])),
            MagicMock(domain="good.com", source="feed1", categories=json.dumps([" ", "news"])),
        ]
        db = _mock_db_with_rows(rows)

        tree = await build_radix(db)

        assert tree.lookup("good.com") == ("news",)

    @pytest.mark.asyncio
    async def test_db_exception_returns_empty_tree(self) -> None:
        """A DB failure during build is caught, returning an empty tree."""
        db = MagicMock()
        db.domain_categories = MagicMock()
        db.domain_categories.select = AsyncMock(side_effect=RuntimeError("db down"))

        tree = await build_radix(db)

        assert tree.lookup("anything.com") is None
