"""Workload identity abstraction — cloud-native first, SPIRE fallback.

Priority chain:
  1. Cloud-native WI (EKS Pod Identity / GCP WI / Azure WI)
  2. SPIRE (bare-metal TPM / cloud IID / K8s PSAT)
  3. K8s Service Account token (basic fallback)

All workload tokens → hub-api token exchange → uniform Tobogganing JWT.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WorkloadIdentityProvider:
    """Describes a workload identity provider available in the current environment.

    Attributes:
        provider_type: Canonical name — ``"eks"``, ``"gcp"``, ``"azure"``,
                       ``"spire"``, or ``"k8s_sa"``.
        priority:      Scheduling priority; lower value = preferred.
                       Cloud-native providers use 10–29, SPIRE uses 50,
                       K8s Service Account fallback uses 90.
        config:        Provider-specific configuration dict (OIDC issuer,
                       audience, endpoint URLs, etc.).
        is_available:  ``True`` when the provider was detected as reachable
                       in the current cluster environment.
    """

    provider_type: str
    priority: int
    config: dict
    is_available: bool


@dataclass(slots=True)
class WorkloadIdentity:
    """Normalised workload identity extracted from any cloud provider token.

    Attributes:
        subject:       SPIFFE URI, pod ARN, GCP SA email, or Azure MI object ID.
        issuer:        OIDC ``iss`` value from the validated token.
        provider_type: Which adapter produced this identity (``"eks"``, etc.).
        tenant:        Tobogganing tenant slug resolved from identity_mappings.
        cluster:       Source cluster name/ID.
        namespace:     Kubernetes namespace (empty string for non-K8s workloads).
        service:       Service account or workload name.
        raw_claims:    Full decoded JWT claims dict for downstream inspection.
    """

    subject: str
    issuer: str
    provider_type: str
    tenant: str
    cluster: str
    namespace: str
    service: str
    raw_claims: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

# Ordered list of (provider_type, priority, detector_config) entries.
# Each entry is evaluated by checking environment variables or metadata
# endpoints that indicate the cloud platform is present.
_PROVIDER_SPECS: list[tuple[str, int, dict]] = [
    (
        "eks",
        10,
        {
            "oidc_issuer_env": "AWS_CONTAINER_CREDENTIALS_FULL_URI",
            "audience": "sts.amazonaws.com",
            "description": "EKS Pod Identity via AWS OIDC",
        },
    ),
    (
        "gcp",
        20,
        {
            "project_env": "GCP_PROJECT_ID",
            "metadata_server": "http://metadata.google.internal/computeMetadata/v1/",
            "token_info_url": "https://www.googleapis.com/oauth2/v3/tokeninfo",
            "description": "GCP Workload Identity via Google OIDC",
        },
    ),
    (
        "azure",
        30,
        {
            "federated_token_file_env": "AZURE_FEDERATED_TOKEN_FILE",
            "client_id_env": "AZURE_CLIENT_ID",
            "tenant_id_env": "AZURE_TENANT_ID",
            "description": "Azure Workload Identity via Azure AD OIDC",
        },
    ),
    (
        "spire",
        50,
        {
            "socket_env": "SPIFFE_ENDPOINT_SOCKET",
            "default_socket": "unix:///run/spire/sockets/agent.sock",
            "description": "SPIRE workload API via SPIFFE mTLS",
        },
    ),
    (
        "k8s_sa",
        90,
        {
            "token_path": "/var/run/secrets/kubernetes.io/serviceaccount/token",
            "ca_path": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
            "namespace_path": "/var/run/secrets/kubernetes.io/serviceaccount/namespace",
            "description": "Kubernetes Service Account token (basic fallback)",
        },
    ),
]


def _detect_eks(config: dict) -> bool:
    """Return True when EKS Pod Identity credentials URI is present."""
    return bool(os.environ.get(config["oidc_issuer_env"]))


def _detect_gcp(config: dict) -> bool:
    """Return True when GCP_PROJECT_ID is set or GCE metadata server env hints exist."""
    if os.environ.get(config["project_env"]):
        return True
    # GKE nodes also expose GOOGLE_CLOUD_PROJECT
    if os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return True
    return False


def _detect_azure(config: dict) -> bool:
    """Return True when the Azure federated token file path is set."""
    token_file = os.environ.get(config["federated_token_file_env"])
    if not token_file:
        return False
    return os.path.isfile(token_file)


def _detect_spire(config: dict) -> bool:
    """Return True when the SPIRE agent socket is present."""
    socket_path = os.environ.get(
        config["socket_env"],
        config["default_socket"],
    )
    # Strip the unix:// scheme to get a filesystem path
    fs_path = socket_path.removeprefix("unix://")
    return os.path.exists(fs_path)


def _detect_k8s_sa(config: dict) -> bool:
    """Return True when the projected SA token file exists."""
    return os.path.isfile(config["token_path"])


_DETECTORS: dict[str, Any] = {
    "eks": _detect_eks,
    "gcp": _detect_gcp,
    "azure": _detect_azure,
    "spire": _detect_spire,
    "k8s_sa": _detect_k8s_sa,
}


def detect_available_providers(
    cluster_config: dict,
) -> list[WorkloadIdentityProvider]:
    """Detect which workload identity providers are available in this environment.

    Each provider is tested via environment variable checks and file presence
    probes (no network calls).  The returned list contains *all* known provider
    types, with ``is_available`` set accordingly.

    Priority semantics (lower = preferred):
    - Cloud-native (EKS/GCP/Azure): 10 / 20 / 30
    - SPIRE:                         50
    - K8s SA fallback:               90

    Args:
        cluster_config: Runtime cluster configuration dict that may carry
                        overrides (e.g. ``{"eks_cluster": "prod-us-east-1"}``).
                        Currently used for contextual logging; individual
                        detectors read environment variables directly.

    Returns:
        List of :class:`WorkloadIdentityProvider` instances, sorted by priority.
    """
    providers: list[WorkloadIdentityProvider] = []

    for provider_type, priority, spec_config in _PROVIDER_SPECS:
        detector = _DETECTORS.get(provider_type)
        available = detector(spec_config) if detector else False

        merged_config = {**spec_config, **cluster_config.get(provider_type, {})}
        providers.append(
            WorkloadIdentityProvider(
                provider_type=provider_type,
                priority=priority,
                config=merged_config,
                is_available=available,
            )
        )

        logger.debug(
            "workload_identity_provider_detected",
            provider_type=provider_type,
            priority=priority,
            is_available=available,
        )

    providers.sort(key=lambda p: p.priority)
    logger.info(
        "workload_identity_providers_scanned",
        available=[p.provider_type for p in providers if p.is_available],
        cluster_config_keys=list(cluster_config.keys()),
    )
    return providers


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def resolve_best_provider(
    providers: list[WorkloadIdentityProvider],
) -> WorkloadIdentityProvider | None:
    """Return the lowest-priority available provider, or ``None`` if none exist.

    Iterates the sorted provider list and returns the first entry whose
    ``is_available`` flag is ``True``.  Callers should sort the list with
    :func:`detect_available_providers` before invoking this function.

    Args:
        providers: Provider list from :func:`detect_available_providers`.

    Returns:
        Best available :class:`WorkloadIdentityProvider`, or ``None``.
    """
    for provider in providers:
        if provider.is_available:
            logger.info(
                "workload_identity_provider_selected",
                provider_type=provider.provider_type,
                priority=provider.priority,
            )
            return provider

    logger.warning("no_workload_identity_provider_available")
    return None


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

def _lookup_identity_mapping(
    provider_type: str,
    external_id: str,
    db: Any,
) -> dict | None:
    """Query identity_mappings table for tenant/team/scopes.

    Args:
        provider_type: Provider type string (e.g. ``"eks"``).
        external_id:   The subject/principal from the cloud token.
        db:            PyDAL DAL instance (runtime-only, ``migrate=False``).

    Returns:
        A dict with keys ``tenant_id``, ``team_id`` (optional), ``scopes``
        (list), or ``None`` if no mapping row is found.
    """
    if db is None:
        return None

    try:
        row = db(
            (db.identity_mappings.provider_type == provider_type)
            & (db.identity_mappings.external_id == external_id)
        ).select(
            db.identity_mappings.tenant_id,
            db.identity_mappings.team_id,
            db.identity_mappings.scopes,
        ).first()

        if row is None:
            return None

        scopes = row.scopes or []
        if isinstance(scopes, str):
            scopes = [s for s in scopes.split(" ") if s]

        return {
            "tenant_id": row.tenant_id,
            "team_id": row.team_id or "",
            "scopes": scopes,
        }

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "identity_mapping_lookup_failed",
            provider_type=provider_type,
            external_id=external_id,
            error=str(exc),
        )
        return None


def exchange_workload_token(
    source_token: str,
    provider: WorkloadIdentityProvider,
    db: Any = None,
) -> dict:
    """Validate a cloud workload token and return Tobogganing JWT claim material.

    Flow:
    1. Select the appropriate :class:`~auth.cloud_identity.CloudIdentityAdapter`
       for the provider type.
    2. Validate the source token via OIDC discovery + JWKS signature check.
    3. Look up the resolved ``subject`` in ``identity_mappings`` to obtain the
       Tobogganing tenant, team, and scope grants.
    4. Return a claim dict ready to be signed by
       :class:`~auth.jwt_manager.JWTManager`.

    Args:
        source_token: Raw bearer token from the workload (EKS OIDC, GCP STS,
                      Azure AD federated, SPIRE SVID, or raw K8s SA JWT).
        provider:     The selected :class:`WorkloadIdentityProvider`.
        db:           Optional PyDAL ``DAL`` instance for mapping resolution.
                      When ``None``, mappings fall back to empty defaults.

    Returns:
        Dict containing Tobogganing JWT claim fields::

            {
                "sub":      "<workload subject>",
                "tenant":   "<tenant slug>",
                "teams":    ["<team_id>", ...],
                "roles":    ["workload"],
                "scopes":   ["<scope>", ...],
                "provider": "<provider_type>",
                "cluster":  "<cluster>",
                "namespace":"<namespace>",
                "service":  "<service>",
            }

    Raises:
        ValueError: If the token is invalid or the adapter cannot validate it.
    """
    # Import here to avoid circular imports at module load time
    from auth.cloud_identity import (  # noqa: PLC0415
        get_adapter_for_provider,
    )

    adapter = get_adapter_for_provider(provider.provider_type)
    if adapter is None:
        raise ValueError(
            f"No cloud identity adapter registered for provider '{provider.provider_type}'"
        )

    # Validate token; raises ValueError on failure
    identity: WorkloadIdentity = adapter.validate(source_token)

    log = logger.bind(
        provider_type=provider.provider_type,
        subject=identity.subject,
        cluster=identity.cluster,
        namespace=identity.namespace,
    )
    log.info("workload_token_validated")

    # Resolve tenant/team/scopes from DB mapping
    mapping = _lookup_identity_mapping(
        provider_type=provider.provider_type,
        external_id=identity.subject,
        db=db,
    )

    if mapping:
        tenant = mapping["tenant_id"]
        team_ids = [mapping["team_id"]] if mapping.get("team_id") else []
        scopes = mapping["scopes"]
        log.info(
            "workload_identity_mapping_resolved",
            tenant=tenant,
            teams=team_ids,
            scope_count=len(scopes),
        )
    else:
        # Fallback: use identity fields directly; no tenant/team grants
        tenant = identity.tenant or "default"
        team_ids = []
        scopes = ["policies:read", "hubs:read"]
        log.warning(
            "workload_identity_mapping_not_found",
            fallback_tenant=tenant,
        )

    return {
        "sub": identity.subject,
        "tenant": tenant,
        "teams": team_ids,
        "roles": ["workload"],
        "scopes": scopes,
        "provider": provider.provider_type,
        "cluster": identity.cluster,
        "namespace": identity.namespace,
        "service": identity.service,
    }
