"""Tests for require_admin_role decorator."""
import pytest
from unittest.mock import MagicMock, patch


def test_denies_non_admin():
    """Non-admin users should be denied."""
    # Mock py4web request and abort
    mock_request = MagicMock()
    mock_request.user = {"role": "viewer"}
    mock_abort = MagicMock(side_effect=Exception("Admin role required"))

    with patch("security.middleware.request", mock_request), \
         patch("security.middleware.abort", mock_abort):
        from security.middleware import require_admin_role
        called = []

        @require_admin_role
        def handler():
            called.append(True)
            return "ok"

        with pytest.raises(Exception):
            handler()
        assert not called
        mock_abort.assert_called_once()


def test_allows_admin():
    """Admin users should be allowed."""
    # Mock py4web request and abort
    mock_request = MagicMock()
    mock_request.user = {"role": "admin"}
    mock_abort = MagicMock()

    with patch("security.middleware.request", mock_request), \
         patch("security.middleware.abort", mock_abort):
        from security.middleware import require_admin_role

        @require_admin_role
        def handler():
            return "ok"

        result = handler()
        assert result == "ok"
        mock_abort.assert_not_called()
