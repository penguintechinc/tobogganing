"""Cloud-native workload identity adapters for EKS, GCP, Azure.

Each adapter:
  - validate(token: str) -> WorkloadIdentity
  - is_available(cluster_config: dict) -> bool

Token validation uses OIDC discovery:
  1. Fetch ``<issuer>/.well-known/openid-configuration`` to locate the JWKS URI.
  2. Fetch the JWKS and cache public keys by ``kid``.
  3. Decode the JWT header to find the ``kid``, select the matching key.
  4. Verify signature, ``exp``, ``iss``, and ``aud``.
  5. Map claims -> :class:`~auth.workload_identity.WorkloadIdentity`.

HTTP calls are structured as TODO stubs so they can be wired to ``httpx``
in a subsequent pass without restructuring the logic skeleton.
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass, field

import structlog

from auth.workload_identity import WorkloadIdentity

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# OIDC discovery / JWKS helpers (stubs — wire to httpx in production)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OIDCDiscoveryDocument:
    """Parsed fields from ``/.well-known/openid-configuration``."""

    issuer: str
    jwks_uri: str
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class JWKSKey:
    """Single public key entry from a JWKS endpoint."""

    kid: str
    kty: str
    alg: str
    use: str
    # RSA fields
    n: str = ""
    e: str = ""
    # EC fields (for future ES256 support)
    crv: str = ""
    x: str = ""
    y: str = ""


def fetch_oidc_discovery(issuer_url: str) -> OIDCDiscoveryDocument:
    """Fetch and parse the OIDC discovery document for *issuer_url*.

    Args:
        issuer_url: OIDC issuer base URL (no trailing slash).

    Returns:
        Parsed :class:`OIDCDiscoveryDocument`.

    Raises:
        NotImplementedError: Stub — replace with httpx GET to
            ``{issuer_url}/.well-known/openid-configuration``.
    """
    # TODO: implement with httpx.get(f"{issuer_url.rstrip('/')}/.well-known/openid-configuration")
    raise NotImplementedError(
        f"fetch_oidc_discovery: stub — target: {issuer_url}/.well-known/openid-configuration"
    )


def fetch_jwks(jwks_uri: str) -> list[JWKSKey]:
    """Fetch the JSON Web Key Set from *jwks_uri*.

    Args:
        jwks_uri: URL returned by OIDC discovery ``jwks_uri`` field.

    Returns:
        List of :class:`JWKSKey` objects for signature verification.

    Raises:
        NotImplementedError: Stub — replace with httpx GET to *jwks_uri*.
    """
    # TODO: implement with httpx.get(jwks_uri) and parse response["keys"]
    raise NotImplementedError(f"fetch_jwks: stub — target: {jwks_uri}")


def verify_jwt_with_jwks(
    token: str,
    keys: list[JWKSKey],
    expected_issuer: str,
    expected_audience: str,
) -> dict:
    """Verify *token* signature against *keys* and return the decoded payload.

    Args:
        token:             Raw JWT string.
        keys:              JWKS key list from :func:`fetch_jwks`.
        expected_issuer:   ``iss`` claim the token must carry.
        expected_audience: ``aud`` claim the token must carry.

    Returns:
        Decoded payload dict.

    Raises:
        ValueError: On signature failure, expiry, or claim mismatch.
        NotImplementedError: Stub — replace with PyJWT + JWKS key reconstruction.

    Notes:
        Implementation outline::

            # 1. Get kid from header
            # 2. Match kid -> JWKSKey, reconstruct RSAPublicNumbers from n/e
            # 3. pyjwt.decode(token, public_key, algorithms=[key.alg],
            #                 audience=expected_audience, issuer=expected_issuer)
    """
    # TODO: reconstruct RSA public key from matching JWKSKey.n / .e, then
    #       call pyjwt.decode with full verification enabled.
    raise NotImplementedError("verify_jwt_with_jwks: stub — implement with PyJWT + RSAPublicNumbers")


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------

class CloudIdentityAdapter(abc.ABC):
    """Abstract base for cloud workload identity adapters."""

    @abc.abstractmethod
    def validate(self, token: str) -> WorkloadIdentity:
        """Validate *token* and return a normalised :class:`WorkloadIdentity`.

        Args:
            token: Raw bearer token from the cloud provider's OIDC stack.

        Raises:
            ValueError: On expired, invalid-signature, or malformed token.
        """

    @abc.abstractmethod
    def is_available(self, cluster_config: dict) -> bool:
        """Return ``True`` when this adapter's platform is detectable.

        Args:
            cluster_config: Runtime cluster configuration dict.
        """


# ---------------------------------------------------------------------------
# EKS Pod Identity adapter
# ---------------------------------------------------------------------------

class EKSPodIdentityAdapter(CloudIdentityAdapter):
    """Adapter for EKS Pod Identity via AWS OIDC.

    The ``sub`` claim follows: ``system:serviceaccount:<namespace>:<sa-name>``.
    Issuer pattern: ``https://oidc.eks.<region>.amazonaws.com/id/<cluster-id>``.

    Environment variable: ``AWS_CONTAINER_CREDENTIALS_FULL_URI``.
    """

    AUDIENCE = "sts.amazonaws.com"

    def is_available(self, cluster_config: dict) -> bool:
        """Return ``True`` when ``AWS_CONTAINER_CREDENTIALS_FULL_URI`` is set."""
        return bool(os.environ.get("AWS_CONTAINER_CREDENTIALS_FULL_URI"))

    def validate(self, token: str) -> WorkloadIdentity:
        """Validate an EKS OIDC token.

        Steps:
        1. Decode issuer from unverified claims.
        2. Confirm issuer contains ``eks.amazonaws.com``.
        3. TODO: fetch OIDC discovery + JWKS and call :func:`verify_jwt_with_jwks`.
        4. Map claims via :meth:`_claims_to_identity`.

        Args:
            token: EKS-projected OIDC service-account token.

        Returns:
            Normalised :class:`WorkloadIdentity`.

        Raises:
            ValueError: On validation failure.
        """
        log = logger.bind(adapter="eks")
        log.info("eks_token_validation_requested")

        try:
            import jwt as pyjwt  # noqa: PLC0415
            # TODO: replace with verify_jwt_with_jwks after wiring httpx
            claims = pyjwt.decode(token, options={"verify_signature": False})
        except Exception as exc:
            raise ValueError(f"EKSPodIdentityAdapter: decode failed: {exc}") from exc

        issuer = claims.get("iss", "")
        if "eks.amazonaws.com" not in issuer and "oidc.eks" not in issuer:
            raise ValueError(
                f"EKSPodIdentityAdapter: unexpected issuer '{issuer}'"
            )

        log.warning(
            "eks_token_signature_not_verified",
            reason="OIDC JWKS fetch not yet wired — stub path only",
        )
        return self._claims_to_identity(claims)

    def _claims_to_identity(self, claims: dict) -> WorkloadIdentity:
        """Map EKS JWT claims to :class:`WorkloadIdentity`.

        EKS ``sub``: ``system:serviceaccount:<namespace>:<sa-name>``.
        """
        subject = claims.get("sub", "")
        issuer = claims.get("iss", "")

        namespace = ""
        service = ""
        parts = subject.split(":")
        if len(parts) >= 4 and parts[0] == "system" and parts[1] == "serviceaccount":
            namespace = parts[2]
            service = parts[3]

        # Cluster ID is the last path segment of the EKS OIDC issuer URL
        cluster = issuer.rstrip("/").split("/")[-1] if "/" in issuer else ""

        logger.debug(
            "eks_claims_mapped",
            subject=subject,
            namespace=namespace,
            service=service,
            cluster=cluster,
        )
        return WorkloadIdentity(
            subject=subject,
            issuer=issuer,
            provider_type="eks",
            tenant="",  # resolved by identity_mappings lookup
            cluster=cluster,
            namespace=namespace,
            service=service,
            raw_claims=claims,
        )


# ---------------------------------------------------------------------------
# GCP Workload Identity adapter
# ---------------------------------------------------------------------------

class GCPWorkloadIdentityAdapter(CloudIdentityAdapter):
    """Adapter for GCP Workload Identity via Google OIDC.

    The ``sub`` claim is the numeric Google SA unique ID.
    The ``email`` claim carries ``<name>@<project>.iam.gserviceaccount.com``.

    Environment variables: ``GCP_PROJECT_ID`` or ``GOOGLE_CLOUD_PROJECT``.
    """

    GOOGLE_ISSUER = "https://accounts.google.com"
    TOKEN_INFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"
    OIDC_DISCOVERY_URL = "https://accounts.google.com"

    def is_available(self, cluster_config: dict) -> bool:
        """Return ``True`` when GCP project env vars are present."""
        return bool(
            os.environ.get("GCP_PROJECT_ID")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )

    def validate(self, token: str) -> WorkloadIdentity:
        """Validate a GCP OIDC token.

        Steps:
        1. Decode issuer from unverified claims.
        2. Confirm issuer contains ``accounts.google.com``.
        3. TODO: fetch Google OIDC discovery + JWKS and call
           :func:`verify_jwt_with_jwks`, or POST to :attr:`TOKEN_INFO_URL`.
        4. Map claims via :meth:`_claims_to_identity`.

        Args:
            token: GCP-issued OIDC token from GKE workload identity.

        Raises:
            ValueError: On validation failure.
        """
        log = logger.bind(adapter="gcp")
        log.info("gcp_token_validation_requested")

        try:
            import jwt as pyjwt  # noqa: PLC0415
            # TODO: replace with verify_jwt_with_jwks after wiring httpx
            claims = pyjwt.decode(token, options={"verify_signature": False})
        except Exception as exc:
            raise ValueError(f"GCPWorkloadIdentityAdapter: decode failed: {exc}") from exc

        issuer = claims.get("iss", "")
        if "accounts.google.com" not in issuer and "googleapis.com" not in issuer:
            raise ValueError(
                f"GCPWorkloadIdentityAdapter: unexpected issuer '{issuer}'"
            )

        log.warning(
            "gcp_token_signature_not_verified",
            reason="OIDC JWKS fetch not yet wired — stub path only",
        )
        return self._claims_to_identity(claims)

    def _claims_to_identity(self, claims: dict) -> WorkloadIdentity:
        """Map GCP JWT claims to :class:`WorkloadIdentity`.

        GKE may inject ``google.kubernetes_engine`` sub-claims with cluster
        and namespace info (Kubernetes 1.21+).
        """
        subject = claims.get("sub", "")
        issuer = claims.get("iss", "")
        email = claims.get("email", "")

        gke_info = claims.get("google", {})
        cluster = ""
        namespace = ""
        if isinstance(gke_info, dict):
            ke = gke_info.get("kubernetes_engine", {})
            if isinstance(ke, dict):
                cluster = ke.get("cluster_name", "")
                namespace = ke.get("namespace_name", "")

        # Project from email: <sa>@<project>.iam.gserviceaccount.com
        project = ""
        if "@" in email:
            domain = email.split("@")[1]
            if ".iam.gserviceaccount.com" in domain:
                project = domain.replace(".iam.gserviceaccount.com", "")

        service = email.split("@")[0] if "@" in email else subject

        logger.debug(
            "gcp_claims_mapped",
            subject=subject,
            project=project,
            cluster=cluster,
            namespace=namespace,
        )
        return WorkloadIdentity(
            subject=email or subject,
            issuer=issuer,
            provider_type="gcp",
            tenant=project,  # GCP project acts as tenant hint
            cluster=cluster,
            namespace=namespace,
            service=service,
            raw_claims=claims,
        )


# ---------------------------------------------------------------------------
# Azure Workload Identity adapter
# ---------------------------------------------------------------------------

class AzureWorkloadIdentityAdapter(CloudIdentityAdapter):
    """Adapter for Azure Workload Identity via Azure AD federated credentials.

    AKS projects a federated OIDC token via ``AZURE_FEDERATED_TOKEN_FILE``.
    The ``tid`` claim carries the Azure AD tenant ID; ``sub`` / ``oid`` carry
    the managed identity object ID.

    Environment variables:
      - ``AZURE_FEDERATED_TOKEN_FILE``: path to projected OIDC token file.
      - ``AZURE_CLIENT_ID``: Azure AD application (client) ID.
      - ``AZURE_TENANT_ID``: Azure AD tenant (directory) ID.
    """

    AAD_ISSUER_PREFIX = "https://login.microsoftonline.com/"

    def is_available(self, cluster_config: dict) -> bool:
        """Return ``True`` when the Azure federated token file exists."""
        token_file = os.environ.get("AZURE_FEDERATED_TOKEN_FILE", "")
        return bool(token_file) and os.path.isfile(token_file)

    def validate(self, token: str) -> WorkloadIdentity:
        """Validate an Azure Workload Identity token.

        Steps:
        1. Decode issuer from unverified claims.
        2. Confirm issuer is Azure AD or AKS cluster OIDC issuer.
        3. TODO: fetch OIDC discovery for
           ``https://login.microsoftonline.com/<tid>/v2.0`` and call
           :func:`verify_jwt_with_jwks`.
        4. Map claims via :meth:`_claims_to_identity`.

        Args:
            token: Bearer token (projected cluster token or AAD access token).

        Raises:
            ValueError: On validation failure.
        """
        log = logger.bind(adapter="azure")
        log.info("azure_token_validation_requested")

        try:
            import jwt as pyjwt  # noqa: PLC0415
            # TODO: replace with verify_jwt_with_jwks after wiring httpx
            claims = pyjwt.decode(token, options={"verify_signature": False})
        except Exception as exc:
            raise ValueError(
                f"AzureWorkloadIdentityAdapter: decode failed: {exc}"
            ) from exc

        issuer = claims.get("iss", "")
        is_aad = (
            "login.microsoftonline.com" in issuer
            or "sts.windows.net" in issuer
        )
        is_aks_projected = bool(os.environ.get("AZURE_FEDERATED_TOKEN_FILE"))

        if not is_aad and not is_aks_projected:
            raise ValueError(
                f"AzureWorkloadIdentityAdapter: unexpected issuer '{issuer}'"
            )

        log.warning(
            "azure_token_signature_not_verified",
            reason="OIDC JWKS fetch not yet wired — stub path only",
        )
        return self._claims_to_identity(claims)

    def _claims_to_identity(self, claims: dict) -> WorkloadIdentity:
        """Map Azure JWT claims to :class:`WorkloadIdentity`.

        Key claims: ``sub`` / ``oid`` (object ID), ``tid`` (AAD tenant),
        ``azp`` / ``appid`` (client ID), ``xms_mirid`` (managed identity
        resource ID with cluster/namespace path).
        """
        subject = claims.get("sub", "") or claims.get("oid", "")
        issuer = claims.get("iss", "")
        azure_tenant_id = claims.get("tid", os.environ.get("AZURE_TENANT_ID", ""))
        client_id = claims.get(
            "azp",
            claims.get("appid", os.environ.get("AZURE_CLIENT_ID", "")),
        )

        # Parse cluster + namespace from xms_mirid if present.
        # Format: /subscriptions/.../managedClusters/<cluster>/namespaces/<ns>/...
        mirid = claims.get("xms_mirid", "")
        cluster = ""
        namespace = ""
        if mirid:
            parts = mirid.split("/")
            for marker, dest in [("managedClusters", "cluster"), ("namespaces", "namespace")]:
                try:
                    idx = parts.index(marker) + 1
                    val = parts[idx] if idx < len(parts) else ""
                    if dest == "cluster":
                        cluster = val
                    else:
                        namespace = val
                except ValueError:
                    pass

        service = (
            claims.get("upn")
            or claims.get("preferred_username")
            or client_id
            or subject
        )

        logger.debug(
            "azure_claims_mapped",
            subject=subject,
            azure_tenant_id=azure_tenant_id,
            cluster=cluster,
            namespace=namespace,
        )
        return WorkloadIdentity(
            subject=subject,
            issuer=issuer,
            provider_type="azure",
            tenant=azure_tenant_id,  # Azure AD tenant ID acts as tenant hint
            cluster=cluster,
            namespace=namespace,
            service=service,
            raw_claims=claims,
        )


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

#: Mapping of provider_type -> adapter instance.
#: Extend via :func:`register_adapter` for SPIRE / K8s SA adapters.
_ADAPTER_REGISTRY: dict[str, CloudIdentityAdapter] = {
    "eks": EKSPodIdentityAdapter(),
    "gcp": GCPWorkloadIdentityAdapter(),
    "azure": AzureWorkloadIdentityAdapter(),
}


def get_adapter_for_provider(
    provider_type: str,
) -> CloudIdentityAdapter | None:
    """Return the registered adapter for *provider_type*, or ``None``.

    Args:
        provider_type: Provider type string (e.g. ``"eks"``, ``"gcp"``).

    Returns:
        Corresponding :class:`CloudIdentityAdapter`, or ``None`` if not found.
    """
    adapter = _ADAPTER_REGISTRY.get(provider_type)
    if adapter is None:
        logger.warning(
            "cloud_identity_adapter_not_found",
            provider_type=provider_type,
            registered=list(_ADAPTER_REGISTRY.keys()),
        )
    return adapter


def register_adapter(provider_type: str, adapter: CloudIdentityAdapter) -> None:
    """Register a custom adapter under *provider_type*.

    Allows SPIRE and K8s SA adapters (or test doubles) to be plugged in
    without modifying this module.

    Args:
        provider_type: Canonical provider name (must be unique in the registry).
        adapter:       Concrete :class:`CloudIdentityAdapter` instance.
    """
    if provider_type in _ADAPTER_REGISTRY:
        logger.warning(
            "cloud_identity_adapter_overwritten",
            provider_type=provider_type,
        )
    _ADAPTER_REGISTRY[provider_type] = adapter
    logger.info(
        "cloud_identity_adapter_registered",
        provider_type=provider_type,
        adapter_class=type(adapter).__name__,
    )
