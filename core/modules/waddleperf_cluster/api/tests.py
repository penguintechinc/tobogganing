"""WaddlePerf performance test REST API blueprint."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, jsonify, request

from core.auth.middleware import current_claims, require_scope, require_tenant
from core.db import get_db
from core.entitlements.gate import require_feature
from core.modules.waddleperf_cluster.services.device_auth import authenticate_device_global
from core.modules.waddleperf_cluster.services.test_manager import TestManager

logger = structlog.get_logger()

blueprint = Blueprint("wpc_tests", __name__, url_prefix="/tests")


# Delegation to shared device auth module
async def _authenticate_device(db: object, api_key: str) -> tuple[Any, str] | None:
    """Authenticate device using shared helper.

    Args:
        db: penguin-dal DAL instance.
        api_key: Unencrypted API key from Authorization header.

    Returns:
        Tuple of (device_record, tenant_id) if authenticated, None otherwise.
    """
    return await authenticate_device_global(db, api_key)


@blueprint.route("", methods=["POST"])
@require_tenant
@require_scope("tests:write")
@require_feature("waddleperf_cluster", "tests")
async def create_test() -> tuple[dict[str, Any], int]:
    """Create a new performance test.

    Required scope: tests:write
    Required feature: waddleperf_cluster.tests

    JSON body:
        device_id: Device identifier (required)
        test_type: Test type (required)
        target: Target URL or endpoint (optional)
        status: Test status (default: pending)
        started_at: Test start timestamp (optional)

    Returns:
        JSON response with created test and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data:
            return {"error": "Request body is required"}, 400

        if "device_id" not in data or "test_type" not in data:
            return {"error": "Missing required fields: device_id, test_type"}, 400

        db = get_db()
        mgr = TestManager(db, tenant_id)
        await mgr.initialize()

        test = await mgr.create_test(
            {
                "device_id": data["device_id"],
                "test_type": data["test_type"],
                "target": data.get("target"),
                "status": data.get("status", "pending"),
                "started_at": data.get("started_at"),
            }
        )

        logger.info(
            "test_created",
            test_id=test.id,
            device_id=test.device_id,
            test_type=test.test_type,
            tenant=tenant_id,
        )

        return (
            {
                "id": test.id,
                "device_id": test.device_id,
                "test_type": test.test_type,
                "status": test.status,
                "target": test.target,
                "created_at": test.created_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        logger.error("create_test_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("waddleperf_cluster", "tests")
async def list_tests() -> tuple[dict[str, Any], int]:
    """List all performance tests for the tenant.

    Query parameters:
        device_id: Filter by device ID (optional)
        test_type: Filter by test type (optional)
        status: Filter by status (optional)
        limit: Maximum number of results (default: 100)
        offset: Pagination offset (default: 0)

    Required scope: tests:read
    Required feature: waddleperf_cluster.tests

    Returns:
        JSON response with list of tests and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        device_id = request.args.get("device_id", None, type=str)
        test_type = request.args.get("test_type", None, type=str)
        status = request.args.get("status", None, type=str)
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        db = get_db()
        mgr = TestManager(db, tenant_id)
        await mgr.initialize()

        tests = await mgr.list_results(
            device_id=device_id,
            test_type=test_type,
            status=status,
            limit=limit,
            offset=offset,
        )

        test_list = [
            {
                "id": t.id,
                "device_id": t.device_id,
                "test_type": t.test_type,
                "status": t.status,
                "target": t.target,
                "latency_ms": t.latency_ms,
                "throughput": t.throughput,
                "created_at": t.created_at.isoformat(),
            }
            for t in tests
        ]

        logger.info(
            "tests_listed",
            count=len(test_list),
            tenant=tenant_id,
        )

        return (
            {
                "tests": test_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_tests_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<test_id>", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("waddleperf_cluster", "tests")
async def get_test(test_id: str) -> tuple[dict[str, Any], int]:
    """Get performance test details.

    Args:
        test_id: Test identifier

    Required scope: tests:read
    Required feature: waddleperf_cluster.tests

    Returns:
        JSON response with test details and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        mgr = TestManager(db, tenant_id)
        await mgr.initialize()

        test = await mgr.get_test(test_id)

        if not test:
            return {"error": "Test not found"}, 404

        logger.info(
            "test_retrieved",
            test_id=test_id,
            tenant=tenant_id,
        )

        return (
            {
                "id": test.id,
                "device_id": test.device_id,
                "test_type": test.test_type,
                "status": test.status,
                "target": test.target,
                "latency_ms": test.latency_ms,
                "throughput": test.throughput,
                "test_output": test.test_output,
                "started_at": test.started_at.isoformat() if test.started_at else None,
                "completed_at": test.completed_at.isoformat()
                if test.completed_at
                else None,
                "created_at": test.created_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_test_failed", test_id=test_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<test_id>/results", methods=["POST"])
async def record_result(test_id: str) -> tuple[dict[str, Any], int]:
    """Record performance test result (device-authenticated endpoint).

    Device authentication:
      1. Extract Bearer token from Authorization header
      2. SHA256 hash the key and query device_api_keys globally
      3. Reject if not found, revoked, or hash mismatch (401)
      4. Derive tenant and device_id from matched key record
      5. Verify result payload's device_id matches authenticated device (403 if mismatch)

    JSON body:
        device_id: Device identifier (must match authenticated device)
        status: Test status (completed, failed, etc.)
        latency_ms: Latency in milliseconds (optional)
        throughput: Throughput metric (optional)
        test_output: Test output/logs (optional)
        completed_at: Completion timestamp (optional)

    Returns:
        JSON response with updated test and meta, or error
    """
    try:
        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("result_upload_no_token")
            return {"error": "Unauthorized: API key required"}, 401

        api_key = auth_header[7:]

        # Authenticate device
        db = get_db()
        auth_result = await _authenticate_device(db, api_key)
        if not auth_result:
            logger.warning("result_upload_auth_failed")
            return {"error": "Unauthorized"}, 401

        device_obj, tenant_id = auth_result

        # Get request data
        data = await request.get_json()
        if not data:
            return {"error": "Request body is required"}, 400

        # Verify device_id in payload matches authenticated device
        payload_device_id = data.get("device_id")
        if payload_device_id != device_obj.id:
            logger.warning(
                "result_upload_device_mismatch",
                authenticated_device_id=device_obj.id,
                payload_device_id=payload_device_id,
                tenant=tenant_id,
            )
            return {"error": "Device ID mismatch"}, 403

        # Record result via TestManager (scoped to device's tenant)
        mgr = TestManager(db, tenant_id)
        await mgr.initialize()

        # IDOR check: Verify test record belongs to authenticated device and tenant
        existing = await mgr.get_test(test_id)
        if not existing:
            return {"error": "Test not found"}, 404
        if existing.device_id != device_obj.id or existing.tenant != tenant_id:
            logger.warning(
                "result_upload_test_device_mismatch",
                test_id=test_id,
                auth_device=device_obj.id,
                test_device=existing.device_id,
                tenant=tenant_id,
            )
            return {"error": "Forbidden"}, 403

        result = await mgr.record_result(
            test_id,
            {
                "status": data.get("status", "completed"),
                "latency_ms": data.get("latency_ms"),
                "throughput": data.get("throughput"),
                "test_output": data.get("test_output"),
                "completed_at": data.get("completed_at"),
            },
        )

        if not result:
            return {"error": "Test not found"}, 404

        logger.info(
            "result_recorded",
            test_id=test_id,
            device_id=device_obj.id,
            tenant=tenant_id,
        )

        return (
            {
                "id": result.id,
                "device_id": result.device_id,
                "test_type": result.test_type,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "throughput": result.throughput,
                "completed_at": result.completed_at.isoformat()
                if result.completed_at
                else None,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("record_result_failed", test_id=test_id, error=str(e))
        return {"error": "Internal server error"}, 500
