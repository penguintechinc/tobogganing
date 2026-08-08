"""Tests for OpenAPI spec generation, auth-gating, and content validation."""
from __future__ import annotations

import asyncio
import json
import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_openapi_spec_file_exists(client):
    """Verify that openapi/v1.yaml file exists and is valid."""
    repo_root = Path(__file__).parent.parent.parent
    spec_path = repo_root / "openapi" / "v1.yaml"

    assert spec_path.exists(), f"OpenAPI spec file not found at {spec_path}"
    assert spec_path.stat().st_size > 0, "OpenAPI spec file is empty"


@pytest.mark.asyncio
async def test_public_docs_no_auth_required(client):
    """/docs/public should be accessible without authentication."""
    response = await client.get("/docs/public")

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = await response.get_json()
    assert "openapi" in data
    assert data["openapi"] == "3.1.0"


@pytest.mark.asyncio
async def test_public_docs_login_only(client):
    """/docs/public should only expose login/token endpoints, not other API surfaces."""
    response = await client.get("/docs/public")

    assert response.status_code == 200
    data = await response.get_json()

    # Should have login path
    assert "/api/v1/auth/login" in data.get("paths", {}), "Login endpoint not in public docs"

    # Should NOT have netsvcs paths (authenticated only)
    netsvcs_paths = [p for p in data.get("paths", {}).keys() if "/netsvcs/" in p]
    assert not netsvcs_paths, f"Public docs exposes netsvcs paths: {netsvcs_paths}"

    # Should NOT have admin/internal paths
    sase_paths = [p for p in data.get("paths", {}).keys() if "/sase/" in p]
    assert not sase_paths, f"Public docs exposes sase paths: {sase_paths}"


@pytest.mark.asyncio
async def test_full_openapi_requires_auth(client):
    """/openapi.json should require authentication."""
    # Without auth token - should return 401
    response = await client.get("/openapi.json")

    assert response.status_code in [401, 403], (
        f"Expected 401/403 without auth, got {response.status_code}. "
        "Full spec must be auth-gated!"
    )

    data = await response.get_json() if response.status_code >= 400 else {}
    if "error" in data:
        assert "unauthorized" in data.get("error", "").lower(), (
            f"Error message should indicate auth issue, got: {data}"
        )


@pytest.mark.asyncio
async def test_generated_spec_contains_core_endpoints(client):
    """Generated spec should contain health and auth endpoints."""
    repo_root = Path(__file__).parent.parent.parent
    spec_path = repo_root / "openapi" / "v1.yaml"

    assert spec_path.exists(), "OpenAPI spec file not generated"

    # Load and parse YAML
    import yaml
    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    assert spec is not None, "OpenAPI spec is not valid YAML"
    assert "openapi" in spec, "Missing 'openapi' field"
    assert "3.1" in spec["openapi"], f"Expected OpenAPI 3.1.x, got {spec['openapi']}"

    # Check for core paths
    paths = spec.get("paths", {})
    assert "/health" in paths, "Missing /health endpoint"
    assert "/ready" in paths, "Missing /ready endpoint"
    assert "/api/v1/auth/login" in paths, "Missing /api/v1/auth/login endpoint"


@pytest.mark.asyncio
async def test_generated_spec_includes_netsvcs_paths(client):
    """The committed spec MUST include netsvcs paths.

    Regression: the generation script previously extracted the spec under a
    plain app_context(), which does not run @app.before_serving, so module
    blueprints (mounted by registry.apply_to inside before_serving) were
    absent — the spec silently shipped with zero module routes. The generator
    now extracts within app.test_app(); this test guards that it stays fixed.
    """
    repo_root = Path(__file__).parent.parent.parent
    spec_path = repo_root / "openapi" / "v1.yaml"

    import yaml
    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    paths = spec.get("paths", {})
    netsvcs_paths = [p for p in paths.keys() if "/netsvcs/" in p]

    assert netsvcs_paths, (
        "OpenAPI spec contains NO netsvcs paths — the generator likely ran "
        "without before_serving (module blueprints unmounted). Regenerate with "
        "scripts/generate_openapi.py (uses app.test_app())."
    )
    assert any("/dns-servers" in p for p in netsvcs_paths), (
        f"netsvcs present but no dns-servers endpoint in spec: {netsvcs_paths}"
    )
    assert any("/zones" in p for p in netsvcs_paths), (
        f"netsvcs present but no zones endpoint in spec: {netsvcs_paths}"
    )


@pytest.mark.asyncio
async def test_generated_spec_has_security_schemes(client):
    """OpenAPI spec should define BearerAuth security scheme."""
    repo_root = Path(__file__).parent.parent.parent
    spec_path = repo_root / "openapi" / "v1.yaml"

    import yaml
    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    components = spec.get("components", {})
    security_schemes = components.get("securitySchemes", {})

    assert "BearerAuth" in security_schemes, "Missing BearerAuth security scheme"

    bearer = security_schemes["BearerAuth"]
    assert bearer.get("type") == "http", "BearerAuth should be type 'http'"
    assert bearer.get("scheme") == "bearer", "BearerAuth should have scheme 'bearer'"
    # Note: quart-schema uses bearer_format (snake_case) not bearerFormat (camelCase)
    assert bearer.get("bearer_format") == "JWT", "BearerAuth should specify JWT format"
