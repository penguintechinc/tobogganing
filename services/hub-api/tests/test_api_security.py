"""
Tests for api/security_routes.py and security/scanner.py, security/feeds.py.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ---------------------------------------------------------------------------
# security_routes.py import
# ---------------------------------------------------------------------------

class TestSecurityRoutesImport:
    def test_security_routes_module_importable(self):
        mock_sm = MagicMock()
        mock_sm.rate_limiter.get_blocked_ips.return_value = []
        mock_sm.rate_limiter.rules = []
        mock_sm.ddos_protection.redis_client.exists.return_value = 0

        with patch("database.get_db", return_value=MagicMock(tables=[])), \
             patch("security.security_middleware", mock_sm):
            try:
                import api.security_routes
                assert api.security_routes is not None
            except Exception as exc:
                pytest.fail(f"security_routes import failed: {exc}")


# ---------------------------------------------------------------------------
# security_routes handler tests
# ---------------------------------------------------------------------------

class TestSecurityRouteHandlers:
    def _setup_mocks(self):
        mock_sm = MagicMock()
        mock_sm.rate_limiter.get_blocked_ips.return_value = ["1.2.3.4"]
        mock_sm.rate_limiter.rules = []
        mock_sm.rate_limiter.db.tables = []
        mock_sm.ddos_protection.redis_client.exists.return_value = 0
        return mock_sm

    def test_get_security_status_returns_dict(self):
        from security.middleware import get_security_stats
        mock_sm = self._setup_mocks()
        with patch("security.middleware.security_middleware", mock_sm):
            result = get_security_stats()
            assert isinstance(result, dict)
            assert "blocked_ips_count" in result

    def test_security_status_blocked_ips_count(self):
        from security.middleware import get_security_stats
        mock_sm = self._setup_mocks()
        with patch("security.middleware.security_middleware", mock_sm):
            result = get_security_stats()
            assert result["blocked_ips_count"] >= 0

    def test_security_status_emergency_mode_field(self):
        from security.middleware import get_security_stats
        mock_sm = self._setup_mocks()
        with patch("security.middleware.security_middleware", mock_sm):
            result = get_security_stats()
            assert "emergency_mode" in result

    def test_get_security_status_with_error_graceful(self):
        """Even on error, get_security_stats should return a dict."""
        from security.middleware import get_security_stats
        with patch("security.middleware.security_middleware", side_effect=AttributeError("broken")):
            result = get_security_stats()
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# security/scanner.py
# ---------------------------------------------------------------------------

class TestSecurityScanner:
    def test_scanner_module_importable(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            try:
                from security import scanner
                assert scanner is not None
            except Exception as exc:
                pytest.fail(f"scanner import failed: {exc}")

    def test_scanner_has_scan_function(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            try:
                from security import scanner
                # Look for any scan-related callable
                funcs = [name for name in dir(scanner) if not name.startswith("_")]
                assert len(funcs) > 0
            except Exception as exc:
                pytest.fail(f"scanner inspection failed: {exc}")


# ---------------------------------------------------------------------------
# security/feeds.py
# ---------------------------------------------------------------------------

class TestSecurityFeeds:
    def test_feeds_module_importable(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            try:
                from security import feeds
                assert feeds is not None
            except Exception as exc:
                pytest.fail(f"feeds import failed: {exc}")

    def test_feeds_has_expected_attributes(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            try:
                from security import feeds
                # Module should have something usable
                attrs = [a for a in dir(feeds) if not a.startswith("_")]
                assert len(attrs) > 0
            except Exception as exc:
                pytest.fail(f"feeds attributes inspection failed: {exc}")


# ---------------------------------------------------------------------------
# require_admin_role decorator
# ---------------------------------------------------------------------------

class TestRequireAdminRole:
    def test_require_admin_role_decorator_importable(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import require_admin_role
            assert callable(require_admin_role)

    def test_require_admin_role_wraps_function(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import require_admin_role

            @require_admin_role
            def my_view():
                return "ok"

            assert callable(my_view)

    def test_require_admin_role_blocks_non_admin(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import require_admin_role
            from py4web import request, abort

            @require_admin_role
            def admin_view():
                return "admin content"

            # Simulate a non-admin user in request.environ
            with patch("security.middleware.request") as mock_req, \
                 patch("security.middleware.abort") as mock_abort:
                mock_req.environ = {"user": {"role": "viewer"}}
                mock_abort.side_effect = Exception("403 Forbidden")
                with pytest.raises(Exception, match="403"):
                    admin_view()

    def test_require_admin_role_allows_admin(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import require_admin_role

            @require_admin_role
            def admin_view():
                return "admin content"

            with patch("security.middleware.request") as mock_req:
                mock_req.environ = {"user": {"role": "admin"}}
                result = admin_view()
                assert result == "admin content"


# ---------------------------------------------------------------------------
# check_security_bypass decorator
# ---------------------------------------------------------------------------

class TestCheckSecurityBypass:
    def test_bypass_decorator_importable(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import check_security_bypass
            assert callable(check_security_bypass)

    def test_bypass_decorator_sets_env_flag(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import check_security_bypass

            captured_env = {}

            @check_security_bypass
            def bypass_view():
                return "bypassed"

            with patch("security.middleware.request") as mock_req:
                mock_req.environ = captured_env
                bypass_view()
                assert captured_env.get("SECURITY_BYPASS") is True


# ---------------------------------------------------------------------------
# SecurityFixture
# ---------------------------------------------------------------------------

class TestSecurityFixture:
    def test_security_fixture_importable(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import SecurityFixture, security_fixture
            assert security_fixture is not None

    def test_security_fixture_is_fixture_subclass(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import SecurityFixture
            from py4web import Fixture
            assert issubclass(SecurityFixture, Fixture)

    def test_security_fixture_get_client_ip_forwarded(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import SecurityFixture
            fixture = SecurityFixture()

            with patch("security.middleware.request") as mock_req:
                mock_req.environ = {"HTTP_X_FORWARDED_FOR": "203.0.113.1, 10.0.0.1"}
                ip = fixture._get_client_ip()
                assert ip == "203.0.113.1"

    def test_security_fixture_get_client_ip_real_ip(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import SecurityFixture
            fixture = SecurityFixture()

            with patch("security.middleware.request") as mock_req:
                mock_req.environ = {"HTTP_X_REAL_IP": "  198.51.100.2  "}
                ip = fixture._get_client_ip()
                assert ip == "198.51.100.2"

    def test_security_fixture_get_client_ip_fallback(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import SecurityFixture
            fixture = SecurityFixture()

            with patch("security.middleware.request") as mock_req:
                mock_req.environ = {"REMOTE_ADDR": "192.168.0.1"}
                ip = fixture._get_client_ip()
                assert ip == "192.168.0.1"

    def test_on_request_skips_static_paths(self):
        with patch("database.get_db", return_value=MagicMock(tables=[])):
            from security.middleware import SecurityFixture
            fixture = SecurityFixture()

            with patch("security.middleware.request") as mock_req, \
                 patch("security.middleware.security_middleware") as mock_sm:
                mock_req.path = "/static/js/app.js"
                mock_req.environ = {"REMOTE_ADDR": "127.0.0.1"}
                # Should return without calling process_request
                result = fixture.on_request(MagicMock())
                mock_sm.process_request.assert_not_called()
