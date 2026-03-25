"""Bridge between workload identity systems and OIDC hierarchy.

Maps SPIFFE IDs, cloud-native workload tokens, and other identity
sources to the Tobogganing tenant/team/scope model, and vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


@dataclass(slots=True)
class IdentityMapping:
    """Maps a workload identity to OIDC hierarchy."""
    workload_id: str
    provider_type: str  # "spiffe" | "eks_pod_identity" | "gcp_wi" | "azure_wi" | "k8s_sa"
    tenant_id: str
    team_id: str
    scopes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkloadIdentity:
    """Represents a resolved workload identity."""
    subject: str
    issuer: str
    provider_type: str
    tenant: str
    cluster: str
    namespace: str
    service: str


class IdentityBridge:
    """Bidirectional mapping between workload identity and OIDC hierarchy."""

    def workload_to_oidc(self, identity: WorkloadIdentity) -> IdentityMapping:
        """Map any workload identity to OIDC tenant/team/scopes."""
        # Try DB lookup first
        mapping = self._lookup_mapping(identity.subject, identity.provider_type)
        if mapping:
            return mapping

        # Fall back to convention-based mapping
        return self._convention_mapping(identity)

    def oidc_to_workload(
        self, tenant_id: str, team_id: str, service: str, cluster: str = "", namespace: str = "",
    ) -> WorkloadIdentity:
        """Reverse map: OIDC hierarchy -> workload identity."""
        # Build SPIFFE ID from OIDC hierarchy
        trust_domain = self._get_trust_domain(tenant_id)
        spiffe_id = f"spiffe://{trust_domain}/{cluster}/{namespace}/{service}"

        return WorkloadIdentity(
            subject=spiffe_id,
            issuer="https://hub-api.tobogganing.io",
            provider_type="spiffe",
            tenant=tenant_id,
            cluster=cluster,
            namespace=namespace,
            service=service,
        )

    def spiffe_to_oidc(self, spiffe_id: str) -> IdentityMapping:
        """Map SPIFFE ID path to tenant/team/scopes."""
        # Parse: spiffe://<trust-domain>/<cluster>/<namespace>/<service>
        parts = spiffe_id.replace("spiffe://", "").split("/")
        if len(parts) < 4:
            logger.warning("invalid_spiffe_id_format", spiffe_id=spiffe_id)
            return IdentityMapping(
                workload_id=spiffe_id,
                provider_type="spiffe",
                tenant_id="default",
                team_id="",
                scopes=["*:read"],
            )

        trust_domain = parts[0]
        tenant_id = trust_domain.split(".")[0]  # acme.tobogganing.io -> acme

        # DB lookup
        mapping = self._lookup_mapping(spiffe_id, "spiffe")
        if mapping:
            return mapping

        return IdentityMapping(
            workload_id=spiffe_id,
            provider_type="spiffe",
            tenant_id=tenant_id,
            team_id="",
            scopes=["*:read"],  # Default: read-only for unmapped workloads
        )

    def cloud_identity_to_oidc(self, cloud_token_claims: dict) -> IdentityMapping:
        """Map cloud-native identity token claims to OIDC hierarchy."""
        subject = cloud_token_claims.get("sub", "")
        issuer = cloud_token_claims.get("iss", "")

        # Detect provider type from issuer
        provider_type = self._detect_provider_type(issuer)

        # DB lookup
        mapping = self._lookup_mapping(subject, provider_type)
        if mapping:
            return mapping

        # Convention-based: extract tenant from claims or default
        tenant_id = cloud_token_claims.get("tenant", "default")

        return IdentityMapping(
            workload_id=subject,
            provider_type=provider_type,
            tenant_id=tenant_id,
            team_id="",
            scopes=["*:read"],
        )

    def _lookup_mapping(self, external_id: str, provider_type: str) -> Optional[IdentityMapping]:
        """Look up identity mapping from database."""
        try:
            from database import get_db
            db = get_db()
            row = db(
                (db.identity_mappings.external_id == external_id)
                & (db.identity_mappings.provider_type == provider_type)
            ).select().first()

            if row:
                scopes = row.scopes if isinstance(row.scopes, list) else []
                return IdentityMapping(
                    workload_id=external_id,
                    provider_type=provider_type,
                    tenant_id=row.tenant_id or "default",
                    team_id=row.team_id or "",
                    scopes=scopes,
                )
        except Exception:
            logger.warning("identity_mapping_lookup_failed", external_id=external_id)

        return None

    def _convention_mapping(self, identity: WorkloadIdentity) -> IdentityMapping:
        """Fall back to convention-based mapping when no DB entry exists."""
        return IdentityMapping(
            workload_id=identity.subject,
            provider_type=identity.provider_type,
            tenant_id=identity.tenant or "default",
            team_id="",
            scopes=["*:read"],
        )

    def _get_trust_domain(self, tenant_id: str) -> str:
        """Get SPIFFE trust domain for a tenant."""
        try:
            from database import get_db
            db = get_db()
            row = db(db.tenants.tenant_id == tenant_id).select(
                db.tenants.spiffe_trust_domain
            ).first()
            if row and row.spiffe_trust_domain:
                return row.spiffe_trust_domain
        except Exception:
            pass
        return f"{tenant_id}.tobogganing.io"

    def _detect_provider_type(self, issuer: str) -> str:
        """Detect cloud provider type from OIDC issuer URL."""
        if "eks.amazonaws.com" in issuer or "oidc.eks" in issuer:
            return "eks_pod_identity"
        if "accounts.google.com" in issuer or "googleapis.com" in issuer:
            return "gcp_wi"
        if "login.microsoftonline.com" in issuer or "sts.windows.net" in issuer:
            return "azure_wi"
        return "unknown"
