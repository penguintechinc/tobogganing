"""SQLAlchemy declarative models for Tobogganing hub-api.

SQLAlchemy + Alembic owns DDL/migrations. PyDAL is runtime-only
(migrate=False) and must stay in sync manually.

Existing tables: users, clusters, clients, policy_rules, vrfs,
    ospf_config, port_configs, port_ranges, certificates,
    sessions, jwt_tokens.

v0.2.0 additions: tenants, teams, user_team_memberships,
    role_scope_bundles, spiffe_entries, identity_mappings.
users and policy_rules gain a nullable tenant_id FK for
backward-compatible migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey,
    Index, Integer, JSON, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ------------------------------------------------------------------
# Base + timestamp mixin
# ------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class _Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ------------------------------------------------------------------
# v0.2.0 — Tenant (declared first; users + policy_rules FK into it)
# ------------------------------------------------------------------

class Tenant(Base, _Timestamps):
    """Isolated org unit. spiffe_trust_domain: SPIRE trust domain. config: JSON."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(255))
    spiffe_trust_domain: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    config: Mapped[Any | None] = mapped_column(JSON)

    users: Mapped[list[User]] = relationship(
        "User", back_populates="tenant", foreign_keys="User.tenant_id"
    )
    teams: Mapped[list[Team]] = relationship(
        "Team", back_populates="tenant", cascade="all, delete-orphan"
    )
    policy_rules: Mapped[list[PolicyRule]] = relationship(
        "PolicyRule", back_populates="tenant", foreign_keys="PolicyRule.tenant_id"
    )
    spiffe_entries: Mapped[list[SpiffeEntry]] = relationship(
        "SpiffeEntry", back_populates="tenant", cascade="all, delete-orphan"
    )
    identity_mappings: Mapped[list[IdentityMapping]] = relationship(
        "IdentityMapping", back_populates="tenant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_tenants_tenant_id", "tenant_id", unique=True),
        Index("ix_tenants_domain", "domain"),
        Index("ix_tenants_spiffe_trust_domain", "spiffe_trust_domain"),
    )


# ------------------------------------------------------------------
# Existing tables
# ------------------------------------------------------------------

class User(Base, _Timestamps):
    """Users. v0.2.0: nullable tenant_id (NULL=platform). PyDAL must stay in sync."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(50), default="user", server_default="user"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    tenant_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("tenants.tenant_id", ondelete="SET NULL"), index=True,
    )

    tenant: Mapped[Tenant | None] = relationship(
        "Tenant", back_populates="users", foreign_keys=[tenant_id]
    )
    clients: Mapped[list[Client]] = relationship(
        "Client", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[Session]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    jwt_tokens: Mapped[list[JWTToken]] = relationship(
        "JWTToken", back_populates="user", cascade="all, delete-orphan"
    )
    team_memberships: Mapped[list[UserTeamMembership]] = relationship(
        "UserTeamMembership", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'reporter', 'user')", name="ck_users_role"),
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )


class Cluster(Base, _Timestamps):
    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    region: Mapped[str | None] = mapped_column(String(100))
    datacenter: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(50), default="active", server_default="active"
    )
    config: Mapped[Any | None] = mapped_column(JSON)

    clients: Mapped[list[Client]] = relationship(
        "Client", back_populates="cluster", cascade="all, delete-orphan"
    )
    port_configs: Mapped[list[PortConfig]] = relationship(
        "PortConfig", back_populates="cluster", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'maintenance')",
            name="ck_clusters_status",
        ),
        Index("ix_clusters_status", "status"),
    )


class Client(Base, _Timestamps):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50))
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clusters.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(
        String(50), default="active", server_default="active"
    )
    public_key: Mapped[str | None] = mapped_column(Text)
    config: Mapped[Any | None] = mapped_column(JSON)
    tunnel_mode: Mapped[str] = mapped_column(
        String(20), default="full", server_default="full"
    )
    split_tunnel_routes: Mapped[Any | None] = mapped_column(JSON)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship("User", back_populates="clients")
    cluster: Mapped[Cluster] = relationship("Cluster", back_populates="clients")
    certificates: Mapped[list[Certificate]] = relationship(
        "Certificate", back_populates="client", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("type IN ('native', 'docker', 'mobile')", name="ck_cli_type"),
        CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')", name="ck_cli_status"
        ),
        CheckConstraint("tunnel_mode IN ('full', 'split')", name="ck_cli_tunnel"),
        Index("ix_clients_user_id", "user_id"),
        Index("ix_clients_cluster_id", "cluster_id"),
        Index("ix_clients_status", "status"),
    )


class PolicyRule(Base, _Timestamps):
    """Unified rules for Go PolicyEngine (wireguard) and Cilium (k8s/both).
    Dimension fields are JSON arrays. v0.2.0: nullable tenant_id (NULL=global).
    PyDAL must stay in sync.
    """

    __tablename__ = "policy_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(
        String(20), default="allow", server_default="allow"
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=100, server_default="100"
    )
    scope: Mapped[str] = mapped_column(
        String(20), default="both", server_default="both"
    )
    direction: Mapped[str] = mapped_column(
        String(20), default="both", server_default="both"
    )
    domains: Mapped[Any | None] = mapped_column(JSON)
    ports: Mapped[Any | None] = mapped_column(JSON)
    protocol: Mapped[str] = mapped_column(
        String(20), default="any", server_default="any"
    )
    src_cidrs: Mapped[Any | None] = mapped_column(JSON)
    dst_cidrs: Mapped[Any | None] = mapped_column(JSON)
    users: Mapped[Any | None] = mapped_column(JSON)
    groups: Mapped[Any | None] = mapped_column(JSON)
    identity_provider: Mapped[str] = mapped_column(
        String(50), default="local", server_default="local"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("tenants.tenant_id", ondelete="SET NULL"), index=True,
    )

    tenant: Mapped[Tenant | None] = relationship(
        "Tenant", back_populates="policy_rules", foreign_keys=[tenant_id]
    )

    __table_args__ = (
        CheckConstraint("action IN ('allow', 'deny')", name="ck_pr_action"),
        CheckConstraint("scope IN ('wireguard', 'k8s', 'both')", name="ck_pr_scope"),
        CheckConstraint(
            "direction IN ('inbound', 'outbound', 'both')", name="ck_pr_direction"
        ),
        CheckConstraint(
            "protocol IN ('tcp', 'udp', 'icmp', 'any')", name="ck_pr_protocol"
        ),
        CheckConstraint(
            "identity_provider IN ('local', 'oidc', 'saml', 'scim')",
            name="ck_pr_idp",
        ),
        Index("ix_policy_rules_tenant_id", "tenant_id"),
        Index("ix_policy_rules_scope_enabled", "scope", "enabled"),
        Index("ix_policy_rules_priority", "priority"),
    )


class VRF(Base, _Timestamps):
    __tablename__ = "vrfs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    rd: Mapped[str] = mapped_column(String(100), unique=True)
    ip_ranges: Mapped[Any | None] = mapped_column(JSON)
    area_type: Mapped[str] = mapped_column(
        String(50), default="normal", server_default="normal"
    )
    area_id: Mapped[str | None] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )

    ospf_configs: Mapped[list[OSPFConfig]] = relationship(
        "OSPFConfig", back_populates="vrf", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "area_type IN ('normal', 'stub', 'nssa', 'backbone')",
            name="ck_vrfs_area_type",
        ),
    )


class OSPFConfig(Base, _Timestamps):
    __tablename__ = "ospf_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vrf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vrfs.id", ondelete="CASCADE")
    )
    area_id: Mapped[str] = mapped_column(String(50))
    area_type: Mapped[str] = mapped_column(
        String(50), default="normal", server_default="normal"
    )
    networks: Mapped[Any | None] = mapped_column(JSON)
    interfaces: Mapped[Any | None] = mapped_column(JSON)
    auth_type: Mapped[str] = mapped_column(
        String(50), default="none", server_default="none"
    )
    auth_key: Mapped[str | None] = mapped_column(String(255))
    hello_interval: Mapped[int] = mapped_column(
        Integer, default=10, server_default="10"
    )
    dead_interval: Mapped[int] = mapped_column(
        Integer, default=40, server_default="40"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )

    vrf: Mapped[VRF] = relationship("VRF", back_populates="ospf_configs")

    __table_args__ = (
        CheckConstraint(
            "area_type IN ('normal', 'stub', 'nssa', 'backbone')",
            name="ck_ospf_area_type",
        ),
        CheckConstraint(
            "auth_type IN ('none', 'simple', 'md5')", name="ck_ospf_auth_type"
        ),
        Index("ix_ospf_config_vrf_id", "vrf_id"),
    )


class PortConfig(Base, _Timestamps):
    __tablename__ = "port_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    headend_id: Mapped[str] = mapped_column(String(255))
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clusters.id", ondelete="CASCADE")
    )
    tcp_ranges: Mapped[str | None] = mapped_column(Text)
    udp_ranges: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )

    cluster: Mapped[Cluster] = relationship("Cluster", back_populates="port_configs")
    port_ranges: Mapped[list[PortRange]] = relationship(
        "PortRange", back_populates="port_config", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_port_configs_cluster_id", "cluster_id"),)


class PortRange(Base, _Timestamps):
    __tablename__ = "port_ranges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    port_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("port_configs.id", ondelete="CASCADE")
    )
    start_port: Mapped[int] = mapped_column(Integer)
    end_port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )

    port_config: Mapped[PortConfig] = relationship(
        "PortConfig", back_populates="port_ranges"
    )

    __table_args__ = (
        CheckConstraint(
            "protocol IN ('tcp', 'udp')", name="ck_port_ranges_protocol"
        ),
        CheckConstraint(
            "start_port BETWEEN 1 AND 65535", name="ck_port_ranges_start"
        ),
        CheckConstraint("end_port BETWEEN 1 AND 65535", name="ck_port_ranges_end"),
        Index("ix_port_ranges_port_config_id", "port_config_id"),
    )


class Certificate(Base, _Timestamps):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cert_type: Mapped[str] = mapped_column(String(50))
    subject: Mapped[str | None] = mapped_column(String(500))
    issuer: Mapped[str | None] = mapped_column(String(500))
    serial_number: Mapped[str] = mapped_column(
        String(100), unique=True
    )
    not_before: Mapped[datetime | None] = mapped_column(DateTime)
    not_after: Mapped[datetime | None] = mapped_column(DateTime)
    certificate_pem: Mapped[str | None] = mapped_column(Text)
    private_key_pem: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="CASCADE")
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    client: Mapped[Client | None] = relationship(
        "Client", back_populates="certificates"
    )

    __table_args__ = (
        CheckConstraint(
            "cert_type IN ('client', 'server', 'ca')", name="ck_certificates_type"
        ),
        Index("ix_certificates_client_id", "client_id"),
        Index("ix_certificates_not_after", "not_after"),
    )


class Session(Base):
    """Web session (no updated_at — immutable)."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(255), unique=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )


class JWTToken(Base):
    """JWT token lifecycle (no updated_at — revoke-only)."""

    __tablename__ = "jwt_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )
    token_type: Mapped[str] = mapped_column(String(50))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="jwt_tokens")

    __table_args__ = (
        CheckConstraint(
            "token_type IN ('access', 'refresh')", name="ck_jwt_tokens_type"
        ),
        Index("ix_jwt_tokens_user_id", "user_id"),
        Index("ix_jwt_tokens_expires_at", "expires_at"),
    )


# ------------------------------------------------------------------
# v0.2.0 — new tables
# ------------------------------------------------------------------

class Team(Base, _Timestamps):
    """Team within a tenant; team_id is a stable slug/UUID for cross-service FKs."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[str] = mapped_column(String(255), unique=True)
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="teams")
    memberships: Mapped[list[UserTeamMembership]] = relationship(
        "UserTeamMembership", back_populates="team", cascade="all, delete-orphan"
    )
    identity_mappings: Mapped[list[IdentityMapping]] = relationship(
        "IdentityMapping",
        back_populates="team",
        foreign_keys="IdentityMapping.team_id",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),
        Index("ix_teams_team_id", "team_id", unique=True),
        Index("ix_teams_tenant_id", "tenant_id"),
    )


class UserTeamMembership(Base):
    """User-to-team: composite PK (user_id, team_id). role_in_team → layer='team'."""

    __tablename__ = "user_team_memberships"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("teams.team_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_in_team: Mapped[str] = mapped_column(
        String(50), default="viewer", server_default="viewer"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="team_memberships")
    team: Mapped[Team] = relationship("Team", back_populates="memberships")

    __table_args__ = (
        CheckConstraint(
            "role_in_team IN ('admin', 'maintainer', 'viewer')",
            name="ck_utm_role_in_team",
        ),
        Index("ix_utm_user_id", "user_id"),
        Index("ix_utm_team_id", "team_id"),
    )


class RoleScopeBundle(Base, _Timestamps):
    """Role → JSON scopes at layer global|tenant|team|resource. UQ (role, layer)."""

    __tablename__ = "role_scope_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_name: Mapped[str] = mapped_column(String(100))
    layer: Mapped[str] = mapped_column(String(50))
    scopes: Mapped[Any] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("role_name", "layer", name="uq_rsb_role_layer"),
        CheckConstraint(
            "layer IN ('global', 'tenant', 'team', 'resource')", name="ck_rsb_layer"
        ),
        Index("ix_rsb_role_name", "role_name"),
        Index("ix_rsb_layer", "layer"),
    )


class SpiffeEntry(Base, _Timestamps):
    """SPIFFE/SPIRE registration entry managed via gRPC.

    selectors: [{"type": "k8s:pod-label", "value": "app:api"}]
    ttl: X.509-SVID TTL seconds (0 = server default).
    """

    __tablename__ = "spiffe_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spiffe_id: Mapped[str] = mapped_column(String(512), unique=True)
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[str | None] = mapped_column(String(512))
    selectors: Mapped[Any | None] = mapped_column(JSON)
    ttl: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    dns_names: Mapped[Any | None] = mapped_column(JSON)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="spiffe_entries")

    __table_args__ = (
        Index("ix_spiffe_entries_spiffe_id", "spiffe_id", unique=True),
        Index("ix_spiffe_entries_tenant_id", "tenant_id"),
        Index("ix_spiffe_entries_parent_id", "parent_id"),
    )


class IdentityMapping(Base, _Timestamps):
    """External identity → Tobogganing scope bundle.

    provider_type: oidc | spiffe | saml | eks-pod-identity
        | gcp-workload-identity | azure-workload-identity
    external_id: stable id (OIDC sub, SPIFFE URI, cloud IAM principal).
    scopes: JSON permissions granted after token exchange.
    team_id: optional team-scoped mapping.
    Unique on (provider_type, external_id, tenant_id).
    """

    __tablename__ = "identity_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_type: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str] = mapped_column(String(512))
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("teams.team_id", ondelete="SET NULL"),
    )
    scopes: Mapped[Any] = mapped_column(JSON)

    tenant: Mapped[Tenant] = relationship(
        "Tenant", back_populates="identity_mappings"
    )
    team: Mapped[Team | None] = relationship(
        "Team", back_populates="identity_mappings", foreign_keys=[team_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_type", "external_id", "tenant_id",
            name="uq_identity_mappings_provider_external_tenant",
        ),
        Index("ix_identity_mappings_tenant_id", "tenant_id"),
        Index("ix_identity_mappings_team_id", "team_id"),
        Index(
            "ix_identity_mappings_provider_external",
            "provider_type", "external_id",
        ),
    )


# ------------------------------------------------------------------
# Intermediate DTOs — @dataclass(slots=True) per project standard
# ------------------------------------------------------------------


@dataclass(slots=True)
class TenantContext:
    """Resolved tenant context attached to an authenticated request."""

    tenant_id: str
    name: str
    spiffe_trust_domain: str | None
    is_active: bool


@dataclass(slots=True)
class TokenExchangeRequest:
    """Input to the workload-identity token-exchange endpoint."""

    provider_type: str
    raw_credential: str
    requested_scopes: list[str]


@dataclass(slots=True)
class TokenExchangeResult:
    """Output of a successful workload-identity token exchange."""

    tobogganing_jwt: str
    scopes: list[str]
    tenant_id: str
    team_id: str | None
    expires_in: int


@dataclass(slots=True)
class PolicyEvalInput:
    """Six-dimension input to the Go PolicyEngine (gRPC or direct)."""

    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str
    identity: str | None  # SPIFFE URI or user ID


@dataclass(slots=True)
class PolicyEvalResult:
    """Result returned by the PolicyEngine for a connection tuple."""

    action: str            # "allow" or "deny"
    matched_rule_id: int | None
    reason: str
