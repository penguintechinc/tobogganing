"""Additional coverage for app.py: create_app() error branches, the
before_serving setup_services() hook, error handlers, and main().

test_app.py covers /health and /ready; this file covers module-registration
and key-provider failure branches in create_app(), the full setup_services()
lifecycle (encryptor init, usage reporter with/without a license client,
keepalive task, exception handling), the 404/500 error handlers, and main().
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.app import create_app
from hub_api.config import Config


def _test_config() -> Config:
    return Config(db_type="sqlite", db_name=":memory:", product_name="test-app")


class TestCreateAppErrorBranches:
    """Tests for create_app()'s module-registration and key-provider error paths."""

    def test_module_registration_failure_logged_not_raised(self) -> None:
        """A module in hub_api.modules.__all__ that fails to import is skipped, not fatal."""
        import hub_api.modules

        with patch("hub_api.db.init_dal"):
            with patch.object(
                hub_api.modules, "__all__", [*hub_api.modules.__all__, "totally_bogus_module"]
            ):
                app = create_app(_test_config())

        assert app is not None
        assert "totally_bogus_module" not in app.registry.modules()  # type: ignore[attr-defined]

    def test_key_provider_configuration_failure_raises(self) -> None:
        """create_app() re-raises when build_signing_provider() fails."""
        with patch("hub_api.db.init_dal"):
            with patch("hub_api.app.build_signing_provider", side_effect=RuntimeError("kms down")):
                with pytest.raises(RuntimeError, match="kms down"):
                    create_app(_test_config())


class TestSetupServicesLifecycle:
    """Tests for the @app.before_serving setup_services() hook.

    Uses `async with app.test_app()` so Quart actually fires the ASGI
    lifespan startup event and runs the registered before_serving hook.
    """

    def _build_app_with_mock_db(self, mock_db: MagicMock) -> Quart:
        import hub_api.db

        with patch("hub_api.db.init_dal"), patch.object(hub_api.db, "get_db", return_value=mock_db):
            app = create_app(_test_config())
        import hub_api.app as app_module

        app_module.get_db = lambda: mock_db  # type: ignore[assignment]
        return app

    @pytest.mark.asyncio
    async def test_setup_services_no_license_client(self, mock_db: MagicMock) -> None:
        """setup_services() logs a warning and skips the reporter when no license client."""
        app = self._build_app_with_mock_db(mock_db)

        with patch("shared.licensing.python_client.get_client", return_value=None):
            async with app.test_app():
                pass

        assert not hasattr(app, "usage_reporter")

    @pytest.mark.asyncio
    async def test_setup_services_starts_keepalive_task(self, mock_db: MagicMock) -> None:
        """setup_services() creates a usage_reporter + background keepalive task."""
        app = self._build_app_with_mock_db(mock_db)
        fake_license_client = MagicMock()

        with patch("shared.licensing.python_client.get_client", return_value=fake_license_client):
            async with app.test_app():
                assert hasattr(app, "usage_reporter")
                assert hasattr(app, "keepalive_task")
                app.keepalive_task.cancel()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_setup_services_encryptor_failure_raises(self, mock_db: MagicMock) -> None:
        """setup_services() re-raises when building the data key provider fails.

        Quart's ASGI lifespan wraps the startup-hook exception as a
        LifespanError (message preserved) rather than letting the original
        RuntimeError propagate directly.
        """
        from quart.testing.app import LifespanError

        app = self._build_app_with_mock_db(mock_db)

        with patch("hub_api.app.build_data_key_provider", side_effect=RuntimeError("kms down")):
            with pytest.raises(LifespanError, match="kms down"):
                async with app.test_app():
                    pass

    @pytest.mark.asyncio
    async def test_setup_services_usage_reporter_init_failure_nonfatal(
        self, mock_db: MagicMock
    ) -> None:
        """A usage-reporter-init failure is logged but does not prevent startup."""
        app = self._build_app_with_mock_db(mock_db)

        with patch("shared.licensing.python_client.get_client", side_effect=RuntimeError("boom")):
            # Should not raise; startup completes despite the reporter failure.
            async with app.test_app():
                pass

        assert not hasattr(app, "usage_reporter")


@pytest.mark.asyncio
async def test_404_handler(app: Quart) -> None:
    """Requesting an undefined route returns the custom 404 JSON body."""
    client = app.test_client()
    resp = await client.get("/this-route-does-not-exist")
    assert resp.status_code == 404
    data = await resp.get_json()
    assert data["error"] == "Not Found"
    assert data["status_code"] == 404


@pytest.mark.asyncio
async def test_500_handler(app: Quart) -> None:
    """An unhandled exception in a route is caught by the custom 500 JSON handler.

    TESTING=True (set by the `app` fixture) makes Quart propagate exceptions
    by default for easier test debugging, bypassing registered error
    handlers — PROPAGATE_EXCEPTIONS must be explicitly disabled to exercise
    the handler itself.
    """
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/__test_raise")
    async def _raise() -> Any:
        raise RuntimeError("boom")

    client = app.test_client()
    resp = await client.get("/__test_raise")
    assert resp.status_code == 500
    data = await resp.get_json()
    assert data["error"] == "Internal Server Error"
    assert data["status_code"] == 500


def test_main_runs_hypercorn_serve() -> None:
    """main() constructs the app and drives it via hypercorn.asyncio.serve()."""
    import hub_api.app as app_module

    with patch("hub_api.app.create_app", return_value=MagicMock()) as mock_create_app:
        with patch("hypercorn.asyncio.serve", new=AsyncMock()):
            with patch("hypercorn.config.Config"):
                with patch("asyncio.run") as mock_run:
                    app_module.main()

    mock_create_app.assert_called_once()
    mock_run.assert_called_once()
