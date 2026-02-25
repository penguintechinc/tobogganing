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
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


@dataclass(slots=True)
class CiliumPolicy:
    """Intermediate representation of a CiliumNetworkPolicy manifest."""
    name: str
    namespace: str
    labels: dict[str, str] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)
    tenant_id: Optional[str] = None

    def to_manifest(self) -> dict[str, Any]:
        """Serialize to a Kubernetes CiliumNetworkPolicy manifest."""
        meta_labels: dict[str, str] = {
            "app.kubernetes.io/managed-by": "tobogganing-hub-api",
            **self.labels,
        }
        if self.tenant_id:
            meta_labels["tobogganing.io/tenant"] = self.tenant_id
        return {
            "apiVersion": "cilium.io/v2",
            "kind": "CiliumNetworkPolicy",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": meta_labels,
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
    tenant_id = getattr(policy_row, "tenant_id", None) or None
    users = policy_row.users if isinstance(getattr(policy_row, "users", None), list) else []
    groups = policy_row.groups if isinstance(getattr(policy_row, "groups", None), list) else []
    spiffe_ids = (
        policy_row.spiffe_ids
        if isinstance(getattr(policy_row, "spiffe_ids", None), list)
        else []
    )

    spec: dict[str, Any] = {
        "endpointSelector": {
            "matchLabels": {
                "app.kubernetes.io/part-of": "tobogganing",
            },
        },
    }

    # Build identity-based fromEndpoints selectors (users, groups, SPIFFE IDs)
    identity_selectors: list[dict[str, Any]] = []
    for user_id in users:
        identity_selectors.append({
            "matchLabels": {"tobogganing.io/user-id": user_id},
        })
    for group_id in groups:
        identity_selectors.append({
            "matchLabels": {"tobogganing.io/group-id": group_id},
        })
    for spiffe_id in spiffe_ids:
        identity_selectors.append({
            "matchLabels": {"tobogganing.io/spiffe-id": spiffe_id},
        })

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

        if identity_selectors:
            ingress_rule["fromEndpoints"] = identity_selectors

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
        tenant_id=tenant_id,
    )


def translate_all(policy_rows, namespace: str = "tobogganing") -> list[dict[str, Any]]:
    """Convert all applicable policy rows to CiliumNetworkPolicy manifests."""
    manifests = []
    for row in policy_rows:
        cp = translate_policy(row, namespace)
        if cp is not None:
            manifests.append(cp.to_manifest())
    return manifests


def generate_cilium_identity(spiffe_entry) -> dict[str, Any]:
    """Generate a CiliumIdentity manifest from a SPIFFE entry.

    Args:
        spiffe_entry: Object with attributes spiffe_id, tenant_id,
                      selectors (dict), and dns_names (list).

    Returns:
        A CiliumIdentity Kubernetes manifest dict.
    """
    spiffe_id: str = getattr(spiffe_entry, "spiffe_id", "")
    tenant_id: str = getattr(spiffe_entry, "tenant_id", "")
    selectors: dict = getattr(spiffe_entry, "selectors", {}) or {}
    dns_names: list = getattr(spiffe_entry, "dns_names", []) or []

    sanitized = _sanitize(spiffe_id.replace("spiffe://", "").replace("/", "-"))
    resource_name = f"identity-{sanitized}"

    identity_labels: dict[str, str] = {
        "tobogganing.io/spiffe-id": spiffe_id,
        "tobogganing.io/tenant": tenant_id,
    }
    # Merge any additional selectors from the SPIFFE entry
    for key, value in selectors.items():
        identity_labels[str(key)] = str(value)

    manifest: dict[str, Any] = {
        "apiVersion": "cilium.io/v2",
        "kind": "CiliumIdentity",
        "metadata": {
            "name": resource_name,
            "labels": identity_labels,
        },
    }

    if dns_names:
        manifest["spec"] = {"dns-names": dns_names}

    return manifest


def translate_all_with_identities(
    policy_rows,
    spiffe_entries,
    namespace: str = "tobogganing",
) -> dict[str, list[dict[str, Any]]]:
    """Translate policies and SPIFFE entries into Cilium manifests.

    Returns a dict with two keys:
      - "network_policies": list of CiliumNetworkPolicy manifests
      - "identities": list of CiliumIdentity manifests
    """
    network_policies: list[dict[str, Any]] = []
    for row in policy_rows:
        cp = translate_policy(row, namespace)
        if cp is not None:
            network_policies.append(cp.to_manifest())

    identities: list[dict[str, Any]] = []
    for entry in spiffe_entries:
        identities.append(generate_cilium_identity(entry))

    return {
        "network_policies": network_policies,
        "identities": identities,
    }


def _sanitize(name: str) -> str:
    """Sanitize a policy name for use as a Kubernetes resource name."""
    return name.lower().replace(" ", "-").replace("_", "-")[:50]
