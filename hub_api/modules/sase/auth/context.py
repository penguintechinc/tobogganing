"""Context-based authorization evaluator for the SASE module.

Enforces tenant-first isolation then OIDC scope checks on a validated
claims set. Fails closed on any missing or malformed input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hub_api.auth.middleware import _scope_satisfied


@dataclass(slots=True)
class ContextAuthDecision:
    """Decision outcome from context-based auth evaluation.

    ``status`` is the HTTP-equivalent code (200 allow, 401 missing tenant, 403 deny).
    """

    allowed: bool
    reason: str
    status: int = 403


class ContextAuthEvaluator:
    """Evaluate an auth context: tenant claim first, then ``resource:action`` scopes.

    Never branches on role names; reuses hub_api scope matching (wildcards).
    """

    def evaluate(self, context: dict[str, Any]) -> ContextAuthDecision:
        """Return allow/deny for a context.

        Expected keys: ``claims`` (validated JWT claims dict), ``tenant``
        (tenant owning the target resource), ``required_scopes`` (iterable).
        Missing or malformed input denies.
        """
        claims = context.get("claims") if isinstance(context, dict) else None
        if not isinstance(claims, dict):
            return ContextAuthDecision(False, "missing_claims", 401)
        token_tenant = claims.get("tenant")
        if not isinstance(token_tenant, str) or not token_tenant:
            return ContextAuthDecision(False, "missing_tenant_claim", 401)
        resource_tenant = context.get("tenant")
        if not isinstance(resource_tenant, str) or not resource_tenant:
            return ContextAuthDecision(False, "missing_resource_tenant", 403)
        if token_tenant != resource_tenant:
            return ContextAuthDecision(False, "tenant_mismatch", 403)
        required = context.get("required_scopes")
        if isinstance(required, str) or not required:
            return ContextAuthDecision(False, "no_required_scopes_declared", 403)
        scope_str = claims.get("scope", "")
        granted = set(scope_str.split()) if isinstance(scope_str, str) else set()
        if not granted:
            return ContextAuthDecision(False, "missing_scope", 403)
        for scope in required:
            if not isinstance(scope, str) or not _scope_satisfied(scope, granted):
                return ContextAuthDecision(False, f"insufficient_scope:{scope}", 403)
        return ContextAuthDecision(True, "allowed", 200)
