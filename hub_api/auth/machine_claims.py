"""Machine-JWT claim builder for cluster/client authentication."""

from __future__ import annotations

import uuid

# Scope sets by node type (least privilege)
CLUSTER_SCOPES = "firewall:read wireguard:read ports:read metrics:write certs:issue swg:read"
CLIENT_SCOPES = "wireguard:read"
DNS_RESOLVER_SCOPES = "dns:config:read metrics:write ioc:read"


def build_machine_claims(
    sub_id: str,
    node_type: str,
    tenant: str,
    *,
    iss: str,
    aud: str = "headend",
    token_type: str = "access",
) -> dict:
    """Build claims dict for machine-JWT (cluster, client, or DNS resolver node).

    Constructs the standard claims for access and refresh tokens issued
    to authenticated clusters, clients, or DNS resolver nodes. Does NOT include iat/exp—the
    encoder adds those based on TTL. Scopes are derived from node_type:
    clusters get full access; clients get wireguard:read only; DNS resolvers get
    config/metrics/ioc scopes (least privilege).

    Args:
        sub_id: Subject ID (cluster.id, client.id, or resolver.id).
        node_type: Node type (kubernetes_node, raw_compute, headend, client_docker, client_native, dns_resolver).
        tenant: Tenant ID (from cluster.tenant, client.tenant, or enrollment tenant for DNS resolvers).
        iss: Issuer claim (e.g. "tobogganing").
        aud: Audience claim, defaults to "headend".
        token_type: Token type; "access" (default) or "refresh".

    Returns:
        Claims dict with sub, iss, aud, tenant, scope, jti, and optionally token_type.
    """
    is_cluster = node_type in ("kubernetes_node", "raw_compute", "headend")
    is_dns_resolver = node_type == "dns_resolver"

    if is_cluster:
        scope = CLUSTER_SCOPES
        sub_prefix = "cluster"
    elif is_dns_resolver:
        scope = DNS_RESOLVER_SCOPES
        sub_prefix = "resolver"
    else:
        scope = CLIENT_SCOPES
        sub_prefix = "client"

    claims = {
        "sub": f"{sub_prefix}:{sub_id}",
        "iss": iss,
        "aud": aud,
        "tenant": tenant,
        "scope": scope,
        "jti": uuid.uuid4().hex,
    }

    if token_type == "refresh":
        claims["token_type"] = "refresh"

    return claims
