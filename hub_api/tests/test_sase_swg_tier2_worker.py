"""Tests for Celery task + hook + write-back (Slice E Task 4)."""
from __future__ import annotations

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


class TestTasksModuleImport:
    """Test that tasks module can be imported and functions exist."""

    def test_categorize_domain_exists(self) -> None:
        """categorize_domain task is defined."""
        from hub_api.modules.sase.security.swg.tasks import categorize_domain

        assert categorize_domain is not None

    def test_refresh_categories_daily_exists(self) -> None:
        """refresh_categories_daily function is defined."""
        from hub_api.modules.sase.security.swg.tasks import refresh_categories_daily

        assert refresh_categories_daily is not None


class TestModuleContract:
    """Test that module() registers flags and entitlements."""

    def test_module_registers_ai_categorizer_flag(self) -> None:
        """module() includes swg_ai_categorizer flag."""
        from hub_api.modules.sase import module

        contract = module()
        assert "tobogganing.sase.swg_ai_categorizer" in contract.flags

    def test_module_registers_ai_categorizer_entitlement(self) -> None:
        """module() includes swg_ai_categorizer entitlement at professional tier."""
        from hub_api.modules.sase import module

        contract = module()
        entitlements = {e.feature: e.tier for e in contract.entitlements}
        assert "sase.swg_ai_categorizer" in entitlements
        assert entitlements["sase.swg_ai_categorizer"] == "professional"
