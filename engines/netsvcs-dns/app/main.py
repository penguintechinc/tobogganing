"""DNS resolver service Quart application.

P3-S0: Skeleton with health checks, enrollment, and config retrieval.
"""
from __future__ import annotations

import asyncio
import os
import structlog
import logging
from datetime import datetime

from quart import Quart, jsonify, g

from app.config import Config
from app.manager_client import ManagerClient

# Basic logging setup
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()

app = Quart(__name__)

# Global state (set during startup)
manager_client: ManagerClient | None = None
config: Config | None = None
ready = False


@app.before_serving
async def startup() -> None:
    """Initialize on app startup."""
    global manager_client, config, ready

    try:
        config = Config.from_env()
        logger.info(
            "config_loaded",
            server_name=config.server_name,
            grpc_addr=config.control_plane_grpc_addr,
        )

        manager_client = ManagerClient(
            grpc_addr=config.control_plane_grpc_addr,
            tls_ca_path=config.grpc_tls_ca_path,
            insecure_dev_flag=config.grpc_insecure_dev_flag,
            cache_dir=config.config_cache_dir,
            server_name=config.server_name,
        )

        # Attempt enrollment
        enrolled = await manager_client.enroll(
            bootstrap_token=config.enrollment_bootstrap_token,
            hostname=config.hostname,
            version=config.version,
        )

        if enrolled:
            # Try to fetch current config
            cfg = await manager_client.get_config()
            if cfg:
                logger.info("startup_enrollment_complete", server_id=manager_client.server_id)
                ready = True
            else:
                logger.warning("startup_config_fetch_failed")
                ready = True  # Still mark ready; offline cache is sufficient
        else:
            logger.error("startup_enrollment_failed")
            ready = False

    except Exception as e:
        logger.error("startup_error", error=str(e))
        ready = False


@app.after_serving
async def shutdown() -> None:
    """Clean up on app shutdown."""
    global manager_client
    if manager_client:
        await manager_client.close()
    logger.info("app_shutdown")


@app.get("/healthz")
async def health() -> tuple[dict, int]:
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200


@app.get("/ready")
async def readiness() -> tuple[dict, int]:
    """Readiness check (ready after enrollment + config)."""
    if ready:
        return jsonify({"ready": True}), 200
    return jsonify({"ready": False, "reason": "not_enrolled"}), 503


@app.get("/metrics")
async def metrics() -> tuple[str, int]:
    """Prometheus metrics endpoint (stub for P3-S0)."""
    # Placeholder stub; real metrics in S2+
    return "# HELP netsvcs_dns_queries_total Total DNS queries\n# TYPE netsvcs_dns_queries_total counter\n", 200


@app.errorhandler(404)
async def not_found(e: Exception) -> tuple[dict, int]:
    """Handle 404 errors."""
    return jsonify({"error": "not_found"}), 404


@app.errorhandler(500)
async def internal_error(e: Exception) -> tuple[dict, int]:
    """Handle 500 errors."""
    logger.error("internal_error", error=str(e))
    return jsonify({"error": "internal_error"}), 500


async def main() -> None:
    """Entry point for the application."""
    logger.info("app_starting", version=os.getenv("VERSION", "0.1.0"))
    bind_host = os.getenv("BIND_HOST", "0.0.0.0")  # nosec B104 - containerized DNS service must bind all interfaces
    await app.run_task(host=bind_host, port=8080)


if __name__ == "__main__":
    asyncio.run(main())
