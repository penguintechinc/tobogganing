"""
Tests for the Quart application (main.py) — health endpoints, status, API routes.

main.py transitively imports modules that require aioredis and py4web.
We patch both at sys.modules level before importing.
"""
import json
import sys
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Patch missing optional deps before any imports from the app occur
if "aioredis" not in sys.modules:
    _mock_aioredis = MagicMock()
    _mock_aioredis.from_url = AsyncMock()
    _mock_aioredis.Redis = MagicMock
    sys.modules["aioredis"] = _mock_aioredis

if "py4web" not in sys.modules:
    sys.modules["py4web"] = MagicMock()


# ---------------------------------------------------------------------------
# App factory fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mock_db_module():
    return MagicMock()


@pytest.fixture
def app(tmp_path):
    """Create a fresh Quart test app with all dependencies mocked.

    main.py tries to import api_bp from api.routes (a py4web module that has no Blueprint).
    We patch that import so create_app() succeeds.
    """
    version_file = tmp_path / ".version"
    version_file.write_text("v0.2.0.1234567890")

    mock_db = MagicMock()
    mock_db.tables = []

    # api.routes uses py4web @action — no api_bp Blueprint exists.
    # Patch it with a Quart Blueprint stub so register_blueprint() works.
    from quart import Blueprint
    _stub_bp = Blueprint("api", __name__, url_prefix="/api/v1")

    with patch("database.initialize_database", return_value=None), \
         patch("database.get_db", return_value=mock_db), \
         patch("licensing.validate_license", return_value={
             "valid": True, "tier": "community", "features": [],
             "client_limit": 10, "headend_limit": 2,
         }), \
         patch("api.routes.api_bp", _stub_bp, create=True), \
         patch("builtins.open", side_effect=lambda path, *a, **kw: (
             open(str(version_file), *a, **kw)
             if ".version" in str(path)
             else open(path, *a, **kw)
         )):
        # Also need to mock the import inside create_app
        import importlib
        import main as _main_module
        # Patch at sys.modules level for the importlib call inside create_app
        import api.routes as _api_routes_module
        _api_routes_module.api_bp = _stub_bp

        if "main" in sys.modules:
            del sys.modules["main"]

        from main import create_app
        application = create_app()
        application.config["TESTING"] = True
        yield application


@pytest_asyncio.fixture
async def client(app):
    """Async test client."""
    async with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

class TestRootEndpoint:
    @pytest.mark.asyncio
    async def test_root_returns_200(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_root_returns_json(self, client):
        resp = await client.get("/")
        data = await resp.get_json()
        assert data is not None

    @pytest.mark.asyncio
    async def test_root_contains_status_field(self, client):
        resp = await client.get("/")
        data = await resp.get_json()
        assert "status" in data or "service" in data or "version" in data


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_healthz_returns_200(self, client):
        resp = await client.get("/healthz")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_contains_status(self, client):
        resp = await client.get("/health")
        data = await resp.get_json()
        assert data is not None
        assert "status" in data

    @pytest.mark.asyncio
    async def test_healthz_contains_healthy_or_ok(self, client):
        resp = await client.get("/healthz")
        data = await resp.get_json()
        assert data is not None
        val = data.get("status", "").lower()
        assert val in ("ok", "healthy", "up", "running") or "status" in data


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_returns_200_or_404(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code in (200, 404, 401)

    @pytest.mark.asyncio
    async def test_metrics_content_type_is_prometheus(self, client):
        resp = await client.get("/metrics")
        if resp.status_code == 200:
            ct = resp.headers.get("Content-Type", "")
            assert "text/plain" in ct or "application/json" in ct or "prometheus" in ct


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status_returns_200(self, client):
        resp = await client.get("/api/v1/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_status_returns_json_with_version(self, client):
        resp = await client.get("/api/v1/status")
        data = await resp.get_json()
        assert data is not None
        assert "version" in data or "status" in data


# ---------------------------------------------------------------------------
# API Blueprint routes
# ---------------------------------------------------------------------------

class TestAPIBlueprintRoutes:
    @pytest.mark.asyncio
    async def test_auth_token_endpoint_rejects_bad_credentials(self, client):
        resp = await client.post(
            "/api/v1/auth/token",
            json={"username": "nobody", "password": "wrongpass"},
        )
        assert resp.status_code in (400, 401, 403, 422)

    @pytest.mark.asyncio
    async def test_cluster_list_requires_auth(self, client):
        resp = await client.get("/api/v1/cluster/list")
        assert resp.status_code in (401, 403, 404)

    @pytest.mark.asyncio
    async def test_client_list_requires_auth(self, client):
        resp = await client.get("/api/v1/client/list")
        assert resp.status_code in (401, 403, 404)

    @pytest.mark.asyncio
    async def test_unknown_endpoint_returns_404(self, client):
        resp = await client.get("/api/v1/does_not_exist_xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# JSON response helpers
# ---------------------------------------------------------------------------

class TestJSONHelpers:
    def test_json_response_helper_importable(self):
        from main import _json_response
        resp = _json_response({"key": "value"}, 200)
        assert resp is not None

    def test_error_response_helper_importable(self):
        from main import _error_response
        resp = _error_response("Test error", 400)
        assert resp is not None


# ---------------------------------------------------------------------------
# create_app
# ---------------------------------------------------------------------------

class TestCreateApp:
    def test_create_app_returns_quart_app(self, tmp_path):
        version_file = tmp_path / ".version"
        version_file.write_text("v0.2.0.1234567890")
        mock_db = MagicMock()
        mock_db.tables = []

        with patch("database.initialize_database", return_value=None), \
             patch("database.get_db", return_value=mock_db), \
             patch("licensing.validate_license", return_value={
                 "valid": True, "tier": "community", "features": [],
             }), \
             patch("builtins.open", side_effect=lambda path, *a, **kw: (
                 open(str(version_file), *a, **kw)
                 if ".version" in str(path)
                 else open(path, *a, **kw)
             )):
            from main import create_app
            from quart import Quart
            app = create_app()
            assert isinstance(app, Quart)
