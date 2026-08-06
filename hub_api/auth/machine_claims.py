"""Machine-JWT claim builder for cluster/client authentication."""

from __future__ import annotations

import uuid

# Scope sets by node type (least privilege)
CLUSTER_SCOPES = "firewall:read wireguard:read ports:read metrics:write certs:issue swg:read"
CLIENT_SCOPES = "wireguard:read"


def build_machine_claims(
    sub_id: str,
    node_type: str,
    tenant: str,
    *,
    iss: str,
    aud: str = "headend",
    token_type: str = "access",
) -> dict:
    """Build claims dict for machine-JWT (cluster or client node).

    Constructs the standard claims for access and refresh tokens issued
    to authenticated clusters or clients. Does NOT include iat/exp—the
    encoder adds those based on TTL. Scopes are derived from node_type:
    clusters get full access; clients get wireguard:read only (least privilege).

    Args:
        sub_id: Subject ID (cluster.id or client.id).
        node_type: Node type (kubernetes_node, raw_compute, headend, client_docker, client_native).
        tenant: Tenant ID (from cluster.tenant or client.tenant).
        iss: Issuer claim (e.g. "tobogganing").
        aud: Audience claim, defaults to "headend".
        token_type: Token type; "access" (default) or "refresh".

    Returns:
        Claims dict with sub, iss, aud, tenant, scope, jti, and optionally token_type.
    """
    is_cluster = node_type in ("kubernetes_node", "raw_compute", "headend")
    scope = CLUSTER_SCOPES if is_cluster else CLIENT_SCOPES

    claims = {
        "sub": f"cluster:{sub_id}" if is_cluster else f"client:{sub_id}",
        "iss": iss,
        "aud": aud,
        "tenant": tenant,
        "scope": scope,
        "jti": uuid.uuid4().hex,
    }

    if token_type == "refresh":
        claims["token_type"] = "refresh"

    return claims
