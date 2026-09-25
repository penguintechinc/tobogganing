"""Tests for SASE context-based authentication evaluator."""
from __future__ import annotations

import pytest

from hub_api.modules.sase.auth.context import ContextAuthEvaluator, ContextAuthDecision


@pytest.mark.asyncio
async def test_context_auth_evaluator_instantiates() -> None:
    """Test that ContextAuthEvaluator can be instantiated.

    Verifies the stub is wired and ready for future development.
    """
    evaluator = ContextAuthEvaluator()
    assert evaluator is not None


@pytest.mark.asyncio
async def test_context_auth_evaluate_returns_decision() -> None:
    """Test that evaluate returns a ContextAuthDecision.

    Verifies the method signature and return type match the contract.
    """
    evaluator = ContextAuthEvaluator()
    context = {"node_id": "test-node", "tenant": "default"}

    decision = evaluator.evaluate(context)

    assert isinstance(decision, ContextAuthDecision)
    assert isinstance(decision.allowed, bool)
    assert isinstance(decision.reason, str)


@pytest.mark.asyncio
async def test_context_auth_evaluate_safe_default() -> None:
    """Test that evaluate returns allow=True by default (Phase-1 stub).

    Phase-1 scaffold always allows; future phases will integrate threat intel.
    """
    evaluator = ContextAuthEvaluator()
    context = {"node_id": "any-node", "tenant": "any-tenant"}

    decision = evaluator.evaluate(context)

    assert decision.allowed is True
    assert "not_implemented" in decision.reason.lower()
