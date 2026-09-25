"""Tests for SASE SWG models and enforcement action enum."""
from __future__ import annotations

from hub_api.modules.sase.security.enforcement import (
    EnforcementAction,
    ACTION_SEVERITY,
    most_restrictive,
    DEFAULT_UNCATEGORIZED,
)


def test_action_enum_values() -> None:
    """Verify EnforcementAction enum members have correct string values."""
    assert EnforcementAction.allow.value == "allow"
    assert EnforcementAction.log_only.value == "log_only"
    assert EnforcementAction.soft_block.value == "soft_block"
    assert EnforcementAction.block.value == "block"
    assert EnforcementAction.drop.value == "drop"


def test_action_severity_ordering() -> None:
    """Verify ACTION_SEVERITY defines correct ordering."""
    assert ACTION_SEVERITY[EnforcementAction.allow] < ACTION_SEVERITY[EnforcementAction.log_only]
    assert ACTION_SEVERITY[EnforcementAction.log_only] < ACTION_SEVERITY[EnforcementAction.soft_block]
    assert ACTION_SEVERITY[EnforcementAction.soft_block] < ACTION_SEVERITY[EnforcementAction.block]
    assert ACTION_SEVERITY[EnforcementAction.block] < ACTION_SEVERITY[EnforcementAction.drop]


def test_most_restrictive() -> None:
    """Test most_restrictive picks the highest severity action."""
    result = most_restrictive([EnforcementAction.allow, EnforcementAction.block, EnforcementAction.log_only])
    assert result == EnforcementAction.block

    result = most_restrictive([EnforcementAction.drop, EnforcementAction.block])
    assert result == EnforcementAction.drop

    result = most_restrictive([EnforcementAction.allow])
    assert result == EnforcementAction.allow


def test_default_uncategorized() -> None:
    """Verify DEFAULT_UNCATEGORIZED is allow."""
    assert DEFAULT_UNCATEGORIZED == EnforcementAction.allow
