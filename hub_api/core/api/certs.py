"""Certificate management blueprint for core module."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import structlog
from quart import Blueprint, current_app, g, request

from hub_api.auth.middleware import require_machine_jwt
from hub_api.core import CertificateManager
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.sdwan.orchestrator.client_registry import ClientRegistry
from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster, ClusterManager

logger = structlog.get_logger()

blueprint = Blueprint("core_certs", __name__, url_prefix="/api/v1/certs")


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


def _sub_node_id(machine_sub: str | None, prefix: str) -> str | None:
    """Extract the node id from a machine-JWT `sub` claim of form `{prefix}:{id}`.

    Returns None for the legacy bootstrap identity (`sub == "legacy"`, no
    real per-node binding) or any subject not matching `prefix`, so callers
    can treat those as "no self-binding available" instead of crashing.

    Args:
        machine_sub: The g.machine_sub value set by require_machine_jwt.
        prefix: Expected subject prefix (e.g. "cluster").

    Returns:
        The node id portion of the subject, or None if unavailable.
    """
    if not machine_sub or machine_sub == "legacy":
        return None
    want = f"{prefix}:"
    if not machine_sub.startswith(want):
        return None
    return machine_sub[len(want) :]


def _hostname_from_headend_url(headend_url: str) -> str | None:
    """Extract a bare hostname/IP from a cluster's registered `headend_url`.

    Args:
        headend_url: The cluster's registered headend_url — typically
            "https://host[:port]", but tolerates a bare host/IP too (the
            leading "//" forces urlparse to treat it as netloc either way).

    Returns:
        The hostname/IP portion, or None if it can't be determined.
    """
    if not headend_url:
        return None
    candidate = headend_url if "//" in headend_url else f"//{headend_url}"
    return urlparse(candidate).hostname


def _cluster_san_names(cluster: Cluster) -> list[str]:
    """Derive the authorized SAN list for a headend cert from the cluster record.

    Server-derived only — request-body `san_names` are never trusted, mirroring
    `hub_api.modules.sdwan.api.wireguard.generate_wireguard_keys`, which also
    passes a server-derived value (`wg_config["ip_address"]`) rather than
    client input. A node in tenant A cannot get a fleet-CA-signed cert minted
    for `headend.tenantB.internal` this way, since the hostname comes from its
    own registered `headend_url`, not the request.

    Args:
        cluster: The caller's own Cluster record (already tenant+identity
            bound by _authorize_cert_identity).

    Returns:
        SAN list derived from the cluster's registered headend_url hostname;
        empty if no hostname can be derived (caller must fail closed on this).
    """
    hostname = _hostname_from_headend_url(cluster.headend_url)
    return [hostname] if hostname else []


async def _authorize_cert_identity(
    cert_type: str, node_id: str
) -> tuple[str | None, Cluster | None]:
    """Bind the requested certificate identity to the authenticated caller.

    Mirrors the ownership check in
    `hub_api.modules.sdwan.api.wireguard.generate_wireguard_keys`: the node
    named by `node_id` (cert CN) must exist under the caller's own tenant
    (`g.machine_tenant`), and for a real machine-JWT, must be the caller's own
    cluster (headend certs) or a client owned by the caller's own cluster
    (client certs). This closes the cross-tenant cert-issuance hole where
    `id` was taken verbatim from the request body. SANs are handled
    separately — see `_cluster_san_names`, which derives them from the
    returned Cluster record rather than trusting body `san_names`. The legacy
    bootstrap-token path (no per-node `sub`, only a shared secret — the
    documented `machine:"legacy"` debt) gets tenant+existence scoping only,
    since there is no per-node subject to bind to; it cannot name a node
    outside its enrollment tenant.

    Args:
        cert_type: "client" or "headend".
        node_id: Requested certificate CN / node identifier.

    Returns:
        Tuple of (denial reason or None if authorized, the resolved Cluster
        record for headend requests so the caller can derive SANs from it —
        always None for client requests or on denial).
    """
    machine_tenant = getattr(g, "machine_tenant", None)
    machine_sub = getattr(g, "machine_sub", None)
    if not machine_tenant:
        # require_machine_jwt always sets a tenant today (real JWT tenant
        # claim, or "default" for the legacy path) — fail closed rather than
        # issue an unbound cert if that ever stops being true.
        return "missing_tenant", None

    db = get_db()
    caller_cluster_id = _sub_node_id(machine_sub, "cluster")

    if cert_type == "headend":
        cluster = await ClusterManager(db, machine_tenant).get_cluster(node_id)
        if not cluster or str(cluster.id) != str(node_id):
            return "unknown_cluster_in_tenant", None
        # Real machine-JWT: a cluster may only request a cert for itself.
        if caller_cluster_id is not None and caller_cluster_id != node_id:
            return "subject_mismatch", None
        return None, cluster

    # cert_type == "client"
    client = await ClientRegistry(db, machine_tenant).get_client(node_id)
    if not client or str(client.id) != str(node_id):
        return "unknown_client_in_tenant", None
    # Real machine-JWT: a cluster may only mint certs for clients it manages.
    if (
        caller_cluster_id is not None
        and str(getattr(client, "cluster_id", None)) != caller_cluster_id
    ):
        return "subject_mismatch", None
    return None, None


@blueprint.route("/certificates", methods=["POST"])
@require_feature("sase", "certs")
@require_machine_jwt("certs:issue")
async def generate_certificate() -> tuple[dict[str, Any], int]:
    """Generate a signed X.509 certificate for a node.

    Requires machine-JWT with certs:issue scope (or legacy enrollment token if flag OFF).
    Used during node onboarding and cert renewal. The requested `id` (CN) is
    bound to the authenticated caller's own tenant (and, where a real
    machine-JWT subject is available, to the caller's own node) via
    `_authorize_cert_identity` — a caller cannot mint a cert naming a node in
    another tenant. Headend cert SANs are derived server-side from the
    caller's own registered cluster record (`_cluster_san_names`) — body
    `san_names` is ignored and never trusted, since SAN is what TLS/mTLS peer
    identity is actually matched on.

    Request body:
    {
        "type": "client" | "headend",
        "id": "node-id",
        "name": "node-name",
        "client_type": "docker" | "native" (for client type)
    }

    Returns:
        JSON response with certificate type and PEM-encoded cert/key/CA.
    """
    try:
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

        # regression: cross-tenant cert issuance (security-audit 2026-09-21)
        # Bind the requested CN to the authenticated caller before ever
        # touching CertificateManager — see _authorize_cert_identity docstring.
        denial_reason, cluster = await _authorize_cert_identity(cert_type, node_id)
        if denial_reason:
            logger.warning(
                "certificate_request_unauthorized",
                node_id=node_id,
                cert_type=cert_type,
                tenant=getattr(g, "machine_tenant", None),
                reason=denial_reason,
            )
            return (
                {"error": "Forbidden: certificate identity not authorized for caller"},
                403,
            )

        # regression: cross-tenant cert issuance via SAN (security-audit 2026-09-22)
        # SANs are what TLS/mTLS peer identity is actually matched on — a
        # caller legitimately owning node_id in its own tenant must not be
        # able to name an arbitrary SAN (e.g. another tenant's headend
        # hostname) via the request body. Derive them server-side instead.
        san_names: list[str] = []
        if cert_type == "headend":
            if cluster is None:
                # Unreachable in practice — _authorize_cert_identity returns
                # a Cluster for every non-denied headend request. Fail closed
                # defensively rather than assume and issue an unbound cert.
                logger.error("certificate_request_missing_cluster_record", node_id=node_id)
                return ({"error": "Internal server error"}, 500)
            san_names = _cluster_san_names(cluster)
            if not san_names:
                logger.warning(
                    "certificate_request_no_authorized_sans",
                    node_id=node_id,
                    cert_type=cert_type,
                    tenant=getattr(g, "machine_tenant", None),
                )
                return (
                    {"error": "Forbidden: no authorized SANs for this cluster"},
                    403,
                )

        # Get certificate manager from app config
        cert_manager: CertificateManager = current_app.config.get("CERT_MANAGER")
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
            # san_names computed above from the cluster's own record —
            # request-body san_names is never used (see docstring).
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
