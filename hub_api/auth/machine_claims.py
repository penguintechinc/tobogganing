"""Machine-JWT claim builder for cluster/client authentication."""

from __future__ import annotations

import uuid


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
    encoder adds those based on TTL.

    Args:
        sub_id: Subject ID (cluster.id or client.id).
        node_type: Node type (kubernetes_node, raw_compute, client_docker, etc.).
        tenant: Tenant ID (from cluster.tenant or client.tenant).
        iss: Issuer claim (e.g. "tobogganing").
        aud: Audience claim, defaults to "headend".
        token_type: Token type; "access" (default) or "refresh".

    Returns:
        Claims dict with sub, iss, aud, tenant, scope, jti, and optionally token_type.
    """
    claims = {
        "sub": f"cluster:{sub_id}" if node_type in ("kubernetes_node", "raw_compute") else f"client:{sub_id}",
        "iss": iss,
        "aud": aud,
        "tenant": tenant,
        "scope": "firewall:read wireguard:read ports:read metrics:write certs:issue",
        "jti": uuid.uuid4().hex,
    }

    if token_type == "refresh":
        claims["token_type"] = "refresh"

    return claims
