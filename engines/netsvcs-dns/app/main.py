"""DNS resolver service Quart application.

P3-S0: Skeleton with health checks, enrollment, and config retrieval.
P3-S2: DoH + DoT servers + resolve pipeline.
"""
from __future__ import annotations

import asyncio
import os
import structlog
import logging
from datetime import datetime

from quart import Quart, jsonify, g
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.config import Config
from app.manager_client import ManagerClient
from app.resolver import DNSResolver
from app.router import SelectiveRouter
from app.cache import CacheManager
from app.pipeline import ResolvePipeline, ResolvePipelineConfig
from app.metrics import MetricsReporter
from app.servers import doh, dot

# Basic logging setup
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()

app = Quart(__name__)

# Global state (set during startup)
manager_client: ManagerClient | None = None
config: Config | None = None
ready = False
pipeline: ResolvePipeline | None = None
dot_task: asyncio.Task | None = None
stream_config_task: asyncio.Task | None = None
heartbeat_task: asyncio.Task | None = None


@app.before_serving
async def startup() -> None:
    """Initialize on app startup."""
    global manager_client, config, ready, pipeline, dot_task, stream_config_task, heartbeat_task

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

        # S2: Initialize DNS components
        logger.info("initializing_dns_components")

        # Create cache manager
        cache = CacheManager(cache_url=config.cache_url)
        await cache.connect()

        # Create resolver, router, and pipeline
        resolver = DNSResolver()
        router = SelectiveRouter()

        # Load zones from manager config (if available)
        if manager_client.config and "zones" in manager_client.config:
            router.load_zones(manager_client.config["zones"])

        pipeline = ResolvePipeline(
            resolver=resolver,
            router=router,
            cache=cache,
            manager_client=manager_client,  # S3: Pass manager_client for gRPC calls
            config=ResolvePipelineConfig(),
        )

        # Initialize DoH routes
        doh.init_doh(app, pipeline)
        logger.info("doh_initialized")

        # S3: Start stream_config_updates background task (live resync)
        async def on_config_update(cfg: dict) -> None:
            """Handle config update from control plane stream."""
            if "zones" in cfg:
                router.load_zones(cfg["zones"])
                logger.info("config_updated_via_stream", version=cfg.get("version"))

        stream_config_task = asyncio.create_task(
            manager_client.stream_config_updates(on_update=on_config_update)
        )
        logger.info("stream_config_updates_started")

        # S3: Start heartbeat background task
        async def send_periodic_heartbeat() -> None:
            """Send heartbeat metrics to control plane periodically."""
            heartbeat_interval = 60  # seconds
            while True:
                try:
                    await asyncio.sleep(heartbeat_interval)
                    metrics = MetricsReporter.to_heartbeat_dict()
                    result = await manager_client.send_heartbeat(metrics)
                    logger.debug("heartbeat_sent", config_version=result.get("config_version"))
                except Exception as e:
                    logger.warning("heartbeat_error", error=str(e))

        heartbeat_task = asyncio.create_task(send_periodic_heartbeat())
        logger.info("heartbeat_task_started")

        # Initialize DoT listener (if TLS configured)
        if config.dot_tls_cert_path and config.dot_tls_key_path:
            dot_task = asyncio.create_task(
                dot.serve_dot(
                    pipeline,
                    port=config.dot_port,
                    cert_path=config.dot_tls_cert_path,
                    key_path=config.dot_tls_key_path,
                )
            )
            logger.info("dot_listener_started", port=config.dot_port)
        else:
            logger.warning("dot_tls_not_configured; skipping DoT listener")

    except Exception as e:
        logger.error("startup_error", error=str(e))
        ready = False


@app.after_serving
async def shutdown() -> None:
    """Clean up on app shutdown."""
    global manager_client, pipeline, dot_task, stream_config_task, heartbeat_task

    if pipeline:
        await pipeline.close()
        logger.info("pipeline_closed")

    if dot_task and not dot_task.done():
        dot_task.cancel()
        try:
            await dot_task
        except asyncio.CancelledError:
            pass
        logger.info("dot_task_cancelled")

    if stream_config_task and not stream_config_task.done():
        stream_config_task.cancel()
        try:
            await stream_config_task
        except asyncio.CancelledError:
            pass
        logger.info("stream_config_task_cancelled")

    if heartbeat_task and not heartbeat_task.done():
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        logger.info("heartbeat_task_cancelled")

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
async def metrics() -> tuple[str, int, dict]:
    """Prometheus metrics endpoint."""
    metrics_output = generate_latest()
    return metrics_output.decode('utf-8'), 200, {'Content-Type': CONTENT_TYPE_LATEST.encode('utf-8').decode('utf-8')}


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
