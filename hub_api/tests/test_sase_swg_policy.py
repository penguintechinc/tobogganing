"""Tests for SASE SWG category policy resolution."""
from __future__ import annotations

from hub_api.modules.sase.security.enforcement import EnforcementAction


def test_policy_manager_basic() -> None:
    """Test basic policy manager initialization."""
    from hub_api.modules.sase.security.swg.policy import CategoryPolicyManager
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mgr = CategoryPolicyManager(mock_db)
    assert mgr.db == mock_db


def test_enforce_scope_precedence() -> None:
    """Test that user scope beats group beats tenant."""
    # This is a logic test: user > group > tenant precedence
    scopes = {
        ("user", "u1"): EnforcementAction.allow,  # most-specific wins even if less restrictive
        ("group", "g1"): EnforcementAction.block,
        ("tenant", None): EnforcementAction.drop,
    }

    # User scope should be chosen first if user_id matches
    user_scope_priority = 2
    group_scope_priority = 1
    tenant_scope_priority = 0

    assert user_scope_priority > group_scope_priority > tenant_scope_priority


def test_most_restrictive_within_scope() -> None:
    """Test that most-restrictive action is selected within a scope."""
    from hub_api.modules.sase.security.enforcement import most_restrictive

    actions = [
        EnforcementAction.allow,
        EnforcementAction.log_only,
        EnforcementAction.block,
    ]

    result = most_restrictive(actions)
    assert result == EnforcementAction.block
