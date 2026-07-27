"""Certificate management blueprint for SASE module."""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, current_app, request

from hub_api.core import CertificateManager
from hub_api.entitlements.gate import require_feature

logger = structlog.get_logger()

blueprint = Blueprint("sase_certs", __name__, url_prefix="/certs")


@dataclass(slots=True)
class CertificateRequest:
    """Request to generate a certificate."""

    cert_type: str
    node_id: str
    name: str
    client_type: str | None = None
    san_names: list[str] | None = None


def _extract_bearer_token(auth_header: str | None) -> str | None:
    """Extract bearer token from Authorization header.

    Args:
        auth_header: Authorization header value.

    Returns:
        Token string if valid Bearer header found, else None.
    """
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def _verify_enrollment_token(token: str | None) -> bool:
    """Constant-time verification of enrollment/bootstrap token.

    Args:
        token: Token to verify.

    Returns:
        True if token matches ENROLLMENT_BOOTSTRAP_TOKEN (constant-time),
        False otherwise or if env var is unset.
    """
    expected = os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


@blueprint.route("/certificates", methods=["POST"])
@require_feature("sase", "certs")
async def generate_certificate() -> tuple[dict[str, Any], int]:
    """Generate a signed X.509 certificate for a node.

    Phase-0 endpoint: requires enrollment token (bootstrap token),
    not a tenant JWT. Used during node onboarding.

    Request body:
    {
        "type": "client" | "headend",
        "id": "node-id",
        "name": "node-name",
        "client_type": "docker" | "native" (for client type),
        "san_names": ["dns1", "dns2"] (for headend type)
    }

    Returns:
        JSON response with certificate type and PEM-encoded cert/key/CA.
    """
    try:
        # Verify enrollment token (Phase-0 gating - not a tenant JWT)
        auth_header = request.headers.get("Authorization")
        enrollment_token = _extract_bearer_token(auth_header)

        if not _verify_enrollment_token(enrollment_token):
            logger.warning(
                "certificate_generation_unauthorized",
                reason="invalid_enrollment_token",
            )
            return (
                {"error": "Unauthorized: enrollment token required"},
                401,
            )

        # Parse request body
        data = await request.get_json()

        cert_type = data.get("type", "client")
        if cert_type not in ("client", "headend"):
            return (
                {"error": "Invalid certificate type"},
                400,
            )

        node_id = data.get("id", "")
        name = data.get("name", "")
        if not node_id or not name:
            return (
                {"error": "Missing required fields: id, name"},
                400,
            )

        # Get certificate manager from app config
        cert_manager: CertificateManager = current_app.config.get(
            "CERT_MANAGER"
        )
        if not cert_manager:
            logger.error("certificate_manager_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        # Generate certificate based on type
        if cert_type == "client":
            client_type = data.get("client_type", "native")
            try:
                key, cert, ca = await cert_manager.generate_client_certificate(
                    node_id, name, client_type
                )
            except Exception as e:
                logger.error(
                    "certificate_generation_failed",
                    node_id=node_id,
                    cert_type=cert_type,
                    error=str(e),
                )
                return (
                    {"error": "Failed to generate certificate"},
                    500,
                )
        elif cert_type == "headend":
            san_names = data.get("san_names", [])
            if not isinstance(san_names, list):
                san_names = []
            try:
                key, cert, ca = await cert_manager.generate_headend_certificate(
                    node_id, name, san_names
                )
            except Exception as e:
                logger.error(
                    "certificate_generation_failed",
                    node_id=node_id,
                    cert_type=cert_type,
                    error=str(e),
                )
                return (
                    {"error": "Failed to generate certificate"},
                    500,
                )

        logger.info(
            "certificate_generated",
            node_id=node_id,
            cert_type=cert_type,
        )

        return (
            {
                "type": cert_type,
                "certificates": {
                    "key": key,
                    "cert": cert,
                    "ca": ca,
                },
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except ValueError as e:
        logger.error("certificate_request_validation_failed", error=str(e))
        return (
            {"error": f"Invalid request: {str(e)}"},
            400,
        )
    except Exception as e:
        logger.error("certificate_generation_error", error=str(e), exc_info=True)
        return (
            {"error": "Internal server error"},
            500,
        )
