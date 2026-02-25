"""Translates unified policy rules into CiliumNetworkPolicy CRDs.

Converts the canonical policy_rules from hub-api into Cilium-native
L3/L4/L7 network policies for enforcement on Kubernetes workloads.

Translation mapping:
  - domains  -> toFQDNs[].matchPattern (Cilium L7 DNS proxy)
  - ports    -> toPorts[].ports[]
  - dst_cidrs -> toCIDR[] or toCIDRSet[]
  - src_cidrs -> fromCIDR[] or fromCIDRSet[]
  - action=allow -> ingress/egress rules
  - action=deny  -> ingressDeny/egressDeny rules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CiliumPolicy:
    """Intermediate representation of a CiliumNetworkPolicy manifest."""
    name: str
    namespace: str
    labels: dict[str, str] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, Any]:
        """Serialize to a Kubernetes CiliumNetworkPolicy manifest."""
        return {
            "apiVersion": "cilium.io/v2",
            "kind": "CiliumNetworkPolicy",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "tobogganing-hub-api",
                    **self.labels,
                },
            },
            "spec": self.spec,
        }


def _parse_port(port_str: str) -> dict[str, Any]:
    """Parse a port string like '443' or '8080-8090' into a Cilium port spec."""
    if "-" in port_str:
        # Port ranges are not directly supported in CiliumNetworkPolicy;
        # expand or use the first port as approximation.
        start, end = port_str.split("-", 1)
        return {"port": start.strip(), "protocol": "TCP"}
    return {"port": port_str.strip(), "protocol": "TCP"}


def _build_l7_rules(domains: list[str]) -> list[dict[str, Any]]:
    """Build Cilium toFQDNs rules from domain patterns."""
    fqdn_rules = []
    for domain in domains:
        if domain.startswith("*."):
            fqdn_rules.append({"matchPattern": domain})
        else:
            fqdn_rules.append({"matchName": domain})
    return fqdn_rules


def translate_policy(
    policy_row,
    namespace: str = "tobogganing",
) -> CiliumPolicy | None:
    """Convert a single policy_rules row to a CiliumPolicy.

    Returns None if the policy scope excludes Kubernetes enforcement.
    """
    scope = getattr(policy_row, "scope", "both")
    if scope == "wireguard":
        return None

    name = f"policy-{policy_row.id}-{_sanitize(policy_row.name)}"
    direction = getattr(policy_row, "direction", "both")
    action = getattr(policy_row, "action", "allow")

    domains = policy_row.domains if isinstance(policy_row.domains, list) else []
    ports = policy_row.ports if isinstance(policy_row.ports, list) else []
    src_cidrs = policy_row.src_cidrs if isinstance(policy_row.src_cidrs, list) else []
    dst_cidrs = policy_row.dst_cidrs if isinstance(policy_row.dst_cidrs, list) else []
    protocol = getattr(policy_row, "protocol", "any")

    spec: dict[str, Any] = {
        "endpointSelector": {
            "matchLabels": {
                "app.kubernetes.io/part-of": "tobogganing",
            },
        },
    }

    # Build egress rules
    if direction in ("outbound", "both"):
        egress_rule: dict[str, Any] = {}

        if dst_cidrs:
            if action == "allow":
                egress_rule["toCIDR"] = dst_cidrs
            else:
                egress_rule["toCIDRSet"] = [{"cidr": c} for c in dst_cidrs]

        if domains:
            egress_rule["toFQDNs"] = _build_l7_rules(domains)

        if ports:
            port_specs = []
            for p in ports:
                ps = _parse_port(p)
                if protocol != "any":
                    ps["protocol"] = protocol.upper()
                port_specs.append(ps)
            egress_rule["toPorts"] = [{"ports": port_specs}]

        if egress_rule:
            key = "egressDeny" if action == "deny" else "egress"
            spec[key] = [egress_rule]

    # Build ingress rules
    if direction in ("inbound", "both"):
        ingress_rule: dict[str, Any] = {}

        if src_cidrs:
            if action == "allow":
                ingress_rule["fromCIDR"] = src_cidrs
            else:
                ingress_rule["fromCIDRSet"] = [{"cidr": c} for c in src_cidrs]

        if ports:
            port_specs = []
            for p in ports:
                ps = _parse_port(p)
                if protocol != "any":
                    ps["protocol"] = protocol.upper()
                port_specs.append(ps)
            ingress_rule["toPorts"] = [{"ports": port_specs}]

        if ingress_rule:
            key = "ingressDeny" if action == "deny" else "ingress"
            spec[key] = [ingress_rule]

    return CiliumPolicy(
        name=name,
        namespace=namespace,
        labels={"tobogganing.io/policy-id": str(policy_row.id)},
        spec=spec,
    )


def translate_all(policy_rows, namespace: str = "tobogganing") -> list[dict[str, Any]]:
    """Convert all applicable policy rows to CiliumNetworkPolicy manifests."""
    manifests = []
    for row in policy_rows:
        cp = translate_policy(row, namespace)
        if cp is not None:
            manifests.append(cp.to_manifest())
    return manifests


def _sanitize(name: str) -> str:
    """Sanitize a policy name for use as a Kubernetes resource name."""
    return name.lower().replace(" ", "-").replace("_", "-")[:50]
