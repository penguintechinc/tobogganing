"""Live-test WebSocket blueprint for WaddlePerf cluster performance testing.

Provides real-time streaming of test execution via WebSocket and optional
synchronous HTTP trigger.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, current_app, jsonify, request, websocket

from core.auth.middleware import current_claims, require_tenant
from core.db import get_db
from core.entitlements.gate import require_feature
from core.flags import feature_enabled
from core.modules.waddleperf_cluster.services.device_manager import DeviceManager
from core.modules.waddleperf_cluster.services.engine_client import EngineClient, EngineError
from core.modules.waddleperf_cluster.services.test_manager import TestManager

logger = structlog.get_logger()

blueprint = Blueprint("wpc_live_test", __name__, url_prefix="/live-test")


@dataclass(slots=True)
class StreamMessage:
    """WebSocket message structure for streaming test progress."""

    event: str
    data: dict[str, Any]

    def to_json(self) -> str:
        """Serialize message to JSON."""
        return json.dumps(asdict(self))


async def _validate_websocket_auth() -> tuple[str | None, str | None]:
    """Validate WebSocket connection via JWT Authorization header.

    Returns:
        Tuple of (tenant, claims) if valid, (None, None) otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("websocket_auth_failed_missing_bearer")
        return None, None

    token = auth_header[7:]
    key_provider = current_app.config.get("KEY_PROVIDER")
    if not key_provider:
        logger.error("websocket_auth_failed_no_key_provider")
        return None, None

    from core.auth.jwt import decode_token

    claims = decode_token(token, key_provider)
    if not claims:
        logger.warning("websocket_auth_failed_invalid_token")
        return None, None

    tenant = claims.get("tenant")
    if not tenant:
        logger.warning("websocket_auth_failed_missing_tenant_claim")
        return None, None

    return tenant, claims


async def _check_feature_flag(tenant: str) -> bool:
    """Check if live_test feature is enabled for tenant.

    Args:
        tenant: Tenant identifier

    Returns:
        True if feature enabled, False otherwise
    """
    # Check feature flag (distinct_id can be tenant for tenant-scoped flags)
    return feature_enabled("waddleperf_cluster", "live_test", distinct_id=tenant)


async def _stream_test_progress(
    ws: Any,
    engine_client: EngineClient,
    test_type: str,
    target: str,
    device_id: str,
    device_headers: dict[str, str],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Execute test on engine and stream progress to WebSocket.

    Args:
        ws: WebSocket connection
        engine_client: EngineClient instance
        test_type: Type of test (http, tcp, udp, icmp, etc.)
        target: Target host/IP for test
        device_id: Device ID for tracking
        device_headers: Device metadata headers
        params: Additional test parameters

    Returns:
        Test result dict if successful, None on error
    """
    try:
        # Send test_started event
        msg = StreamMessage(
            event="test_started",
            data={
                "test_type": test_type,
                "target": target,
                "device_id": device_id,
                "message": "Test execution started",
            },
        )
        await ws.send(msg.to_json())

        # Execute test via engine
        result = await engine_client.run_test(
            test_type=test_type,
            target=target,
            device_headers=device_headers,
            **params,
        )

        logger.info(
            "test_executed",
            test_type=test_type,
            target=target,
            device_id=device_id,
        )

        return result

    except EngineError as e:
        logger.error(
            "test_execution_failed",
            test_type=test_type,
            target=target,
            error=str(e),
        )
        msg = StreamMessage(
            event="error",
            data={"message": f"Test execution failed: {str(e)}"},
        )
        await ws.send(msg.to_json())
        return None
    except Exception as e:
        logger.error(
            "test_stream_error",
            test_type=test_type,
            error=str(e),
            exc_info=True,
        )
        msg = StreamMessage(
            event="error",
            data={"message": f"Unexpected error: {str(e)}"},
        )
        try:
            await ws.send(msg.to_json())
        except Exception:
            pass  # Connection may be closed
        return None


@blueprint.websocket("/stream")
async def live_test_stream() -> None:
    """WebSocket endpoint for real-time test streaming.

    Expects client to send:
        {
            "test_type": "http|tcp|udp|icmp|http_trace|tcp_trace|udp_trace|traceroute",
            "target": "host or IP",
            "device_id": "device-uuid",
            "params": { "port": 80, "timeout": 30, "count": 10, ... }
        }

    Streams back:
        { "event": "test_started", "data": {...} }
        { "event": "test_complete", "data": {...} }
        { "event": "error", "data": {"message": "..."} }

    Closes on:
        - Unauthenticated connect (close code 1008)
        - Feature flag disabled (close code 1008)
        - Engine error (after sending error frame)
    """
    ws = websocket.server

    # Validate auth (tenant + claims from JWT)
    tenant, claims = await _validate_websocket_auth()
    if not tenant or not claims:
        logger.warning("websocket_rejected_unauthorized")
        await ws.close(code=1008, message="Unauthorized")
        return

    # Check feature flag
    if not await _check_feature_flag(tenant):
        logger.warning("websocket_rejected_feature_disabled", tenant=tenant)
        await ws.close(code=1008, message="Feature not enabled")
        return

    logger.info("websocket_connected", tenant=tenant)

    engine_client = EngineClient()

    try:
        async for message in ws.receive():
            try:
                msg_data = json.loads(message)

                test_type = msg_data.get("test_type", "").lower()
                target = msg_data.get("target", "").strip()
                device_id = msg_data.get("device_id", "").strip()
                params = msg_data.get("params", {})

                # Validate required fields
                if not test_type or not target or not device_id:
                    error_msg = StreamMessage(
                        event="error",
                        data={"message": "Missing required fields: test_type, target, device_id"},
                    )
                    await ws.send(error_msg.to_json())
                    continue

                # Verify the device belongs to the caller's tenant (prevent
                # device spoofing — a tenant user must not run/record tests
                # for an arbitrary or unregistered device_id).
                if not await DeviceManager(get_db(), tenant).get_device(device_id):
                    await ws.send(
                        StreamMessage(
                            event="error",
                            data={"message": "Unknown device for tenant"},
                        ).to_json()
                    )
                    continue

                # Prepare device headers
                device_headers = {
                    "X-Device-ID": device_id,
                    "X-Tenant-ID": tenant,
                }

                # Execute test and stream progress
                result = await _stream_test_progress(
                    ws,
                    engine_client,
                    test_type,
                    target,
                    device_id,
                    device_headers,
                    params,
                )

                if result is None:
                    # Error already sent; continue listening
                    continue

                # Send completion event with result
                complete_msg = StreamMessage(
                    event="test_complete",
                    data={
                        "test_type": test_type,
                        "target": target,
                        "device_id": device_id,
                        "status": "success",
                        "result": result,
                    },
                )
                await ws.send(complete_msg.to_json())

                # Persist result via TestManager (non-blocking, log errors)
                try:
                    db = get_db()
                    test_manager = TestManager(db, tenant)

                    # Create test record
                    test_record = await test_manager.create_test(
                        {
                            "device_id": device_id,
                            "test_type": test_type,
                            "target": target,
                            "status": "completed",
                            "started_at": datetime.now(timezone.utc),
                            "completed_at": datetime.now(timezone.utc),
                        }
                    )

                    # Record result details
                    await test_manager.record_result(
                        test_record.id,
                        {
                            "status": "completed",
                            "test_output": json.dumps(result),
                            "completed_at": datetime.now(timezone.utc),
                        },
                    )

                    logger.info(
                        "test_result_persisted",
                        test_id=test_record.id,
                        device_id=device_id,
                        tenant=tenant,
                    )
                except Exception as e:
                    logger.error(
                        "test_result_persistence_failed",
                        error=str(e),
                        device_id=device_id,
                        tenant=tenant,
                    )
                    # Don't close connection; client got the result via stream

            except json.JSONDecodeError:
                logger.warning("websocket_invalid_json")
                error_msg = StreamMessage(
                    event="error",
                    data={"message": "Invalid JSON format"},
                )
                await ws.send(error_msg.to_json())
            except Exception as e:
                logger.error("websocket_message_error", error=str(e))
                error_msg = StreamMessage(
                    event="error",
                    data={"message": f"Message processing error: {str(e)}"},
                )
                try:
                    await ws.send(error_msg.to_json())
                except Exception:
                    pass

    except asyncio.CancelledError:
        logger.info("websocket_cancelled", tenant=tenant)
    except Exception as e:
        logger.error("websocket_error", error=str(e), exc_info=True)
        try:
            error_msg = StreamMessage(
                event="error",
                data={"message": f"WebSocket error: {str(e)}"},
            )
            await ws.send(error_msg.to_json())
        except Exception:
            pass
    finally:
        await engine_client.close()
        logger.info("websocket_closed", tenant=tenant)


@blueprint.route("/run", methods=["POST"])
@require_tenant
@require_feature("waddleperf_cluster", "live_test")
async def run_test_sync() -> tuple[dict[str, Any], int]:
    """Synchronous HTTP endpoint to run a single test.

    Requires valid JWT with tenant claim.

    Request body:
        {
            "test_type": "http|tcp|udp|icmp|...",
            "target": "host or IP",
            "device_id": "device-uuid",
            "params": { "port": 80, "timeout": 30, "count": 10, ... }
        }

    Returns:
        JSON response with test result and metadata.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims.get("tenant")
        if not tenant:
            return {"error": "Missing tenant claim"}, 403

        data = await request.get_json()

        test_type = (data.get("test_type") or "").lower()
        target = (data.get("target") or "").strip()
        device_id = (data.get("device_id") or "").strip()
        params = data.get("params") or {}

        # Validate required fields
        if not test_type or not target or not device_id:
            return (
                {
                    "error": "Missing required fields",
                    "required": ["test_type", "target", "device_id"],
                },
                400,
            )

        # Verify the device belongs to the caller's tenant (prevent spoofing).
        if not await DeviceManager(get_db(), tenant).get_device(device_id):
            return {"error": "Unknown device for tenant"}, 404

        # Prepare device headers
        device_headers = {
            "X-Device-ID": device_id,
            "X-Tenant-ID": tenant,
        }

        # Execute test
        engine_client = EngineClient()
        try:
            result = await engine_client.run_test(
                test_type=test_type,
                target=target,
                device_headers=device_headers,
                **params,
            )

            logger.info(
                "sync_test_completed",
                test_type=test_type,
                target=target,
                device_id=device_id,
                tenant=tenant,
            )

            # Persist result (non-blocking)
            try:
                db = get_db()
                test_manager = TestManager(db, tenant)

                test_record = await test_manager.create_test(
                    {
                        "device_id": device_id,
                        "test_type": test_type,
                        "target": target,
                        "status": "completed",
                        "started_at": datetime.now(timezone.utc),
                        "completed_at": datetime.now(timezone.utc),
                    }
                )

                await test_manager.record_result(
                    test_record.id,
                    {
                        "status": "completed",
                        "test_output": json.dumps(result),
                        "completed_at": datetime.now(timezone.utc),
                    },
                )
            except Exception as e:
                logger.error(
                    "sync_test_result_persistence_failed",
                    error=str(e),
                    tenant=tenant,
                )

            return (
                {
                    "data": result,
                    "meta": {
                        "version": 1,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
                200,
            )

        except EngineError as e:
            logger.error(
                "sync_test_failed",
                test_type=test_type,
                error=str(e),
                tenant=tenant,
            )
            return (
                {
                    "error": "Test execution failed",
                    "message": str(e),
                },
                503,
            )

    except Exception as e:
        logger.error("sync_test_error", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500
