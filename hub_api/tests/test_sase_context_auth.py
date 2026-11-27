"""Tests for SASE context-based authorization evaluator (tenant-first, scope-based)."""

from __future__ import annotations

from typing import Any

import pytest

from hub_api.modules.sase.auth.context import ContextAuthDecision, ContextAuthEvaluator


def _ctx(claims: Any, tenant: Any = "t1", scopes: Any = ("sase:read",)) -> dict[str, Any]:
    """Build an evaluation context."""
    return {"claims": claims, "tenant": tenant, "required_scopes": scopes}


def test_allowed() -> None:
    """Matching tenant and scope allows."""
    d = ContextAuthEvaluator().evaluate(_ctx({"tenant": "t1", "scope": "sase:read x:y"}))
    assert d == ContextAuthDecision(True, "allowed", 200)


def test_allowed_wildcard() -> None:
    """Wildcard scope satisfies requirement."""
    assert ContextAuthEvaluator().evaluate(_ctx({"tenant": "t1", "scope": "sase:*"})).allowed


def test_missing_tenant() -> None:
    """Missing tenant claim rejects before scope checks."""
    d = ContextAuthEvaluator().evaluate(_ctx({"scope": "*:*"}))
    assert (d.allowed, d.reason, d.status) == (False, "missing_tenant_claim", 401)


def test_tenant_mismatch() -> None:
    """Tenant mismatch is 403 even with admin scope."""
    d = ContextAuthEvaluator().evaluate(_ctx({"tenant": "t2", "scope": "*:*"}))
    assert (d.allowed, d.reason, d.status) == (False, "tenant_mismatch", 403)


def test_missing_scope() -> None:
    """No scope claim denies."""
    d = ContextAuthEvaluator().evaluate(_ctx({"tenant": "t1"}))
    assert (d.allowed, d.reason, d.status) == (False, "missing_scope", 403)


def test_wrong_scope() -> None:
    """Unrelated scope denies; role names are ignored."""
    d = ContextAuthEvaluator().evaluate(
        _ctx({"tenant": "t1", "scope": "sase:write", "roles": ["admin"]})
    )
    assert not d.allowed and d.reason == "insufficient_scope:sase:read"


@pytest.mark.parametrize(
    "ctx,reason",
    [
        ({}, "missing_claims"),
        (_ctx({"tenant": "t1", "scope": "sase:read"}, tenant=None), "missing_resource_tenant"),
        (_ctx({"tenant": "t1", "scope": "sase:read"}, scopes=()), "no_required_scopes_declared"),
        (
            _ctx({"tenant": "t1", "scope": "sase:read"}, scopes="sase:read"),
            "no_required_scopes_declared",
        ),
        (_ctx({"tenant": "t1", "scope": 5}), "missing_scope"),
        (_ctx({"tenant": "t1", "scope": "sase:read"}, scopes=(None,)), "insufficient_scope:None"),
    ],
)
def test_fail_closed(ctx: dict[str, Any], reason: str) -> None:
    """Malformed input always denies."""
    d = ContextAuthEvaluator().evaluate(ctx)
    assert not d.allowed and d.reason == reason
