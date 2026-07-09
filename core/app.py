"""Main Quart application factory for Tobogganing Core."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from quart import Quart, jsonify
from quart_cors import cors

from core.config import Config, build_db_uri
from core.db import init_dal, get_db

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
    cors_origins = [
        origin.strip() for origin in config.cors_origins.split(",")
    ]
    cors(app, allow_origin=cors_origins)

    # Set DATABASE_URI for penguin-dal init_dal()
    db_uri = build_db_uri(config)
    app.config["DATABASE_URI"] = db_uri

    # Initialize penguin-dal if available (guard for tests)
    if init_dal is not None:
        init_dal(app, pool_size=config.db_pool_size)

    # Store config for later access
    app.config_obj = config  # type: ignore[attr-defined]

    @app.before_serving
    async def setup_services() -> None:
        """Initialize services after DB connection is ready."""
        if get_db is not None:
            db = get_db()
            app.db = db  # type: ignore[attr-defined]
            logger.info("Services initialized on app startup")

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    async def health_check() -> tuple[dict[str, str], int]:
        """Health check endpoint.

        Returns:
            JSON response with health status.
        """
        return {"status": "healthy"}, 200

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
