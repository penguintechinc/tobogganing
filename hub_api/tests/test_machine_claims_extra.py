"""Additional coverage for hub_api.auth.machine_claims: the dns_resolver node type.

Existing tests only cover cluster and client node types; this file covers the
dns_resolver branch (DNS_RESOLVER_SCOPES, "resolver:" subject prefix).
"""

from __future__ import annotations

from hub_api.auth.machine_claims import DNS_RESOLVER_SCOPES, build_machine_claims


def test_dns_resolver_node_gets_resolver_scopes_and_prefix() -> None:
    """dns_resolver node_type gets DNS_RESOLVER_SCOPES and a 'resolver:' sub prefix."""
    claims = build_machine_claims(
        sub_id="resolver-1",
        node_type="dns_resolver",
        tenant="tenant-a",
        iss="tobogganing",
        aud="headend",
    )

    assert claims["sub"] == "resolver:resolver-1"
    assert claims["scope"] == DNS_RESOLVER_SCOPES
    assert "dns:config:read" in claims["scope"]
    assert "ioc:read" in claims["scope"]
