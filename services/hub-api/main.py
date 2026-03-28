"""Tobogganing Hub API - Central management service built on Quart."""

import asyncio
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from quart import Quart, jsonify, request
import structlog

from database import initialize_database, close_database
from orchestrator.cluster_manager import ClusterManager
from orchestrator.client_registry import ClientRegistry
from certs.certificate_manager import CertificateManager
from auth.jwt_manager import JWTManager
from auth.user_manager import UserManager
from metrics.prometheus import manager_metrics
from config.sal_loader import load_secrets, get_secret

logger = structlog.get_logger()

# Read version from project root .version file
VERSION_FILE = Path(__file__).resolve().parent / ".." / ".." / ".version"
try:
    SERVICE_VERSION = VERSION_FILE.read_text().strip()
except FileNotFoundError:
    SERVICE_VERSION = "unknown"

BUILD_EPOCH = SERVICE_VERSION.split(".")[-1] if "." in SERVICE_VERSION else "0"

# Global service instances
cluster_manager: Optional[ClusterManager] = None
client_registry: Optional[ClientRegistry] = None
cert_manager: Optional[CertificateManager] = None
jwt_manager: Optional[JWTManager] = None
user_manager: Optional[UserManager] = None

# Thread pool for CPU-intensive operations
thread_pool = ThreadPoolExecutor(max_workers=int(os.getenv("THREAD_POOL_SIZE", "10")))

# Background task references
_background_tasks: list[asyncio.Task] = []


def _json_response(data: dict, status: int = 200, meta: Optional[dict] = None) -> tuple:
    """Standard JSON response format for all API responses."""
    response_body = {
        "status": "success" if status < 400 else "error",
        "data": data,
        "meta": {
            "version": SERVICE_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(meta or {}),
        },
    }
    return jsonify(response_body), status


def _error_response(message: str, status: int = 500) -> tuple:
    """Standard error response format."""
    return _json_response({"message": message}, status=status)


def create_app() -> Quart:
    """Create and configure the Quart application."""
    app = Quart(__name__)

    app.config["SERVICE_NAME"] = "Tobogganing Hub API"
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")

    # Register blueprints
    from api.routes import api_bp

    app.register_blueprint(api_bp)

    # --- Lifespan events ---

    @app.before_serving
    async def startup() -> None:
        global cluster_manager, client_registry, cert_manager, jwt_manager, user_manager

        logger.info("Starting Tobogganing Hub API Service")

        # Load secrets first — other services depend on them.
        # Reads from K8s Secrets (when K8S_NAMESPACE is set) or env vars.
        logger.info("Loading secrets via penguin-sal")
        load_secrets()

        # Wire loaded secrets back into the environment so downstream code
        # that still uses os.getenv() continues to work unchanged.
        import os as _os
        for _secret_key in ("JWT_SECRET_KEY", "DB_PASS", "REDIS_PASSWORD"):
            _val = get_secret(_secret_key)
            if _val:
                _os.environ.setdefault(_secret_key, _val)

        # Initialize database first — registers penguin-dal AsyncDB on app
        logger.info("Initializing penguin-dal (AsyncDB) database connection")
        initialize_database(app)

        # Initialize core services
        cluster_manager = ClusterManager()
        client_registry = ClientRegistry()
        cert_manager = CertificateManager()
        jwt_manager = JWTManager(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            token_expiry_hours=int(os.getenv("TOKEN_EXPIRY_HOURS", "24")),
            refresh_expiry_days=int(os.getenv("REFRESH_EXPIRY_DAYS", "7")),
        )
        user_manager = UserManager()

        # Initialize all services concurrently
        await asyncio.gather(
            cluster_manager.initialize(),
            client_registry.initialize(),
            cert_manager.initialize(),
            jwt_manager.initialize(),
        )

        # Inject service references into the app for blueprint access
        app.config["cluster_manager"] = cluster_manager
        app.config["client_registry"] = client_registry
        app.config["cert_manager"] = cert_manager
        app.config["jwt_manager"] = jwt_manager
        app.config["user_manager"] = user_manager

        # Start background tasks
        _background_tasks.extend(
            [
                asyncio.create_task(cluster_manager.monitor_health()),
                asyncio.create_task(client_registry.cleanup_expired()),
                asyncio.create_task(jwt_manager.cleanup_expired_tokens()),
                asyncio.create_task(user_manager.cleanup_expired_sessions()),
                asyncio.create_task(_periodic_health_check()),
                asyncio.create_task(_periodic_metrics_update()),
            ]
        )

        logger.info("Tobogganing Hub API Service started successfully")

    @app.after_serving
    async def shutdown() -> None:
        logger.info("Shutting down Tobogganing Hub API Service")

        # Cancel background tasks
        for task in _background_tasks:
            task.cancel()

        # Shutdown services concurrently
        if cluster_manager and client_registry and cert_manager and jwt_manager:
            await asyncio.gather(
                cluster_manager.shutdown(),
                client_registry.shutdown(),
                cert_manager.shutdown(),
                jwt_manager.close(),
                return_exceptions=True,
            )

        # Close database connections
        await close_database()

        # Shutdown thread pool
        thread_pool.shutdown(wait=True)

        logger.info("Tobogganing Hub API Service shutdown complete")

    # --- Core routes (not behind /api/v1) ---

    @app.route("/")
    async def index():
        return _json_response(
            {
                "service": "Tobogganing Hub API",
                "version": SERVICE_VERSION,
                "status": "healthy",
                "clusters": (
                    await cluster_manager.get_cluster_count() if cluster_manager else 0
                ),
                "clients": (
                    await client_registry.get_client_count() if client_registry else 0
                ),
            }
        )

    @app.route("/health")
    async def health():
        health_status = {
            "manager": "healthy",
            "cluster_manager": (
                "healthy"
                if cluster_manager and await cluster_manager.is_healthy()
                else "unhealthy"
            ),
            "client_registry": (
                "healthy"
                if client_registry and await client_registry.is_healthy()
                else "unhealthy"
            ),
            "certificate_manager": (
                "healthy"
                if cert_manager and await cert_manager.is_healthy()
                else "unhealthy"
            ),
            "jwt_manager": "healthy" if jwt_manager else "unhealthy",
        }

        overall_healthy = all(v == "healthy" for v in health_status.values())
        status_code = 200 if overall_healthy else 503

        return _json_response(health_status, status=status_code)

    @app.route("/healthz")
    async def healthz():
        """Kubernetes-style liveness probe."""
        try:
            # Minimal check - if the app responds, it is alive
            return _json_response({"status": "ok"})
        except Exception:
            return _error_response("unhealthy", status=503)

    @app.route("/metrics")
    async def metrics():
        """Prometheus metrics endpoint with authentication."""
        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            metrics_token = os.getenv("METRICS_TOKEN", "prometheus-scraper-token")
            provided_token = auth_header[7:]

            if provided_token != metrics_token:
                return _error_response("Unauthorized", status=401)
        else:
            return _error_response("Unauthorized", status=401)

        from quart import Response

        return Response(
            manager_metrics.get_metrics(),
            status=200,
            content_type=manager_metrics.get_content_type(),
        )

    @app.route("/api/v1/status")
    async def api_status():
        """Return service version and build epoch."""
        return _json_response(
            {
                "service": "Tobogganing Hub API",
                "version": SERVICE_VERSION,
                "build_epoch": BUILD_EPOCH,
            }
        )

    # --- Error handlers ---

    @app.errorhandler(400)
    async def bad_request(error):
        return _error_response("Bad request", status=400)

    @app.errorhandler(401)
    async def unauthorized(error):
        return _error_response("Unauthorized", status=401)

    @app.errorhandler(403)
    async def forbidden(error):
        return _error_response("Forbidden", status=403)

    @app.errorhandler(404)
    async def not_found(error):
        return _error_response("Not found", status=404)

    @app.errorhandler(500)
    async def internal_error(error):
        logger.error("Internal server error", error=str(error))
        return _error_response("Internal server error", status=500)

    return app


async def _periodic_health_check() -> None:
    """Background task for periodic health monitoring."""
    while True:
        try:
            await asyncio.sleep(30)

            if cluster_manager and client_registry and cert_manager and jwt_manager:
                active_clusters = await cluster_manager.get_cluster_count()
                active_clients = await client_registry.get_client_count()

                logger.info(
                    "Health check",
                    clusters=active_clusters,
                    clients=active_clients,
                    threads_active=threading.active_count(),
                )

        except asyncio.CancelledError:
            logger.info("Health check task cancelled")
            break
        except Exception as e:
            logger.error("Health check failed", error=str(e))


async def _periodic_metrics_update() -> None:
    """Background task for updating Prometheus metrics."""
    while True:
        try:
            await asyncio.sleep(60)

            if cluster_manager and client_registry:
                # Cluster stats
                clusters = await cluster_manager.get_all_clusters()
                cluster_count = len(clusters)
                cluster_status_counts: dict[str, int] = {}
                for cluster in clusters:
                    status = cluster.status
                    cluster_status_counts[status] = cluster_status_counts.get(status, 0) + 1

                manager_metrics.update_cluster_stats(cluster_count, cluster_status_counts)

                # Client stats
                clients = await client_registry.get_all_clients()
                client_count = len(clients)
                client_type_counts: dict[str, int] = {}
                client_status_counts: dict[str, int] = {}
                for client in clients:
                    client_type = client.type
                    client_status = client.status
                    client_type_counts[client_type] = (
                        client_type_counts.get(client_type, 0) + 1
                    )
                    client_status_counts[client_status] = (
                        client_status_counts.get(client_status, 0) + 1
                    )

                manager_metrics.update_client_stats(
                    client_count, client_type_counts, client_status_counts
                )

            # Update system resources
            try:
                import psutil

                memory = psutil.virtual_memory()
                cpu_percent = psutil.cpu_percent(interval=1)
                manager_metrics.update_system_resources(memory.used, cpu_percent)
            except ImportError:
                pass

        except asyncio.CancelledError:
            logger.info("Metrics update task cancelled")
            break
        except Exception as e:
            logger.error("Metrics update failed", error=str(e))


async def run_in_thread(func, *args, **kwargs):
    """Run CPU-intensive operations in thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(thread_pool, func, *args)


app = create_app()

if __name__ == "__main__":
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    config = Config()
    config.bind = [f"0.0.0.0:{os.getenv('PORT', '8080')}"]
    config.workers = int(os.getenv("WORKERS", "4"))
    config.loglevel = os.getenv("LOG_LEVEL", "info").lower()
    config.accesslog = "-"

    asyncio.run(serve(app, config))
