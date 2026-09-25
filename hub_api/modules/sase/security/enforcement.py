"""Unified enforcement action enum and utilities for SASE security decisions."""
from __future__ import annotations

from enum import Enum

__all__ = ["EnforcementAction", "ACTION_SEVERITY", "most_restrictive", "DEFAULT_UNCATEGORIZED"]


class EnforcementAction(str, Enum):
    """Unified enforcement action for security checks.

    Defines the possible actions the security system can take on a request.
    """

    allow = "allow"
    log_only = "log_only"
    soft_block = "soft_block"
    block = "block"
    drop = "drop"
    # isolate = "isolate"  # reserved — not implemented


# Severity ordering: allow (lowest) < log_only < soft_block < block < drop (highest)
ACTION_SEVERITY: dict[EnforcementAction, int] = {
    EnforcementAction.allow: 0,
    EnforcementAction.log_only: 1,
    EnforcementAction.soft_block: 2,
    EnforcementAction.block: 3,
    EnforcementAction.drop: 4,
}

DEFAULT_UNCATEGORIZED = EnforcementAction.allow


def most_restrictive(actions: list[EnforcementAction]) -> EnforcementAction:
    """Return the most restrictive (highest severity) action from a list.

    Args:
        actions: List of EnforcementAction values.

    Returns:
        The action with the highest severity (closest to drop).
    """
    if not actions:
        return DEFAULT_UNCATEGORIZED
    return max(actions, key=lambda a: ACTION_SEVERITY[a])
