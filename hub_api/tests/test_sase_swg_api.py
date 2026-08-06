"""Tests for SASE SWG API endpoints."""
from __future__ import annotations

import pytest


def test_lookup_result_dto_fields() -> None:
    """Test that LookupResultDTO has the correct fields."""
    from hub_api.modules.sase.security.swg.api import LookupResultDTO

    dto = LookupResultDTO(
        domain="example.com",
        categories=["news", "shopping"],
        action="allow",
        matched_scope="tenant",
        uncategorized=False,
    )

    assert dto.domain == "example.com"
    assert set(dto.categories) == {"news", "shopping"}
    assert dto.action == "allow"
    assert dto.matched_scope == "tenant"
    assert not dto.uncategorized


def test_swg_blueprint_registration() -> None:
    """Test that SWG blueprint is correctly imported."""
    from hub_api.modules.sase.security.swg.api import blueprint as swg_blueprint

    assert swg_blueprint.name == "sase_swg"
    assert swg_blueprint.url_prefix == "/swg"


def test_swg_blueprint_has_routes() -> None:
    """Test that SWG blueprint is a valid Blueprint object."""
    from hub_api.modules.sase.security.swg.api import blueprint as swg_blueprint

    # Verify it's a Blueprint and has the correct configuration
    assert swg_blueprint is not None
    assert hasattr(swg_blueprint, 'deferred_functions')
    assert len(swg_blueprint.deferred_functions) > 0  # Should have registered routes
