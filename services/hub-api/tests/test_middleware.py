"""Tests for scope-based authorization middleware (auth/middleware.py).

The middleware is built for py4web, so we mock ``py4web.request`` and
``py4web.response`` at the module level before importing the units under test.
``get_jwt_claims`` is patched at its call-site within the middleware module so
tests can control the returned claims dict without needing a live JWT stack.
"""
import sys
import types
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Minimal py4web stub — must be in place before any auth.* import
# ---------------------------------------------------------------------------

def _install_py4web_stub():
    """Inject a minimal py4web stub into sys.modules."""
    if "py4web" in sys.modules:
        return  # already present (e.g. installed)

    stub = types.ModuleType("py4web")

    # Shared mutable request/response objects that tests can mutate freely
    _request = MagicMock()
    _request.headers = {}
    _response = MagicMock()
    _response.status = 200
    _response.headers = {}

    stub.request = _request
    stub.response = _response
    sys.modules["py4web"] = stub


_install_py4web_stub()

# Install structlog stub so auth.middleware can import it
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = MagicMock(return_value=MagicMock())
    sys.modules["structlog"] = _structlog

# Install database.models stub for TenantContext
if "database" not in sys.modules:
    _db_mod = types.ModuleType("database")
    _db_mod.get_db = MagicMock()

    _db_models = types.ModuleType("database.models")

    from dataclasses import dataclass

    @dataclass
    class TenantContext:
        tenant_id: str
        name: str
        spiffe_trust_domain: str
        is_active: bool

    _db_models.TenantContext = TenantContext
    sys.modules["database"] = _db_mod
    sys.modules["database.models"] = _db_models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request_mock(headers=None, jwt_claims=None):
    """Return a fresh mock for py4web.request."""
    import py4web
    mock_req = py4web.request
    mock_req.headers = headers or {}
    mock_req.jwt_claims = jwt_claims
    return mock_req


def _make_response_mock():
    """Return the py4web.response mock (already patched globally)."""
    import py4web
    py4web.response.status = 200
    py4web.response.headers = {}
    return py4web.response


# ---------------------------------------------------------------------------
# Tests: scope_required
# ---------------------------------------------------------------------------

class TestScopeRequired:
    """Tests for the scope_required decorator factory."""

    @patch("auth.middleware.get_jwt_claims")
    def test_missing_auth_returns_401(self, mock_claims):
        """No Bearer header → claims is None → 401."""
        mock_claims.return_value = None

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()

        assert result["status"] == "error"
        assert "data" in result
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    def test_matching_scope_passes(self, mock_claims):
        """Claims include the required scope → handler is called."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": "policies:read policies:write",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success", "data": "ok"})
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()
        handler.assert_called_once()

    @patch("auth.middleware.get_jwt_claims")
    def test_insufficient_scope_returns_403(self, mock_claims):
        """Claims hold only read, endpoint needs admin → 403."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": "policies:read",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = scope_required("policies:admin")(handler)

        result = wrapped()

        assert result["status"] == "error"
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    def test_wildcard_scope_satisfies(self, mock_claims):
        """Claims hold *:read which satisfies policies:read."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": "*:read",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()
        handler.assert_called_once()

    @patch("auth.middleware.get_jwt_claims")
    def test_full_wildcard_satisfies_anything(self, mock_claims):
        """*:* satisfies every scope requirement."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": "*:*",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:admin", "users:delete", "tenants:admin")(handler)

        result = wrapped()
        handler.assert_called_once()

    @patch("auth.middleware.get_jwt_claims")
    def test_multiple_required_all_satisfied(self, mock_claims):
        """All required scopes must be present — both satisfied here."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": "policies:read hubs:read",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:read", "hubs:read")(handler)

        wrapped()
        handler.assert_called_once()

    @patch("auth.middleware.get_jwt_claims")
    def test_multiple_required_one_missing(self, mock_claims):
        """All required scopes must be present — one is missing → 403."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": "policies:read",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:read", "hubs:write")(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    def test_scope_as_list_in_claims(self, mock_claims):
        """``scope`` claim may arrive as a Python list (internally issued tokens)."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": ["policies:read", "hubs:write"],
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()
        handler.assert_called_once()

    @patch("auth.middleware.get_jwt_claims")
    def test_scopes_claim_fallback(self, mock_claims):
        """``scopes`` (plural) claim is tried as fallback when ``scope`` is absent."""
        import py4web
        py4web.request.jwt_claims = {
            "scopes": "policies:read",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()
        handler.assert_called_once()

    @patch("auth.middleware.get_jwt_claims")
    def test_no_scope_claim_returns_403(self, mock_claims):
        """Claims with no scope at all → 403 for a required scope."""
        import py4web
        py4web.request.jwt_claims = {"tenant": "acme"}
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    def test_preserves_handler_return_value(self, mock_claims):
        """The wrapper transparently returns the handler's return value."""
        import py4web
        expected = {"status": "success", "data": {"id": "42"}, "meta": {}}
        py4web.request.jwt_claims = {
            "scope": "*:read",
            "tenant": "acme",
        }
        mock_claims.return_value = py4web.request.jwt_claims

        from auth.middleware import scope_required
        handler = MagicMock(return_value=expected)
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()
        assert result is expected

    @patch("auth.middleware.get_jwt_claims")
    def test_uses_cached_claims_from_request(self, mock_claims):
        """If request.jwt_claims already set, get_jwt_claims is not called again."""
        import py4web
        py4web.request.jwt_claims = {
            "scope": "*:read",
            "tenant": "acme",
        }
        # Return None to detect if get_jwt_claims was invoked
        mock_claims.return_value = None

        from auth.middleware import scope_required
        handler = MagicMock(return_value={"status": "success"})
        wrapped = scope_required("policies:read")(handler)

        result = wrapped()
        # Handler should be called because request.jwt_claims was already populated
        handler.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: tenant_required
# ---------------------------------------------------------------------------

class TestTenantRequired:
    """Tests for the tenant_required decorator."""

    @patch("auth.middleware.get_jwt_claims")
    def test_no_claims_returns_401(self, mock_claims):
        mock_claims.return_value = None

        from auth.middleware import tenant_required
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = tenant_required(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    def test_missing_tenant_claim_returns_403(self, mock_claims):
        mock_claims.return_value = {"scope": "*:read"}  # no tenant key

        from auth.middleware import tenant_required
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = tenant_required(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    @patch("database.get_db")
    def test_tenant_not_found_returns_403(self, mock_get_db, mock_claims):
        mock_claims.return_value = {"scope": "*:read", "tenant": "ghost-tenant"}
        mock_db = MagicMock()
        mock_db.return_value.select.return_value.first.return_value = None
        mock_get_db.return_value = mock_db

        from auth.middleware import tenant_required
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = tenant_required(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    @patch("database.get_db")
    def test_inactive_tenant_returns_403(self, mock_get_db, mock_claims):
        mock_claims.return_value = {"scope": "*:read", "tenant": "frozen"}
        row = MagicMock()
        row.tenant_id = "frozen"
        row.name = "Frozen Inc"
        row.spiffe_trust_domain = "frozen.tobogganing.io"
        row.is_active = False

        mock_db = MagicMock()
        mock_db.return_value.select.return_value.first.return_value = row
        mock_get_db.return_value = mock_db

        from auth.middleware import tenant_required
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = tenant_required(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: require_scope (combined decorator)
# ---------------------------------------------------------------------------

class TestRequireScope:
    """Tests for the combined require_scope decorator."""

    @patch("auth.middleware.get_jwt_claims")
    def test_no_auth_returns_401(self, mock_claims):
        mock_claims.return_value = None

        from auth.middleware import require_scope
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = require_scope("policies:read")(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()

    @patch("auth.middleware.get_jwt_claims")
    def test_missing_tenant_claim_returns_403(self, mock_claims):
        mock_claims.return_value = {"scope": "*:read"}  # no tenant

        from auth.middleware import require_scope
        handler = MagicMock(return_value={"data": "ok"})
        wrapped = require_scope("policies:read")(handler)

        result = wrapped()
        assert result["status"] == "error"
        handler.assert_not_called()

    def test_wraps_preserves_docstring(self):
        """@functools.wraps must preserve the inner function's identity."""
        from auth.middleware import require_scope

        def my_handler():
            """My handler docstring."""

        wrapped = require_scope("policies:read")(my_handler)
        assert wrapped.__name__ == "my_handler"
        assert "My handler docstring" in (wrapped.__doc__ or "")
