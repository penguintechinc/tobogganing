"""Coverage-focused tests for CategoryPolicyManager's CRUD + resolution logic.

The pre-existing test_sase_swg_policy.py only smoke-tests initialization and
tests scope-precedence/most_restrictive as standalone logic; these tests
drive set_policy, get_policies, resolve, and _get_policy directly against a
mocked DAL, including validation and exception-swallowing branches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hub_api.modules.sase.security.enforcement import EnforcementAction
from hub_api.modules.sase.security.swg.policy import CategoryPolicyManager


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.category_policies = MagicMock()
    db.category_policies.select = AsyncMock(return_value=[])
    db.category_policies.insert = AsyncMock(return_value="row-1")
    db.category_policies.update = AsyncMock(return_value=1)
    return db


class TestSetPolicy:
    """Covers set_policy's validation, insert/update, and exception branches."""

    @pytest.mark.asyncio
    async def test_invalid_scope_is_rejected(self) -> None:
        """An unrecognized scope logs a warning and does not touch the DB."""
        db = _mock_db()
        mgr = CategoryPolicyManager(db)

        await mgr.set_policy("tenant-a", "not-a-scope", None, "gambling", "block")

        db.category_policies.insert.assert_not_called()
        db.category_policies.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_action_is_rejected(self) -> None:
        """An unrecognized action logs a warning and does not touch the DB."""
        db = _mock_db()
        mgr = CategoryPolicyManager(db)

        await mgr.set_policy("tenant-a", "tenant", None, "gambling", "not-a-real-action")

        db.category_policies.insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_inserts_new_policy(self) -> None:
        """A valid policy with no existing match is inserted."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(return_value=[])
        mgr = CategoryPolicyManager(db)

        await mgr.set_policy("tenant-a", "tenant", None, "gambling", "block")

        db.category_policies.insert.assert_called_once()
        inserted = db.category_policies.insert.call_args[0][0]
        assert inserted["category"] == "gambling"
        assert inserted["action"] == "block"

    @pytest.mark.asyncio
    async def test_updates_existing_policy(self) -> None:
        """A matching existing policy is updated rather than inserted."""
        db = _mock_db()
        existing = MagicMock(action="allow")
        db.category_policies.select = AsyncMock(return_value=[existing])
        mgr = CategoryPolicyManager(db)

        await mgr.set_policy("tenant-a", "tenant", None, "gambling", "block")

        db.category_policies.update.assert_called_once_with(existing)
        assert existing.action == "block"
        db.category_policies.insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_exception_is_swallowed(self) -> None:
        """A DB failure during set_policy is logged and swallowed."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(side_effect=RuntimeError("db down"))
        mgr = CategoryPolicyManager(db)

        await mgr.set_policy("tenant-a", "tenant", None, "gambling", "block")  # must not raise


class TestGetPolicies:
    """Covers get_policies' success/empty/exception branches."""

    @pytest.mark.asyncio
    async def test_returns_rows_as_list(self) -> None:
        """Rows returned by the DB are converted to a list."""
        db = _mock_db()
        row = MagicMock()
        db.category_policies.select = AsyncMock(return_value=[row])
        mgr = CategoryPolicyManager(db)

        result = await mgr.get_policies("tenant-a")

        assert result == [row]

    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty_list(self) -> None:
        """A falsy rowset returns an empty list."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(return_value=None)
        mgr = CategoryPolicyManager(db)

        result = await mgr.get_policies("tenant-a")

        assert result == []

    @pytest.mark.asyncio
    async def test_db_exception_returns_empty_list(self) -> None:
        """A DB failure while fetching policies returns an empty list."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(side_effect=RuntimeError("db down"))
        mgr = CategoryPolicyManager(db)

        result = await mgr.get_policies("tenant-a")

        assert result == []


class TestResolve:
    """Covers resolve()'s scope-precedence and exception-handling branches."""

    @pytest.mark.asyncio
    async def test_no_categories_returns_default(self) -> None:
        """None/empty categories resolve to the tenant default immediately."""
        db = _mock_db()
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve("tenant-a", None)

        assert scope == "default"
        db.category_policies.select.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_policies_returns_default(self) -> None:
        """A tenant with zero policies resolves to the default action."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(return_value=[])
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve("tenant-a", ("gambling",))

        assert scope == "default"

    @pytest.mark.asyncio
    async def test_no_matching_category_returns_default(self) -> None:
        """Policies exist but none match the looked-up categories."""
        db = _mock_db()
        policy = MagicMock(category="shopping", scope="tenant", scope_id=None, action="block")
        db.category_policies.select = AsyncMock(return_value=[policy])
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve("tenant-a", ("gambling",))

        assert scope == "default"

    @pytest.mark.asyncio
    async def test_user_scope_takes_precedence(self) -> None:
        """A matching user-scoped policy wins over group/tenant policies."""
        db = _mock_db()
        policies = [
            MagicMock(category="gambling", scope="tenant", scope_id=None, action="drop"),
            MagicMock(category="gambling", scope="group", scope_id="g1", action="block"),
            MagicMock(category="gambling", scope="user", scope_id="u1", action="allow"),
        ]
        db.category_policies.select = AsyncMock(return_value=policies)
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve(
            "tenant-a", ("gambling",), user_id="u1", group_ids=("g1",)
        )

        assert scope == "user"
        assert action == EnforcementAction.allow

    @pytest.mark.asyncio
    async def test_group_scope_wins_when_no_user_match(self) -> None:
        """A group-scoped policy wins when no user-scoped policy matches."""
        db = _mock_db()
        policies = [
            MagicMock(category="gambling", scope="tenant", scope_id=None, action="drop"),
            MagicMock(category="gambling", scope="group", scope_id="g1", action="block"),
        ]
        db.category_policies.select = AsyncMock(return_value=policies)
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve(
            "tenant-a", ("gambling",), user_id="someone-else", group_ids=("g1",)
        )

        assert scope == "group"
        assert action == EnforcementAction.block

    @pytest.mark.asyncio
    async def test_tenant_scope_wins_when_no_user_or_group_match(self) -> None:
        """A tenant-scoped policy applies when neither user nor group match."""
        db = _mock_db()
        policies = [MagicMock(category="gambling", scope="tenant", scope_id=None, action="drop")]
        db.category_policies.select = AsyncMock(return_value=policies)
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve("tenant-a", ("gambling",))

        assert scope == "tenant"
        assert action == EnforcementAction.drop

    @pytest.mark.asyncio
    async def test_most_restrictive_selected_within_a_scope(self) -> None:
        """Multiple tenant-scoped matches pick the most restrictive action."""
        db = _mock_db()
        policies = [
            MagicMock(category="gambling", scope="tenant", scope_id=None, action="allow"),
            MagicMock(category="gambling", scope="tenant", scope_id=None, action="block"),
        ]
        db.category_policies.select = AsyncMock(return_value=policies)
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve("tenant-a", ("gambling",))

        assert action == EnforcementAction.block

    @pytest.mark.asyncio
    async def test_matching_policy_with_no_scope_match_returns_default(self) -> None:
        """A matching-category policy that fits no scope bucket falls through to default."""
        db = _mock_db()
        # scope="user" but caller passes no user_id -> user_policies filtered to []
        # group_ids also None -> group_policies filtered to []
        # scope != "tenant" -> tenant_policies also []
        policy = MagicMock(category="gambling", scope="user", scope_id="u1", action="block")
        db.category_policies.select = AsyncMock(return_value=[policy])
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve("tenant-a", ("gambling",))

        assert scope == "default"

    @pytest.mark.asyncio
    async def test_exception_fails_open_to_default(self) -> None:
        """An exception during resolution fails open to the default action."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(side_effect=RuntimeError("db down"))
        mgr = CategoryPolicyManager(db)

        action, scope = await mgr.resolve("tenant-a", ("gambling",))

        assert scope == "default"


class TestGetPolicy:
    """Covers _get_policy's row-found/not-found/exception branches."""

    @pytest.mark.asyncio
    async def test_returns_first_matching_row(self) -> None:
        """The first row from the DB query is returned."""
        db = _mock_db()
        row = MagicMock()
        db.category_policies.select = AsyncMock(return_value=[row])
        mgr = CategoryPolicyManager(db)

        result = await mgr._get_policy("tenant-a", "tenant", None, "gambling")

        assert result is row

    @pytest.mark.asyncio
    async def test_no_rows_returns_none(self) -> None:
        """An empty rowset returns None."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(return_value=[])
        mgr = CategoryPolicyManager(db)

        result = await mgr._get_policy("tenant-a", "tenant", None, "gambling")

        assert result is None

    @pytest.mark.asyncio
    async def test_db_exception_returns_none(self) -> None:
        """A DB failure while fetching a single policy returns None."""
        db = _mock_db()
        db.category_policies.select = AsyncMock(side_effect=RuntimeError("db down"))
        mgr = CategoryPolicyManager(db)

        result = await mgr._get_policy("tenant-a", "tenant", None, "gambling")

        assert result is None
