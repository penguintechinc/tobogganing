"""Main Quart application factory for Tobogganing Core."""

from __future__ import annotations

import asyncio
import logging
import os

import sqlalchemy as sa
from quart import Quart, Response
from quart_cors import cors
from quart_schema import QuartSchema

from hub_api.cache import CacheClient
from hub_api.config import Config, build_db_uri
from hub_api.config.readiness import validate_prod_readiness
from hub_api.crypto.secrets import SecretEncryptor, set_encryptor
from hub_api.crypto.selection import build_data_key_provider, build_signing_provider
from hub_api.db import get_db, init_dal
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

    # Cap request body size (this is a JSON API; no file uploads). Prevents
    # unbounded-body memory/DoS on any endpoint that calls request.get_json().
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MiB

    # Initialize QuartSchema for OpenAPI spec generation (disable auto-mounted routes)
    # We implement custom /openapi.json (auth-gated) and /docs/public (login-only)
    from quart_schema import HttpSecurityScheme

    QuartSchema(
        app,
        openapi_path=None,
        swagger_ui_path=None,
        redoc_ui_path=None,
        scalar_ui_path=None,
        security_schemes={
            "BearerAuth": HttpSecurityScheme(
                scheme="bearer",
                bearer_format="JWT",
            )
        },
    )

    # Configure logging
    logging.basicConfig(level=config.log_level)

    # Configure CORS. allow_credentials=True is required for the browser
    # cookie-based auth flow (HttpOnly access/refresh/CSRF cookies set by
    # /api/v1/auth/login and /refresh-token) — the browser will not send or
    # accept cookies on a cross-origin fetch/XHR without it, and per the CORS
    # spec this must never be paired with a wildcard origin (cors_origins is
    # a concrete allowlist, never "*").
    cors_origins = [origin.strip() for origin in config.cors_origins.split(",")]
    cors(app, allow_origin=cors_origins, allow_credentials=True)

    # Register core API blueprints
    from hub_api.api.auth_routes import auth_bp
    from hub_api.api.headend_routes import headend_bp
    from hub_api.api.portal_routes import portal_bp
    from hub_api.core.api import certs_blueprint, jwt_blueprint

    app.register_blueprint(auth_bp)
    app.register_blueprint(portal_bp)
    # Headend routes: flat app-level paths for hub-router headend service
    # Registered at app level (url_prefix='/api/v1') to bypass module prefixing
    app.register_blueprint(headend_bp, url_prefix="/api/v1")
    # Core API blueprints: certificate and JWT management
    # Registered directly (blueprints define their own full /api/v1/* prefixes)
    app.register_blueprint(certs_blueprint)
    app.register_blueprint(jwt_blueprint)

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
    registry.register_entitlements([Entitlement(feature="hub_api.external_kms", tier="enterprise")])
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

    # Initialize cache client from environment variables
    app.config["CACHE"] = CacheClient(
        host=os.getenv("CACHE_HOST", "localhost"),
        port=int(os.getenv("CACHE_PORT", "6379")),
        db=int(os.getenv("CACHE_DB", "0")),
        user=os.getenv("CACHE_USER"),
        password=os.getenv("CACHE_PASS"),
    )

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
            ctx = ModuleContext(config=config, db=db, key_provider=app.config.get("KEY_PROVIDER"))
            registry.apply_to(app, ctx)

            # Initialize the global encryptor from the selected data key provider
            try:
                data_key_provider = build_data_key_provider(registry)
                encryptor = SecretEncryptor(data_key_provider.get_data_key())
                set_encryptor(encryptor)
                logger.info(f"Initialized encryptor: {type(data_key_provider).__name__}")
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
                                    logger.warning("Usage report failed (will retry in 1h)")
                            except asyncio.CancelledError:
                                logger.info("Hourly keepalive task cancelled")
                                break
                            except Exception as e:
                                logger.error(f"Unexpected error in keepalive task: {e}")

                    # Start the keepalive task in background (never await it here)
                    app.keepalive_task = asyncio.create_task(hourly_keepalive())  # type: ignore[attr-defined]
                    logger.info("Usage reporter initialized with hourly keepalive")
                else:
                    logger.warning("License client not available; usage reporting disabled")
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

    # OpenAPI spec routes (two-document split for security)
    @app.route("/docs/public", methods=["GET"])
    async def public_docs() -> tuple[dict, int]:
        """Public OpenAPI documentation with login endpoint only.

        Accessible without authentication. Exposes only the login/token endpoints
        to allow unauthenticated clients to discover how to authenticate.
        """
        public_spec = {
            "openapi": "3.1.0",
            "info": {
                "title": app.config.get("PRODUCT_NAME", "Hub API"),
                "version": "1.0.0",
                "description": (
                    "Public login documentation. For full API docs, "
                    "authenticate and access /docs/full"
                ),
            },
            "paths": {
                "/api/v1/auth/login": {
                    "post": {
                        "summary": "Login with email and password",
                        "operationId": "loginUser",
                        "tags": ["Authentication"],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "email": {
                                                "type": "string",
                                                "format": "email",
                                                "description": "User email address",
                                            },
                                            "password": {
                                                "type": "string",
                                                "format": "password",
                                                "description": "User password",
                                            },
                                            "mfa_token": {
                                                "type": "string",
                                                "description": (
                                                    "Optional MFA token if MFA is enabled"
                                                ),
                                            },
                                        },
                                        "required": ["email", "password"],
                                    }
                                }
                            },
                        },
                        "responses": {
                            "200": {
                                "description": "Login successful or MFA required",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "oneOf": [
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "access_token": {"type": "string"},
                                                        "refresh_token": {"type": "string"},
                                                        "expires_in": {"type": "integer"},
                                                        "token_type": {
                                                            "type": "string",
                                                            "enum": ["Bearer"],
                                                        },
                                                    },
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "mfa_required": {
                                                            "type": "boolean",
                                                            "const": True,
                                                        },
                                                    },
                                                },
                                            ]
                                        }
                                    }
                                },
                            },
                            "401": {
                                "description": "Invalid credentials",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "error": {"type": "string"},
                                            },
                                        }
                                    }
                                },
                            },
                        },
                    }
                },
            },
            "components": {
                "securitySchemes": {
                    "BearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                    }
                }
            },
        }
        return public_spec, 200

    @app.route("/openapi.json", methods=["GET"])
    async def full_openapi_spec() -> tuple[dict | tuple, int]:
        """Full OpenAPI specification for authenticated users only.

        Returns 401 if the request does not include a valid JWT token.
        Exposes the complete API surface, schemas, and security requirements.
        """
        from hub_api.auth.middleware import _validate_and_store_token

        # Validate authentication token
        token_valid = await _validate_and_store_token()
        if not token_valid:
            error_resp = {"error": "Unauthorized: missing or invalid token"}
            return error_resp, 401

        # For now, return a placeholder full spec.
        # In production, this would be generated via quart-schema or auto-generated.
        full_spec = {
            "openapi": "3.1.0",
            "info": {
                "title": app.config.get("PRODUCT_NAME", "Hub API"),
                "version": "1.0.0",
                "description": (
                    "Complete Hub API specification. Includes all endpoints, "
                    "schemas, and authentication requirements."
                ),
            },
            "servers": [
                {"url": "https://hub.penguintech.io", "description": "Production"},
                {"url": "http://localhost:5000", "description": "Local development"},
            ],
            "paths": {
                "/api/v1/auth/login": {
                    "post": {
                        "summary": "Login with email and password",
                        "operationId": "loginUser",
                        "tags": ["Authentication"],
                        "security": [],  # No auth required for login
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "email": {
                                                "type": "string",
                                                "format": "email",
                                            },
                                            "password": {
                                                "type": "string",
                                                "format": "password",
                                            },
                                            "mfa_token": {
                                                "type": "string",
                                            },
                                        },
                                        "required": ["email", "password"],
                                    }
                                }
                            },
                        },
                        "responses": {
                            "200": {"description": "Login successful or MFA required"},
                            "401": {"description": "Invalid credentials"},
                        },
                    }
                },
                "/api/v1/auth/refresh-token": {
                    "post": {
                        "summary": "Refresh access token",
                        "operationId": "refreshToken",
                        "tags": ["Authentication"],
                        "security": [],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "refresh_token": {"type": "string"},
                                        },
                                        "required": ["refresh_token"],
                                    }
                                }
                            },
                        },
                        "responses": {
                            "200": {"description": "Token refreshed successfully"},
                            "401": {"description": "Invalid or expired refresh token"},
                        },
                    }
                },
                "/api/v1/auth/logout": {
                    "post": {
                        "summary": "Logout and revoke tokens",
                        "operationId": "logoutUser",
                        "tags": ["Authentication"],
                        "security": [],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "refresh_token": {"type": "string"},
                                        },
                                        "required": ["refresh_token"],
                                    }
                                }
                            },
                        },
                        "responses": {
                            "204": {"description": "Logout successful"},
                        },
                    }
                },
                "/health": {
                    "get": {
                        "summary": "Liveness probe",
                        "operationId": "healthCheck",
                        "tags": ["Health"],
                        "security": [],
                        "responses": {
                            "200": {
                                "description": "Service is healthy",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "status": {"type": "string", "enum": ["healthy"]},
                                            },
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
                "/ready": {
                    "get": {
                        "summary": "Readiness probe",
                        "operationId": "readinessCheck",
                        "tags": ["Health"],
                        "security": [],
                        "responses": {
                            "200": {
                                "description": "Service is ready",
                            },
                            "503": {
                                "description": "Service is not ready",
                            },
                        },
                    }
                },
            },
            "components": {
                "securitySchemes": {
                    "BearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                        "description": "JWT access token obtained from /api/v1/auth/login",
                    }
                }
            },
            "security": [{"BearerAuth": []}],
        }
        return full_spec, 200

    # Security headers on every response. This is a JSON API (no HTML
    # rendering), so the CSP is intentionally maximally restrictive.
    @app.after_request
    async def set_security_headers(response: Response) -> Response:
        """Attach baseline security headers to every response.

        Args:
            response: The outgoing Quart response.

        Returns:
            The same response with security headers set.
        """
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

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
