"""Context-based authentication evaluator for SASE module.

Provides threat-intelligence lookup, impossible-travel detection, and
risk-based step-up for adaptive authentication. Scaffold phase: safe defaults.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ContextAuthDecision:
    """Decision outcome from context-based auth evaluation."""

    allowed: bool
    reason: str


class ContextAuthEvaluator:
    """Evaluate authentication context for risk-based access control.

    Phase-1 scaffold: stub implementation with safe defaults (allow).
    Future phases will integrate threat-intel feeds, geo-IP databases,
    and behavioral analytics for adaptive authentication.
    """

    def evaluate(self, context: dict) -> ContextAuthDecision:
        """Evaluate authentication context and return allow/deny decision.

        Args:
            context: Authentication context (node_id, tenant, location, etc.).

        Returns:
            ContextAuthDecision with allow=True and reason (stub always allows).
        """
        # Phase-1: safe default — allow all requests
        # Future: check threat feeds, impossible travel, risk scores
        return ContextAuthDecision(allowed=True, reason="context_auth_not_implemented")
