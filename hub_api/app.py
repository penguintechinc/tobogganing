"""Main Quart application factory for Tobogganing Core."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import sqlalchemy as sa
from quart import Quart, jsonify
from quart_cors import cors

from hub_api.config import Config, build_db_uri
from hub_api.config.readiness import validate_prod_readiness
from hub_api.crypto.secrets import SecretEncryptor, set_encryptor
from hub_api.crypto.selection import build_signing_provider, build_data_key_provider
from hub_api.db import init_dal, get_db
from hub_api.registry import ModuleContext, ModuleRegistry
from hub_api.registry.contract import Entitlement

logger = logging.getLogger(__name__)


def create_app(config: Config | None = None) -> Quart:
    """Create and configure the Quart application.

    Args:
        config: Optional Config object. If None, creates a new Config instance.

    Returns:
        Configured Quart application instance.
    """
    # Initialize configuration
    if config is None:
        config = Config()

    # Create Quart app instance
    app = Quart(__name__)

    # Load configuration
    app.config["TESTING"] = False
    app.config["PRODUCT_NAME"] = config.product_name

    # Configure logging
    logging.basicConfig(level=config.log_level)

    # Configure CORS
    cors_origins = [origin.strip() for origin in config.cors_origins.split(",")]
    cors(app, allow_origin=cors_origins)

    # Register core API blueprints
    from hub_api.api.auth_routes import auth_bp
    from hub_api.api.portal_routes import portal_bp
    from hub_api.api.headend_routes import headend_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(portal_bp)
    # Headend routes: flat app-level paths for hub-router headend service
    # Registered at app level (url_prefix='/api/v1') to bypass module prefixing
    app.register_blueprint(headend_bp, url_prefix="/api/v1")

    # Set DATABASE_URI for penguin-dal init_dal()
    db_uri = build_db_uri(config)
    app.config["DATABASE_URI"] = db_uri

    # Initialize penguin-dal if available (guard for tests)
    if init_dal is not None:
        init_dal(app, pool_size=config.db_pool_size)

    # Store config for later access
    app.config_obj = config  # type: ignore[attr-defined]

    # Initialize module registry
    registry = ModuleRegistry()
    app.registry = registry  # type: ignore[attr-defined]

    # Register core-level entitlements and flags
    registry.register_entitlements(
        [Entitlement(feature="hub_api.external_kms", tier="enterprise")]
    )
    registry._flags.append("tobogganing.hub_api.external_kms")

    # Import and register modules from hub_api.modules
    import hub_api.modules

    for module_name in hub_api.modules.__all__:
        # Dynamically import the module and call its module() factory
        module_path = f"hub_api.modules.{module_name}"
        try:
            module_pkg = __import__(module_path, fromlist=["module"])
            if hasattr(module_pkg, "module"):
                contract = module_pkg.module()
                registry.register(contract)
                logger.info(f"Registered module: {module_name}")
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to register module {module_name}: {e}")

    # Build and set the signing key provider (in-app or external KMS)
    try:
        key_provider = build_signing_provider(registry)
        app.config["KEY_PROVIDER"] = key_provider
        logger.info(f"Configured key provider: {type(key_provider).__name__}")
    except Exception as e:
        logger.error(f"Failed to configure key provider: {e}")
        raise

    @app.before_serving
    async def setup_services() -> None:
        """Initialize services after DB connection is ready."""
        # Validate production readiness and emit warnings if needed (non-fatal)
        readiness_warnings = validate_prod_readiness(
            {
                "env": config.env,
                "hub_router_count": config.hub_router_count,
            }
        )
        for warning in readiness_warnings:
            logger.warning(warning)

        if get_db is not None:
            db = get_db()
            app.db = db  # type: ignore[attr-defined]
            # Apply registry to app with the module context
            ctx = ModuleContext(
                config=config, db=db, key_provider=app.config.get("KEY_PROVIDER")
            )
            registry.apply_to(app, ctx)

            # Initialize the global encryptor from the selected data key provider
            try:
                data_key_provider = build_data_key_provider(registry)
                encryptor = SecretEncryptor(data_key_provider.get_data_key())
                set_encryptor(encryptor)
                logger.info(
                    f"Initialized encryptor: {type(data_key_provider).__name__}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize encryptor: {e}")
                raise

            # Initialize usage reporter for license keepalive
            try:
                from hub_api.entitlements.metering import (
                    UsageReporter,
                    count_registered_nodes,
                )
                from shared.licensing.python_client import get_client

                license_client = get_client()
                if license_client is not None:
                    # Create reporter with real node counter
                    reporter = UsageReporter(
                        db=db,
                        license_client=license_client,
                        node_counter=lambda: count_registered_nodes(db),
                    )
                    app.usage_reporter = reporter  # type: ignore[attr-defined]

                    # Schedule hourly keepalive task
                    async def hourly_keepalive() -> None:
                        """Send usage report to license server hourly (best-effort)."""
                        while True:
                            try:
                                await asyncio.sleep(3600)  # 1 hour
                                success = await reporter.report()
                                if not success:
                                    logger.warning(
                                        "Usage report failed (will retry in 1h)"
                                    )
                            except asyncio.CancelledError:
                                logger.info("Hourly keepalive task cancelled")
                                break
                            except Exception as e:
                                logger.error(f"Unexpected error in keepalive task: {e}")

                    # Start the keepalive task in background (never await it here)
                    app.keepalive_task = asyncio.create_task(hourly_keepalive())  # type: ignore[attr-defined]
                    logger.info("Usage reporter initialized with hourly keepalive")
                else:
                    logger.warning(
                        "License client not available; usage reporting disabled"
                    )
            except Exception as e:
                logger.error(f"Failed to initialize usage reporter: {e}")
                # Non-fatal; continue startup

            logger.info("Services initialized on app startup")

    # Liveness probe endpoint (lightweight, no dependencies)
    @app.route("/health", methods=["GET"])
    async def health_check() -> tuple[dict[str, str], int]:
        """Liveness probe endpoint. Returns 200 if process is running.

        Does not check external dependencies; only verifies the process is up.

        Returns:
            JSON response with health status and status code.
            200 always (process-only check).
        """
        return {"status": "healthy"}, 200

    # Readiness probe endpoint (with database check)
    @app.route("/ready", methods=["GET"])
    async def readiness_check() -> tuple[dict[str, str | int], int]:
        """Readiness probe endpoint with database connectivity check.

        Returns 200 if process is up and database is reachable, 503 if DB check fails.

        Returns:
            JSON response with readiness status and status code.
            200 if ready, 503 if database check fails.
        """
        try:
            db = get_db()
            if db is not None and hasattr(db, "connection"):
                # Try to execute a simple query to check DB connectivity
                def check_db() -> None:
                    db.connection.execute(sa.text("SELECT 1"))

                await asyncio.to_thread(check_db)
            return {"status": "healthy"}, 200
        except Exception as e:
            logger.error(f"Readiness check failed: {str(e)}")
            return {"status": "unhealthy", "error": "database"}, 503

    # Error handlers
    @app.errorhandler(404)
    async def not_found(error: Exception) -> tuple[dict[str, str | int], int]:
        """Handle 404 Not Found errors."""
        return {
            "error": "Not Found",
            "message": "The requested resource was not found",
            "status_code": 404,
        }, 404

    @app.errorhandler(500)
    async def internal_error(error: Exception) -> tuple[dict[str, str | int], int]:
        """Handle 500 Internal Server errors."""
        logger.error(f"Internal server error: {str(error)}")
        return {
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
            "status_code": 500,
        }, 500

    logger.info("Quart application created successfully")

    return app


# Module-level app instance for production deployment
app = create_app()


def main() -> None:
    """Run the application with hypercorn."""
    import hypercorn.asyncio
    import hypercorn.config

    config = Config()
    dev_app = create_app(config)

    hypercorn_cfg: hypercorn.config.Config = hypercorn.config.Config(  # type: ignore[call-arg]
        bind="0.0.0.0:5000",
    )

    asyncio.run(hypercorn.asyncio.serve(dev_app, hypercorn_cfg))


if __name__ == "__main__":
    main()
