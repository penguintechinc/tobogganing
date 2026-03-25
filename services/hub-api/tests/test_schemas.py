"""Tests for all Pydantic API schemas in hub-api."""
import pytest
from pydantic import ValidationError

from api.schemas.auth import LoginRequest, TokenExchangeRequest, TokenRequest
from api.schemas.client import ClientRegisterRequest, ClientUpdateRequest
from api.schemas.cluster import ClusterRegisterRequest, ClusterUpdateRequest
from api.schemas.identity import SpiffeEntryRequest, TeamCreateRequest, TenantCreateRequest
from api.schemas.network import PortConfigRequest, VRFCreateRequest
from api.schemas.perf import PerfMetricQuery, PerfMetricSubmission
from api.schemas.policy import PolicyRuleCreateRequest, PolicyRuleUpdateRequest


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------


class TestTokenRequest:
    def test_valid_kubernetes_node(self):
        obj = TokenRequest.model_validate(
            {"node_id": "node-1", "node_type": "kubernetes_node", "api_key": "secret"}
        )
        assert obj.node_id == "node-1"
        assert obj.node_type == "kubernetes_node"
        assert obj.api_key == "secret"

    def test_valid_raw_compute(self):
        obj = TokenRequest.model_validate(
            {"node_id": "n2", "node_type": "raw_compute", "api_key": "k"}
        )
        assert obj.node_type == "raw_compute"

    def test_valid_client_docker(self):
        obj = TokenRequest.model_validate(
            {"node_id": "d1", "node_type": "client_docker", "api_key": "k"}
        )
        assert obj.node_type == "client_docker"

    def test_valid_client_native(self):
        obj = TokenRequest.model_validate(
            {"node_id": "n1", "node_type": "client_native", "api_key": "k"}
        )
        assert obj.node_type == "client_native"

    def test_invalid_node_type(self):
        with pytest.raises(ValidationError):
            TokenRequest.model_validate(
                {"node_id": "n1", "node_type": "virtual_machine", "api_key": "k"}
            )

    def test_missing_node_id(self):
        with pytest.raises(ValidationError):
            TokenRequest.model_validate({"node_type": "raw_compute", "api_key": "k"})

    def test_missing_api_key(self):
        with pytest.raises(ValidationError):
            TokenRequest.model_validate(
                {"node_id": "n1", "node_type": "raw_compute"}
            )

    def test_missing_node_type(self):
        with pytest.raises(ValidationError):
            TokenRequest.model_validate({"node_id": "n1", "api_key": "k"})

    def test_strict_mode_rejects_int_node_id(self):
        with pytest.raises(ValidationError):
            TokenRequest.model_validate(
                {"node_id": 42, "node_type": "raw_compute", "api_key": "k"}
            )

    def test_expected_fields(self):
        fields = set(TokenRequest.model_fields.keys())
        assert fields == {"node_id", "node_type", "api_key"}


class TestLoginRequest:
    def test_valid(self):
        obj = LoginRequest.model_validate({"username": "admin", "password": "s3cr3t"})
        assert obj.username == "admin"
        assert obj.password == "s3cr3t"

    def test_missing_username(self):
        with pytest.raises(ValidationError):
            LoginRequest.model_validate({"password": "s3cr3t"})

    def test_missing_password(self):
        with pytest.raises(ValidationError):
            LoginRequest.model_validate({"username": "admin"})

    def test_strict_mode_rejects_int_username(self):
        with pytest.raises(ValidationError):
            LoginRequest.model_validate({"username": 1, "password": "x"})

    def test_expected_fields(self):
        fields = set(LoginRequest.model_fields.keys())
        assert fields == {"username", "password"}


class TestTokenExchangeRequest:
    def test_valid_minimal(self):
        obj = TokenExchangeRequest.model_validate(
            {"token": "jwt.token.here", "provider": "oidc"}
        )
        assert obj.token == "jwt.token.here"
        assert obj.provider == "oidc"
        assert obj.tenant_id is None

    def test_valid_with_tenant(self):
        obj = TokenExchangeRequest.model_validate(
            {"token": "tok", "provider": "saml", "tenant_id": "acme"}
        )
        assert obj.tenant_id == "acme"

    def test_missing_token(self):
        with pytest.raises(ValidationError):
            TokenExchangeRequest.model_validate({"provider": "oidc"})

    def test_missing_provider(self):
        with pytest.raises(ValidationError):
            TokenExchangeRequest.model_validate({"token": "tok"})

    def test_expected_fields(self):
        fields = set(TokenExchangeRequest.model_fields.keys())
        assert fields == {"token", "provider", "tenant_id"}


# ---------------------------------------------------------------------------
# Client schemas
# ---------------------------------------------------------------------------


class TestClientRegisterRequest:
    def test_valid_native(self):
        obj = ClientRegisterRequest.model_validate(
            {"name": "laptop-1", "type": "native", "public_key": "abc123"}
        )
        assert obj.type == "native"
        assert obj.location is None

    def test_valid_docker_with_location(self):
        obj = ClientRegisterRequest.model_validate(
            {
                "name": "container-1",
                "type": "docker",
                "public_key": "abc123",
                "location": {"city": "NYC", "lat": 40.7},
            }
        )
        assert obj.location == {"city": "NYC", "lat": 40.7}

    def test_valid_mobile(self):
        obj = ClientRegisterRequest.model_validate(
            {"name": "phone", "type": "mobile", "public_key": "pk"}
        )
        assert obj.type == "mobile"

    def test_valid_client_native(self):
        obj = ClientRegisterRequest.model_validate(
            {"name": "c", "type": "client_native", "public_key": "pk"}
        )
        assert obj.type == "client_native"

    def test_valid_client_docker(self):
        obj = ClientRegisterRequest.model_validate(
            {"name": "c", "type": "client_docker", "public_key": "pk"}
        )
        assert obj.type == "client_docker"

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            ClientRegisterRequest.model_validate(
                {"name": "c", "type": "vm", "public_key": "pk"}
            )

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            ClientRegisterRequest.model_validate(
                {"type": "native", "public_key": "pk"}
            )

    def test_missing_public_key(self):
        with pytest.raises(ValidationError):
            ClientRegisterRequest.model_validate({"name": "c", "type": "native"})

    def test_strict_mode_rejects_int_name(self):
        with pytest.raises(ValidationError):
            ClientRegisterRequest.model_validate(
                {"name": 99, "type": "native", "public_key": "pk"}
            )

    def test_expected_fields(self):
        fields = set(ClientRegisterRequest.model_fields.keys())
        assert fields == {"name", "type", "public_key", "location"}


class TestClientUpdateRequest:
    def test_all_optional_defaults_to_none(self):
        obj = ClientUpdateRequest.model_validate({})
        assert obj.name is None
        assert obj.tunnel_mode is None
        assert obj.split_tunnel_routes is None

    def test_valid_full_tunnel(self):
        obj = ClientUpdateRequest.model_validate({"tunnel_mode": "full"})
        assert obj.tunnel_mode == "full"

    def test_valid_split_tunnel(self):
        obj = ClientUpdateRequest.model_validate(
            {"tunnel_mode": "split", "split_tunnel_routes": ["10.0.0.0/8"]}
        )
        assert obj.tunnel_mode == "split"
        assert obj.split_tunnel_routes == ["10.0.0.0/8"]

    def test_invalid_tunnel_mode(self):
        with pytest.raises(ValidationError):
            ClientUpdateRequest.model_validate({"tunnel_mode": "vpn-only"})

    def test_expected_fields(self):
        fields = set(ClientUpdateRequest.model_fields.keys())
        assert fields == {"name", "tunnel_mode", "split_tunnel_routes"}


# ---------------------------------------------------------------------------
# Cluster schemas
# ---------------------------------------------------------------------------


class TestClusterRegisterRequest:
    def test_valid(self):
        obj = ClusterRegisterRequest.model_validate(
            {
                "name": "us-east-1",
                "region": "us-east",
                "datacenter": "dc1",
                "headend_url": "https://hub.example.com",
            }
        )
        assert obj.name == "us-east-1"
        assert obj.headend_url == "https://hub.example.com"

    def test_valid_http_url(self):
        obj = ClusterRegisterRequest.model_validate(
            {
                "name": "c",
                "region": "r",
                "datacenter": "d",
                "headend_url": "http://internal.lan",
            }
        )
        assert obj.headend_url == "http://internal.lan"

    def test_invalid_url_no_scheme(self):
        with pytest.raises(ValidationError):
            ClusterRegisterRequest.model_validate(
                {
                    "name": "c",
                    "region": "r",
                    "datacenter": "d",
                    "headend_url": "hub.example.com",
                }
            )

    def test_invalid_url_ftp_scheme(self):
        with pytest.raises(ValidationError):
            ClusterRegisterRequest.model_validate(
                {
                    "name": "c",
                    "region": "r",
                    "datacenter": "d",
                    "headend_url": "ftp://hub.example.com",
                }
            )

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            ClusterRegisterRequest.model_validate(
                {"region": "r", "datacenter": "d", "headend_url": "https://x.com"}
            )

    def test_missing_headend_url(self):
        with pytest.raises(ValidationError):
            ClusterRegisterRequest.model_validate(
                {"name": "c", "region": "r", "datacenter": "d"}
            )

    def test_strict_mode_rejects_int_region(self):
        with pytest.raises(ValidationError):
            ClusterRegisterRequest.model_validate(
                {
                    "name": "c",
                    "region": 1,
                    "datacenter": "d",
                    "headend_url": "https://x.com",
                }
            )

    def test_expected_fields(self):
        fields = set(ClusterRegisterRequest.model_fields.keys())
        assert fields == {"name", "region", "datacenter", "headend_url"}


class TestClusterUpdateRequest:
    def test_all_optional_defaults_to_none(self):
        obj = ClusterUpdateRequest.model_validate({})
        assert obj.name is None
        assert obj.status is None

    def test_valid_active_status(self):
        obj = ClusterUpdateRequest.model_validate({"status": "active"})
        assert obj.status == "active"

    def test_valid_inactive_status(self):
        obj = ClusterUpdateRequest.model_validate({"status": "inactive"})
        assert obj.status == "inactive"

    def test_valid_maintenance_status(self):
        obj = ClusterUpdateRequest.model_validate({"status": "maintenance"})
        assert obj.status == "maintenance"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ClusterUpdateRequest.model_validate({"status": "degraded"})

    def test_expected_fields(self):
        fields = set(ClusterUpdateRequest.model_fields.keys())
        assert fields == {"name", "region", "datacenter", "status"}


# ---------------------------------------------------------------------------
# Identity schemas
# ---------------------------------------------------------------------------


class TestTenantCreateRequest:
    def test_valid_minimal(self):
        obj = TenantCreateRequest.model_validate(
            {"tenant_id": "acme", "name": "Acme Corp"}
        )
        assert obj.tenant_id == "acme"
        assert obj.name == "Acme Corp"
        assert obj.domain is None
        assert obj.spiffe_trust_domain is None
        assert obj.config is None

    def test_valid_full(self):
        obj = TenantCreateRequest.model_validate(
            {
                "tenant_id": "acme",
                "name": "Acme Corp",
                "domain": "acme.com",
                "spiffe_trust_domain": "acme.com",
                "config": {"max_users": 100},
            }
        )
        assert obj.domain == "acme.com"
        assert obj.config == {"max_users": 100}

    def test_missing_tenant_id(self):
        with pytest.raises(ValidationError):
            TenantCreateRequest.model_validate({"name": "Acme"})

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            TenantCreateRequest.model_validate({"tenant_id": "acme"})

    def test_expected_fields(self):
        fields = set(TenantCreateRequest.model_fields.keys())
        assert fields == {"tenant_id", "name", "domain", "spiffe_trust_domain", "config"}


class TestTeamCreateRequest:
    def test_valid_minimal(self):
        obj = TeamCreateRequest.model_validate(
            {"team_id": "eng", "tenant_id": "acme", "name": "Engineering"}
        )
        assert obj.team_id == "eng"
        assert obj.description is None

    def test_valid_with_description(self):
        obj = TeamCreateRequest.model_validate(
            {
                "team_id": "eng",
                "tenant_id": "acme",
                "name": "Engineering",
                "description": "Core eng team",
            }
        )
        assert obj.description == "Core eng team"

    def test_missing_team_id(self):
        with pytest.raises(ValidationError):
            TeamCreateRequest.model_validate({"tenant_id": "acme", "name": "Eng"})

    def test_missing_tenant_id(self):
        with pytest.raises(ValidationError):
            TeamCreateRequest.model_validate({"team_id": "eng", "name": "Eng"})

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            TeamCreateRequest.model_validate({"team_id": "eng", "tenant_id": "acme"})

    def test_expected_fields(self):
        fields = set(TeamCreateRequest.model_fields.keys())
        assert fields == {"team_id", "tenant_id", "name", "description"}


class TestSpiffeEntryRequest:
    def test_valid_minimal(self):
        obj = SpiffeEntryRequest.model_validate(
            {"spiffe_id": "spiffe://acme.com/svc", "tenant_id": "acme"}
        )
        assert obj.spiffe_id == "spiffe://acme.com/svc"
        assert obj.ttl == 0
        assert obj.parent_id is None
        assert obj.selectors is None
        assert obj.dns_names is None

    def test_valid_full(self):
        obj = SpiffeEntryRequest.model_validate(
            {
                "spiffe_id": "spiffe://acme.com/svc",
                "tenant_id": "acme",
                "parent_id": "spiffe://acme.com",
                "selectors": {"k8s:ns": "default"},
                "ttl": 3600,
                "dns_names": ["svc.acme.com"],
            }
        )
        assert obj.ttl == 3600
        assert obj.dns_names == ["svc.acme.com"]

    def test_default_ttl_zero(self):
        obj = SpiffeEntryRequest.model_validate(
            {"spiffe_id": "spiffe://x/y", "tenant_id": "t"}
        )
        assert obj.ttl == 0

    def test_missing_spiffe_id(self):
        with pytest.raises(ValidationError):
            SpiffeEntryRequest.model_validate({"tenant_id": "acme"})

    def test_missing_tenant_id(self):
        with pytest.raises(ValidationError):
            SpiffeEntryRequest.model_validate({"spiffe_id": "spiffe://x/y"})

    def test_strict_mode_rejects_string_ttl(self):
        with pytest.raises(ValidationError):
            SpiffeEntryRequest.model_validate(
                {"spiffe_id": "spiffe://x/y", "tenant_id": "t", "ttl": "3600"}
            )

    def test_expected_fields(self):
        fields = set(SpiffeEntryRequest.model_fields.keys())
        assert fields == {
            "spiffe_id", "tenant_id", "parent_id", "selectors", "ttl", "dns_names"
        }


# ---------------------------------------------------------------------------
# Network schemas
# ---------------------------------------------------------------------------


class TestVRFCreateRequest:
    def test_valid_minimal(self):
        obj = VRFCreateRequest.model_validate({"name": "vrf-blue", "rd": "65001:10"})
        assert obj.name == "vrf-blue"
        assert obj.rd == "65001:10"
        assert obj.area_type == "ospf"
        assert obj.ip_ranges is None
        assert obj.area_id is None

    def test_valid_bgp(self):
        obj = VRFCreateRequest.model_validate(
            {"name": "vrf-red", "rd": "65001:20", "area_type": "bgp"}
        )
        assert obj.area_type == "bgp"

    def test_valid_static(self):
        obj = VRFCreateRequest.model_validate(
            {"name": "vrf-green", "rd": "65001:30", "area_type": "static"}
        )
        assert obj.area_type == "static"

    def test_invalid_area_type(self):
        with pytest.raises(ValidationError):
            VRFCreateRequest.model_validate(
                {"name": "v", "rd": "65001:1", "area_type": "rip"}
            )

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            VRFCreateRequest.model_validate({"rd": "65001:1"})

    def test_missing_rd(self):
        with pytest.raises(ValidationError):
            VRFCreateRequest.model_validate({"name": "v"})

    def test_with_ip_ranges(self):
        obj = VRFCreateRequest.model_validate(
            {
                "name": "vrf-blue",
                "rd": "65001:10",
                "ip_ranges": ["10.0.0.0/8", "172.16.0.0/12"],
            }
        )
        assert obj.ip_ranges == ["10.0.0.0/8", "172.16.0.0/12"]

    def test_expected_fields(self):
        fields = set(VRFCreateRequest.model_fields.keys())
        assert fields == {"name", "rd", "ip_ranges", "area_type", "area_id"}


class TestPortConfigRequest:
    def test_valid_minimal(self):
        obj = PortConfigRequest.model_validate(
            {"headend_id": "hub-1", "cluster_id": 5}
        )
        assert obj.headend_id == "hub-1"
        assert obj.cluster_id == 5
        assert obj.tcp_ranges is None
        assert obj.udp_ranges is None

    def test_valid_with_ranges(self):
        obj = PortConfigRequest.model_validate(
            {
                "headend_id": "hub-1",
                "cluster_id": 5,
                "tcp_ranges": "8000-9000",
                "udp_ranges": "10000-11000",
            }
        )
        assert obj.tcp_ranges == "8000-9000"
        assert obj.udp_ranges == "10000-11000"

    def test_missing_headend_id(self):
        with pytest.raises(ValidationError):
            PortConfigRequest.model_validate({"cluster_id": 5})

    def test_missing_cluster_id(self):
        with pytest.raises(ValidationError):
            PortConfigRequest.model_validate({"headend_id": "hub-1"})

    def test_strict_mode_rejects_string_cluster_id(self):
        with pytest.raises(ValidationError):
            PortConfigRequest.model_validate({"headend_id": "hub-1", "cluster_id": "5"})

    def test_expected_fields(self):
        fields = set(PortConfigRequest.model_fields.keys())
        assert fields == {"headend_id", "cluster_id", "tcp_ranges", "udp_ranges"}


# ---------------------------------------------------------------------------
# Perf schemas
# ---------------------------------------------------------------------------


class TestPerfMetricSubmission:
    def test_valid_minimal(self):
        obj = PerfMetricSubmission.model_validate(
            {
                "source_id": "router-1",
                "source_type": "hub-router",
                "target_id": "client-1",
                "protocol": "wireguard",
                "latency_ms": 12.5,
            }
        )
        assert obj.source_id == "router-1"
        assert obj.latency_ms == 12.5
        assert obj.jitter_ms is None
        assert obj.packet_loss_pct is None
        assert obj.throughput_mbps is None
        assert obj.timestamp is None

    def test_valid_full(self):
        obj = PerfMetricSubmission.model_validate(
            {
                "source_id": "router-1",
                "source_type": "client",
                "target_id": "router-2",
                "protocol": "tcp",
                "latency_ms": 5.0,
                "jitter_ms": 0.5,
                "packet_loss_pct": 0.01,
                "throughput_mbps": 950.0,
                "timestamp": "2026-02-26T00:00:00Z",
            }
        )
        assert obj.jitter_ms == 0.5
        assert obj.throughput_mbps == 950.0

    def test_valid_source_types(self):
        for source_type in ("hub-router", "client"):
            obj = PerfMetricSubmission.model_validate(
                {
                    "source_id": "s",
                    "source_type": source_type,
                    "target_id": "t",
                    "protocol": "udp",
                    "latency_ms": 1.0,
                }
            )
            assert obj.source_type == source_type

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            PerfMetricSubmission.model_validate(
                {
                    "source_id": "s",
                    "source_type": "gateway",
                    "target_id": "t",
                    "protocol": "tcp",
                    "latency_ms": 1.0,
                }
            )

    def test_missing_latency_ms(self):
        with pytest.raises(ValidationError):
            PerfMetricSubmission.model_validate(
                {
                    "source_id": "s",
                    "source_type": "client",
                    "target_id": "t",
                    "protocol": "tcp",
                }
            )

    def test_strict_mode_rejects_string_latency(self):
        with pytest.raises(ValidationError):
            PerfMetricSubmission.model_validate(
                {
                    "source_id": "s",
                    "source_type": "client",
                    "target_id": "t",
                    "protocol": "tcp",
                    "latency_ms": "12.5",
                }
            )

    def test_expected_fields(self):
        fields = set(PerfMetricSubmission.model_fields.keys())
        assert fields == {
            "source_id", "source_type", "target_id", "protocol",
            "latency_ms", "jitter_ms", "packet_loss_pct", "throughput_mbps", "timestamp",
        }


class TestPerfMetricQuery:
    def test_all_optional_defaults(self):
        obj = PerfMetricQuery.model_validate({})
        assert obj.cluster_id is None
        assert obj.time_range_start is None
        assert obj.time_range_end is None
        assert obj.protocol is None
        assert obj.limit == 100

    def test_valid_with_params(self):
        obj = PerfMetricQuery.model_validate(
            {
                "cluster_id": "cluster-5",
                "time_range_start": "2026-02-01T00:00:00Z",
                "time_range_end": "2026-02-28T00:00:00Z",
                "protocol": "tcp",
                "limit": 50,
            }
        )
        assert obj.cluster_id == "cluster-5"
        assert obj.limit == 50

    def test_custom_limit(self):
        obj = PerfMetricQuery.model_validate({"limit": 500})
        assert obj.limit == 500

    def test_strict_mode_rejects_string_limit(self):
        with pytest.raises(ValidationError):
            PerfMetricQuery.model_validate({"limit": "50"})

    def test_expected_fields(self):
        fields = set(PerfMetricQuery.model_fields.keys())
        assert fields == {
            "cluster_id", "time_range_start", "time_range_end", "protocol", "limit"
        }


# ---------------------------------------------------------------------------
# Policy schemas
# ---------------------------------------------------------------------------


class TestPolicyRuleCreateRequest:
    def test_valid_minimal(self):
        obj = PolicyRuleCreateRequest.model_validate({"name": "allow-all"})
        assert obj.name == "allow-all"
        assert obj.action == "allow"
        assert obj.priority == 100
        assert obj.scope == "both"
        assert obj.direction == "both"
        assert obj.protocol == "any"
        assert obj.enabled is True
        assert obj.description is None

    def test_valid_full(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {
                "name": "deny-external",
                "description": "Block all external traffic",
                "action": "deny",
                "priority": 50,
                "scope": "wireguard",
                "direction": "inbound",
                "domains": ["evil.example.com"],
                "ports": ["443", "8080-8090"],
                "protocol": "tcp",
                "src_cidrs": ["0.0.0.0/0"],
                "dst_cidrs": ["10.0.0.0/8"],
                "users": ["uid-1"],
                "groups": ["grp-1"],
                "identity_provider": "oidc",
                "enabled": False,
                "tenant_id": "acme",
            }
        )
        assert obj.action == "deny"
        assert obj.scope == "wireguard"
        assert obj.protocol == "tcp"
        assert obj.enabled is False

    # --- action field ---

    def test_action_allow(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "action": "allow"}
        )
        assert obj.action == "allow"

    def test_action_deny(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "action": "deny"}
        )
        assert obj.action == "deny"

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate({"name": "r", "action": "drop"})

    # --- scope field ---

    def test_scope_wireguard(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "scope": "wireguard"}
        )
        assert obj.scope == "wireguard"

    def test_scope_k8s(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "scope": "k8s"}
        )
        assert obj.scope == "k8s"

    def test_scope_openziti(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "scope": "openziti"}
        )
        assert obj.scope == "openziti"

    def test_scope_both(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "scope": "both"}
        )
        assert obj.scope == "both"

    def test_invalid_scope(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "scope": "ipsec"}
            )

    # --- direction field ---

    def test_direction_inbound(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "direction": "inbound"}
        )
        assert obj.direction == "inbound"

    def test_direction_outbound(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "direction": "outbound"}
        )
        assert obj.direction == "outbound"

    def test_direction_both(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "direction": "both"}
        )
        assert obj.direction == "both"

    def test_invalid_direction(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "direction": "egress"}
            )

    # --- protocol field ---

    def test_protocol_tcp(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "protocol": "tcp"}
        )
        assert obj.protocol == "tcp"

    def test_protocol_udp(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "protocol": "udp"}
        )
        assert obj.protocol == "udp"

    def test_protocol_icmp(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "protocol": "icmp"}
        )
        assert obj.protocol == "icmp"

    def test_protocol_any(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "protocol": "any"}
        )
        assert obj.protocol == "any"

    def test_invalid_protocol(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "protocol": "esp"}
            )

    # --- identity_provider field ---

    def test_identity_provider_local(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "identity_provider": "local"}
        )
        assert obj.identity_provider == "local"

    def test_identity_provider_oidc(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "identity_provider": "oidc"}
        )
        assert obj.identity_provider == "oidc"

    def test_identity_provider_saml(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "identity_provider": "saml"}
        )
        assert obj.identity_provider == "saml"

    def test_identity_provider_scim(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "identity_provider": "scim"}
        )
        assert obj.identity_provider == "scim"

    def test_invalid_identity_provider(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "identity_provider": "ldap"}
            )

    # --- CIDR validation ---

    def test_valid_src_cidrs_ipv4(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "src_cidrs": ["10.0.0.0/8", "192.168.0.0/16"]}
        )
        assert obj.src_cidrs is not None
        assert len(obj.src_cidrs) == 2

    def test_valid_dst_cidrs_ipv6(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "dst_cidrs": ["fe80::/10", "2001:db8::/32"]}
        )
        assert obj.dst_cidrs is not None

    def test_cidr_with_host_bits_accepted(self):
        # strict=False is the default — host bits are allowed and normalised
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "src_cidrs": ["192.168.1.5/24"]}
        )
        assert obj.src_cidrs is not None

    def test_invalid_src_cidr_plain_ip(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "src_cidrs": ["192.168.1.1"]}
            )

    def test_invalid_dst_cidr_garbage(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "dst_cidrs": ["not-a-cidr"]}
            )

    def test_invalid_cidr_out_of_range_prefix(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "src_cidrs": ["10.0.0.0/33"]}
            )

    def test_cidrs_none_is_allowed(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "src_cidrs": None, "dst_cidrs": None}
        )
        assert obj.src_cidrs is None
        assert obj.dst_cidrs is None

    # --- Port validation ---

    def test_valid_single_port(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "ports": ["80"]}
        )
        assert obj.ports == ["80"]

    def test_valid_port_range(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "ports": ["8000-9000"]}
        )
        assert obj.ports == ["8000-9000"]

    def test_valid_port_boundary_min(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "ports": ["1"]}
        )
        assert obj.ports == ["1"]

    def test_valid_port_boundary_max(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "ports": ["65535"]}
        )
        assert obj.ports == ["65535"]

    def test_valid_port_range_full_span(self):
        obj = PolicyRuleCreateRequest.model_validate(
            {"name": "r", "ports": ["1-65535"]}
        )
        assert obj.ports == ["1-65535"]

    def test_invalid_port_zero(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate({"name": "r", "ports": ["0"]})

    def test_invalid_port_over_max(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate({"name": "r", "ports": ["65536"]})

    def test_invalid_port_range_backwards(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "ports": ["9000-8000"]}
            )

    def test_invalid_port_range_start_zero(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "ports": ["0-1000"]}
            )

    def test_invalid_port_range_end_over_max(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate(
                {"name": "r", "ports": ["1000-65536"]}
            )

    def test_ports_none_is_allowed(self):
        obj = PolicyRuleCreateRequest.model_validate({"name": "r", "ports": None})
        assert obj.ports is None

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            PolicyRuleCreateRequest.model_validate({})

    def test_expected_fields(self):
        fields = set(PolicyRuleCreateRequest.model_fields.keys())
        assert fields == {
            "name", "description", "action", "priority", "scope", "direction",
            "domains", "ports", "protocol", "src_cidrs", "dst_cidrs",
            "users", "groups", "identity_provider", "enabled", "tenant_id",
        }


class TestPolicyRuleUpdateRequest:
    def test_all_optional_defaults_to_none(self):
        obj = PolicyRuleUpdateRequest.model_validate({})
        assert obj.name is None
        assert obj.action is None
        assert obj.scope is None
        assert obj.enabled is None

    def test_valid_partial_update(self):
        obj = PolicyRuleUpdateRequest.model_validate(
            {"action": "deny", "enabled": False}
        )
        assert obj.action == "deny"
        assert obj.enabled is False

    # --- scope includes openziti ---

    def test_scope_openziti(self):
        obj = PolicyRuleUpdateRequest.model_validate({"scope": "openziti"})
        assert obj.scope == "openziti"

    def test_scope_wireguard(self):
        obj = PolicyRuleUpdateRequest.model_validate({"scope": "wireguard"})
        assert obj.scope == "wireguard"

    def test_scope_k8s(self):
        obj = PolicyRuleUpdateRequest.model_validate({"scope": "k8s"})
        assert obj.scope == "k8s"

    def test_scope_both(self):
        obj = PolicyRuleUpdateRequest.model_validate({"scope": "both"})
        assert obj.scope == "both"

    def test_invalid_scope(self):
        with pytest.raises(ValidationError):
            PolicyRuleUpdateRequest.model_validate({"scope": "ipsec"})

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            PolicyRuleUpdateRequest.model_validate({"action": "forward"})

    def test_invalid_protocol(self):
        with pytest.raises(ValidationError):
            PolicyRuleUpdateRequest.model_validate({"protocol": "gre"})

    def test_valid_src_cidrs(self):
        obj = PolicyRuleUpdateRequest.model_validate(
            {"src_cidrs": ["10.0.0.0/8"]}
        )
        assert obj.src_cidrs == ["10.0.0.0/8"]

    def test_invalid_src_cidr(self):
        with pytest.raises(ValidationError):
            PolicyRuleUpdateRequest.model_validate(
                {"src_cidrs": ["bad-cidr"]}
            )

    def test_valid_ports(self):
        obj = PolicyRuleUpdateRequest.model_validate({"ports": ["443", "8000-9000"]})
        assert obj.ports == ["443", "8000-9000"]

    def test_invalid_port_zero(self):
        with pytest.raises(ValidationError):
            PolicyRuleUpdateRequest.model_validate({"ports": ["0"]})

    def test_expected_fields(self):
        fields = set(PolicyRuleUpdateRequest.model_fields.keys())
        assert fields == {
            "name", "description", "action", "priority", "scope", "direction",
            "domains", "ports", "protocol", "src_cidrs", "dst_cidrs",
            "users", "groups", "identity_provider", "enabled", "tenant_id",
        }
