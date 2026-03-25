"""Tests for the identity bridge mapping service (auth/identity_bridge.py).

All DB interactions inside IdentityBridge are patched via ``_lookup_mapping``
and ``_get_trust_domain`` stubs so the tests remain hermetic — no live
database is required.
"""
import sys
import types
import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Minimal stubs for py4web / structlog if not already installed
# ---------------------------------------------------------------------------

if "py4web" not in sys.modules:
    _py4web = types.ModuleType("py4web")
    _py4web.request = MagicMock()
    _py4web.response = MagicMock()
    sys.modules["py4web"] = _py4web

if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = MagicMock(return_value=MagicMock())
    sys.modules["structlog"] = _structlog

if "database" not in sys.modules:
    _db_mod = types.ModuleType("database")
    _db_mod.get_db = MagicMock()
    sys.modules["database"] = _db_mod

# ---------------------------------------------------------------------------
# Module imports (after stubs)
# ---------------------------------------------------------------------------

from auth.identity_bridge import IdentityBridge, IdentityMapping, WorkloadIdentity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def bridge():
    """Return a fresh IdentityBridge with DB lookup permanently patched to None."""
    b = IdentityBridge()
    with patch.object(b, "_lookup_mapping", return_value=None):
        yield b


# ---------------------------------------------------------------------------
# TestSpiffeToOidc
# ---------------------------------------------------------------------------

class TestSpiffeToOidc:
    def test_valid_spiffe_id_extracts_tenant(self, bridge):
        mapping = bridge.spiffe_to_oidc("spiffe://acme.tobogganing.io/cluster1/backend/api")
        assert mapping.tenant_id == "acme"

    def test_valid_spiffe_id_provider_type(self, bridge):
        mapping = bridge.spiffe_to_oidc("spiffe://acme.tobogganing.io/cluster1/backend/api")
        assert mapping.provider_type == "spiffe"

    def test_valid_spiffe_id_workload_id(self, bridge):
        spiffe_id = "spiffe://acme.tobogganing.io/cluster1/backend/api"
        mapping = bridge.spiffe_to_oidc(spiffe_id)
        assert mapping.workload_id == spiffe_id

    def test_valid_spiffe_id_default_scopes(self, bridge):
        mapping = bridge.spiffe_to_oidc("spiffe://acme.tobogganing.io/cluster1/backend/api")
        # Unmapped workloads get read-only by default
        assert "*:read" in mapping.scopes

    def test_invalid_spiffe_id_too_short(self, bridge):
        # Only 3 parts after stripping scheme → falls back to "default" tenant
        mapping = bridge.spiffe_to_oidc("spiffe://bad")
        assert mapping.tenant_id == "default"

    def test_invalid_spiffe_id_provider_type_preserved(self, bridge):
        mapping = bridge.spiffe_to_oidc("spiffe://bad")
        assert mapping.provider_type == "spiffe"

    def test_db_mapping_takes_precedence(self):
        bridge = IdentityBridge()
        db_mapping = IdentityMapping(
            workload_id="spiffe://acme.tobogganing.io/c1/ns/svc",
            provider_type="spiffe",
            tenant_id="acme",
            team_id="infra",
            scopes=["*:read", "*:write"],
        )
        with patch.object(bridge, "_lookup_mapping", return_value=db_mapping):
            result = bridge.spiffe_to_oidc("spiffe://acme.tobogganing.io/c1/ns/svc")
            assert result.team_id == "infra"
            assert "*:write" in result.scopes

    def test_db_mapping_has_correct_workload_id(self):
        bridge = IdentityBridge()
        spiffe_id = "spiffe://acme.tobogganing.io/c1/ns/svc"
        db_mapping = IdentityMapping(
            workload_id=spiffe_id,
            provider_type="spiffe",
            tenant_id="acme",
            team_id="ops",
            scopes=["*:admin"],
        )
        with patch.object(bridge, "_lookup_mapping", return_value=db_mapping):
            result = bridge.spiffe_to_oidc(spiffe_id)
            assert result.workload_id == spiffe_id

    def test_tenant_extracted_from_trust_domain(self, bridge):
        # Trust domain: corp.tobogganing.io → tenant: corp
        mapping = bridge.spiffe_to_oidc("spiffe://corp.tobogganing.io/c1/ns/svc")
        assert mapping.tenant_id == "corp"

    def test_multi_subdomain_trust_domain(self, bridge):
        # Only the first label of the trust domain is used as tenant
        mapping = bridge.spiffe_to_oidc("spiffe://myorg.example.com/cluster/ns/svc")
        assert mapping.tenant_id == "myorg"


# ---------------------------------------------------------------------------
# TestCloudIdentityToOidc
# ---------------------------------------------------------------------------

class TestCloudIdentityToOidc:
    def test_eks_detection(self, bridge):
        claims = {
            "sub": "system:serviceaccount:ns:sa",
            "iss": "https://oidc.eks.us-east-1.amazonaws.com/id/abc",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.provider_type == "eks_pod_identity"

    def test_gcp_detection(self, bridge):
        claims = {
            "sub": "sa@project.iam.gserviceaccount.com",
            "iss": "https://accounts.google.com",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.provider_type == "gcp_wi"

    def test_azure_detection(self, bridge):
        claims = {
            "sub": "abc-123",
            "iss": "https://login.microsoftonline.com/tenant/v2.0",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.provider_type == "azure_wi"

    def test_unknown_provider_type(self, bridge):
        claims = {
            "sub": "some-workload",
            "iss": "https://internal-issuer.example.com",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.provider_type == "unknown"

    def test_tenant_from_claim(self, bridge):
        claims = {
            "sub": "workload-1",
            "iss": "https://accounts.google.com",
            "tenant": "myorg",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.tenant_id == "myorg"

    def test_tenant_defaults_to_default(self, bridge):
        claims = {
            "sub": "workload-1",
            "iss": "https://accounts.google.com",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.tenant_id == "default"

    def test_workload_id_is_subject(self, bridge):
        claims = {
            "sub": "my-service-account",
            "iss": "https://accounts.google.com",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.workload_id == "my-service-account"

    def test_default_scopes_read_only(self, bridge):
        claims = {
            "sub": "workload-1",
            "iss": "https://accounts.google.com",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert "*:read" in mapping.scopes

    def test_db_mapping_overrides_convention(self):
        bridge = IdentityBridge()
        db_mapping = IdentityMapping(
            workload_id="my-gcp-sa",
            provider_type="gcp_wi",
            tenant_id="gcp-org",
            team_id="platform",
            scopes=["*:write"],
        )
        with patch.object(bridge, "_lookup_mapping", return_value=db_mapping):
            claims = {
                "sub": "my-gcp-sa",
                "iss": "https://accounts.google.com",
                "tenant": "different",
            }
            result = bridge.cloud_identity_to_oidc(claims)
            assert result.team_id == "platform"
            assert result.tenant_id == "gcp-org"

    def test_eks_amazonaws_detection(self, bridge):
        claims = {
            "sub": "eks-workload",
            "iss": "https://eks.amazonaws.com/id/cluster",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.provider_type == "eks_pod_identity"

    def test_azure_sts_windows_detection(self, bridge):
        claims = {
            "sub": "azure-workload",
            "iss": "https://sts.windows.net/tenant-id/",
        }
        mapping = bridge.cloud_identity_to_oidc(claims)
        assert mapping.provider_type == "azure_wi"


# ---------------------------------------------------------------------------
# TestOidcToWorkload
# ---------------------------------------------------------------------------

class TestOidcToWorkload:
    def test_builds_spiffe_id(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_get_trust_domain", return_value="acme.tobogganing.io"):
            identity = bridge.oidc_to_workload(
                "acme", "infra", "api-server", "aws-us-east-1", "backend"
            )
            assert identity.subject == "spiffe://acme.tobogganing.io/aws-us-east-1/backend/api-server"

    def test_tenant_preserved(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_get_trust_domain", return_value="acme.tobogganing.io"):
            identity = bridge.oidc_to_workload("acme", "infra", "api-server", "cluster1", "ns")
            assert identity.tenant == "acme"

    def test_provider_type_is_spiffe(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_get_trust_domain", return_value="acme.tobogganing.io"):
            identity = bridge.oidc_to_workload("acme", "infra", "svc", "c1", "ns")
            assert identity.provider_type == "spiffe"

    def test_cluster_preserved(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_get_trust_domain", return_value="acme.tobogganing.io"):
            identity = bridge.oidc_to_workload("acme", "infra", "svc", "my-cluster", "ns")
            assert identity.cluster == "my-cluster"

    def test_namespace_preserved(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_get_trust_domain", return_value="acme.tobogganing.io"):
            identity = bridge.oidc_to_workload("acme", "infra", "svc", "c1", "prod-ns")
            assert identity.namespace == "prod-ns"

    def test_service_preserved(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_get_trust_domain", return_value="acme.tobogganing.io"):
            identity = bridge.oidc_to_workload("acme", "infra", "gateway", "c1", "ns")
            assert identity.service == "gateway"

    def test_issuer_is_hub_api(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_get_trust_domain", return_value="acme.tobogganing.io"):
            identity = bridge.oidc_to_workload("acme", "infra", "svc", "c1", "ns")
            assert "hub-api.tobogganing.io" in identity.issuer

    def test_trust_domain_fallback(self):
        """When DB has no trust domain, the convention fallback is used."""
        bridge = IdentityBridge()
        identity = bridge.oidc_to_workload("acme", "infra", "svc", "c1", "ns")
        # Convention: {tenant_id}.tobogganing.io
        assert "acme.tobogganing.io" in identity.subject


# ---------------------------------------------------------------------------
# TestWorkloadToOidc
# ---------------------------------------------------------------------------

class TestWorkloadToOidc:
    def test_convention_fallback(self, bridge):
        identity = WorkloadIdentity(
            subject="test-workload",
            issuer="https://example.com",
            provider_type="k8s_sa",
            tenant="acme",
            cluster="c1",
            namespace="ns",
            service="svc",
        )
        mapping = bridge.workload_to_oidc(identity)
        assert mapping.tenant_id == "acme"
        assert mapping.provider_type == "k8s_sa"

    def test_convention_fallback_default_tenant(self):
        bridge = IdentityBridge()
        with patch.object(bridge, "_lookup_mapping", return_value=None):
            identity = WorkloadIdentity(
                subject="test-workload",
                issuer="https://example.com",
                provider_type="k8s_sa",
                tenant="",  # empty tenant falls back to "default"
                cluster="c1",
                namespace="ns",
                service="svc",
            )
            mapping = bridge.workload_to_oidc(identity)
            assert mapping.tenant_id == "default"

    def test_db_mapping_wins(self):
        bridge = IdentityBridge()
        db_mapping = IdentityMapping(
            workload_id="test-workload",
            provider_type="k8s_sa",
            tenant_id="override-tenant",
            team_id="platform",
            scopes=["*:admin"],
        )
        with patch.object(bridge, "_lookup_mapping", return_value=db_mapping):
            identity = WorkloadIdentity(
                subject="test-workload",
                issuer="https://example.com",
                provider_type="k8s_sa",
                tenant="original-tenant",
                cluster="c1",
                namespace="ns",
                service="svc",
            )
            mapping = bridge.workload_to_oidc(identity)
            assert mapping.tenant_id == "override-tenant"
            assert mapping.team_id == "platform"

    def test_convention_workload_id_is_subject(self, bridge):
        identity = WorkloadIdentity(
            subject="my-special-workload",
            issuer="https://example.com",
            provider_type="spiffe",
            tenant="corp",
            cluster="c1",
            namespace="ns",
            service="svc",
        )
        mapping = bridge.workload_to_oidc(identity)
        assert mapping.workload_id == "my-special-workload"

    def test_convention_scopes_are_read_only(self, bridge):
        identity = WorkloadIdentity(
            subject="test",
            issuer="https://example.com",
            provider_type="k8s_sa",
            tenant="acme",
            cluster="c1",
            namespace="ns",
            service="svc",
        )
        mapping = bridge.workload_to_oidc(identity)
        assert "*:read" in mapping.scopes
        # Only read-only for convention-mapped workloads
        assert "*:write" not in mapping.scopes
        assert "*:admin" not in mapping.scopes


# ---------------------------------------------------------------------------
# TestIdentityMappingDataclass
# ---------------------------------------------------------------------------

class TestIdentityMappingDataclass:
    def test_slots_set(self):
        m = IdentityMapping(
            workload_id="w",
            provider_type="spiffe",
            tenant_id="t",
            team_id="team",
        )
        assert not hasattr(m, "__dict__")

    def test_default_scopes_empty(self):
        m = IdentityMapping(
            workload_id="w",
            provider_type="spiffe",
            tenant_id="t",
            team_id="",
        )
        assert m.scopes == []

    def test_scopes_not_shared_between_instances(self):
        m1 = IdentityMapping(workload_id="w1", provider_type="spiffe", tenant_id="t", team_id="")
        m2 = IdentityMapping(workload_id="w2", provider_type="spiffe", tenant_id="t", team_id="")
        m1.scopes.append("*:read")
        assert "*:read" not in m2.scopes


# ---------------------------------------------------------------------------
# TestWorkloadIdentityDataclass
# ---------------------------------------------------------------------------

class TestWorkloadIdentityDataclass:
    def test_slots_set(self):
        wi = WorkloadIdentity(
            subject="s", issuer="i", provider_type="spiffe",
            tenant="t", cluster="c", namespace="n", service="svc",
        )
        assert not hasattr(wi, "__dict__")

    def test_fields_accessible(self):
        wi = WorkloadIdentity(
            subject="spiffe://a/b/c/d",
            issuer="https://hub-api.tobogganing.io",
            provider_type="spiffe",
            tenant="acme",
            cluster="aws-east",
            namespace="backend",
            service="api",
        )
        assert wi.subject == "spiffe://a/b/c/d"
        assert wi.provider_type == "spiffe"
        assert wi.tenant == "acme"
        assert wi.cluster == "aws-east"
        assert wi.namespace == "backend"
        assert wi.service == "api"
