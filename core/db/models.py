"""SQLAlchemy table models for core database."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UUID, UniqueConstraint, JSON
from sqlalchemy.sql import func

from core.db.base import Base


class User(Base):
    """Identity table for users."""

    __tablename__ = "users"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    email: Column[str] = Column(String(255), nullable=False, index=True)
    username: Column[str] = Column(String(255), nullable=False, index=True)
    password_hash: Column[str] = Column(String(255), nullable=False)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False)
    mfa_enabled: Column[bool] = Column(Boolean, default=False, nullable=False)
    mfa_secret: Column[str | None] = Column(String(255), nullable=True)
    role: Column[str | None] = Column(String(50), default="reporter", nullable=True)
    tenant: Column[str] = Column(
        String(255), nullable=False, index=True
    )  # MANDATORY tenant column
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "email", name="uq_users_tenant_email"),
        UniqueConstraint("tenant", "username", name="uq_users_tenant_username"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<User(id={self.id}, email={self.email}, tenant={self.tenant})>"


class RefreshToken(Base):
    """Refresh tokens for user sessions."""

    __tablename__ = "refresh_tokens"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    user_id: Column[str] = Column(
        UUID(as_uuid=False), nullable=False, index=True
    )  # FK to users.id
    token: Column[str] = Column(Text, nullable=False, unique=True, index=True)
    expires_at: Column[datetime] = Column(DateTime, nullable=False)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<RefreshToken(id={self.id}, user_id={self.user_id})>"


class PasswordResetToken(Base):
    """Password reset tokens."""

    __tablename__ = "password_reset_tokens"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    user_id: Column[str] = Column(
        UUID(as_uuid=False), nullable=False, index=True
    )  # FK to users.id
    token: Column[str] = Column(Text, nullable=False, unique=True, index=True)
    expires_at: Column[datetime] = Column(DateTime, nullable=False)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id})>"


class Session(Base):
    """User sessions for SASE auth."""

    __tablename__ = "sessions"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    user_id: Column[str] = Column(
        UUID(as_uuid=False), nullable=False, index=True
    )  # FK to users.id
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    token: Column[str] = Column(Text, nullable=False, unique=True, index=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    expires_at: Column[datetime] = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Session(id={self.id}, user_id={self.user_id}, tenant={self.tenant})>"


class FirewallRule(Base):
    """Firewall access control rules for SASE module."""

    __tablename__ = "firewall_rules"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    user_id: Column[str] = Column(
        UUID(as_uuid=False), nullable=False, index=True
    )  # FK to users.id
    rule_type: Column[str] = Column(String(50), nullable=False)  # domain, ip, ip_range, url_pattern, protocol_rule
    access_type: Column[str] = Column(String(20), nullable=False)  # allow, deny
    pattern: Column[str] = Column(String(500), nullable=False)
    priority: Column[int] = Column(Integer, default=100, nullable=False)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False, index=True)
    description: Column[str | None] = Column(Text, nullable=True)
    src_ip: Column[str | None] = Column(String(100), nullable=True)
    dst_ip: Column[str | None] = Column(String(100), nullable=True)
    protocol: Column[str | None] = Column(String(20), nullable=True)
    src_port: Column[str | None] = Column(String(100), nullable=True)
    dst_port: Column[str | None] = Column(String(100), nullable=True)
    direction: Column[str | None] = Column(String(20), nullable=True)  # inbound, outbound, both
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<FirewallRule(id={self.id}, tenant={self.tenant}, user_id={self.user_id}, rule_type={self.rule_type})>"


class VRF(Base):
    """Virtual Routing and Forwarding configurations for SASE module."""

    __tablename__ = "vrfs"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    name: Column[str] = Column(String(255), nullable=False, index=True)
    description: Column[str | None] = Column(Text, nullable=True)
    rd: Column[str] = Column(String(50), nullable=False)  # Route Distinguisher
    rt_import: Column[str | None] = Column(Text, nullable=True)  # JSON array
    rt_export: Column[str | None] = Column(Text, nullable=True)  # JSON array
    ip_ranges: Column[str | None] = Column(Text, nullable=True)  # JSON array
    status: Column[str] = Column(String(20), default="inactive", nullable=False)  # active, inactive, pending, error
    ospf_enabled: Column[bool] = Column(Boolean, default=False, nullable=False)
    ospf_router_id: Column[str | None] = Column(String(50), nullable=True)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False, index=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_vrfs_tenant_name"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<VRF(id={self.id}, tenant={self.tenant}, name={self.name})>"


class OSPFArea(Base):
    """OSPF area configurations within a VRF."""

    __tablename__ = "ospf_areas"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    vrf_id: Column[str] = Column(
        UUID(as_uuid=False), nullable=False, index=True
    )  # FK to vrfs.id
    area_id: Column[str] = Column(String(20), nullable=False)  # Area ID (e.g., 0.0.0.0)
    area_type: Column[str] = Column(
        String(20), default="normal", nullable=False
    )  # normal, stub, nssa, backbone
    networks: Column[str | None] = Column(Text, nullable=True)  # JSON array
    auth_type: Column[str | None] = Column(String(20), nullable=True)  # none, simple, md5
    auth_key: Column[str | None] = Column(String(255), nullable=True)
    stub_default_cost: Column[int] = Column(Integer, default=1, nullable=False)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "vrf_id", "area_id", name="uq_ospf_areas_tenant_vrf_area"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<OSPFArea(id={self.id}, tenant={self.tenant}, area_id={self.area_id})>"


class OSPFNeighbor(Base):
    """OSPF neighbor relationships."""

    __tablename__ = "ospf_neighbors"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    vrf_id: Column[str] = Column(
        UUID(as_uuid=False), nullable=False, index=True
    )  # FK to vrfs.id
    neighbor_id: Column[str] = Column(String(50), nullable=False)
    neighbor_ip: Column[str] = Column(String(50), nullable=False)
    interface: Column[str] = Column(String(50), nullable=False)
    area_id: Column[str] = Column(String(20), nullable=False)
    state: Column[str] = Column(String(20), default="Down", nullable=False)
    priority: Column[int] = Column(Integer, default=1, nullable=False)
    dead_interval: Column[int] = Column(Integer, default=40, nullable=False)
    hello_interval: Column[int] = Column(Integer, default=10, nullable=False)
    last_seen: Column[datetime | None] = Column(DateTime, nullable=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<OSPFNeighbor(id={self.id}, tenant={self.tenant}, neighbor_id={self.neighbor_id})>"


class PortRange(Base):
    """Port range configurations for headend servers."""

    __tablename__ = "port_ranges"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    headend_id: Column[str] = Column(String(255), nullable=False, index=True)
    cluster_id: Column[str] = Column(String(255), nullable=False, index=True)
    start_port: Column[int] = Column(Integer, nullable=False)
    end_port: Column[int] = Column(Integer, nullable=False)
    protocol: Column[str] = Column(String(20), nullable=False)  # tcp, udp
    description: Column[str | None] = Column(Text, nullable=True)
    enabled: Column[bool] = Column(Boolean, default=True, nullable=False)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<PortRange(id={self.id}, tenant={self.tenant}, headend_id={self.headend_id})>"


class Cluster(Base):
    """SASE cluster configurations."""

    __tablename__ = "clusters"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    name: Column[str] = Column(String(255), nullable=False)
    region: Column[str] = Column(String(100), nullable=False, index=True)
    datacenter: Column[str] = Column(String(100), nullable=False, index=True)
    headend_url: Column[str] = Column(String(500), nullable=False)
    status: Column[str] = Column(String(50), default="active", nullable=False)
    last_heartbeat: Column[datetime] = Column(DateTime, nullable=False)
    client_count: Column[int] = Column(Integer, default=0, nullable=False)
    api_key_hash: Column[str | None] = Column(String(255), nullable=True, index=True)
    cluster_metadata: Column[dict] = Column("metadata", JSON, nullable=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "id", name="uq_clusters_tenant_id"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Cluster(id={self.id}, tenant={self.tenant}, region={self.region}, datacenter={self.datacenter})>"


class Client(Base):
    """SASE client configurations."""

    __tablename__ = "clients"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    name: Column[str] = Column(String(255), nullable=False)
    type: Column[str] = Column(String(50), nullable=False)  # docker, native
    cluster_id: Column[str] = Column(String(255), nullable=False, index=True)
    api_key_hash: Column[str] = Column(String(255), nullable=False, unique=True, index=True)
    public_key: Column[str] = Column(Text, nullable=False)
    ip_address: Column[str] = Column(String(50), nullable=False)
    status: Column[str] = Column(String(50), default="pending", nullable=False)
    client_metadata: Column[dict] = Column("metadata", JSON, nullable=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_seen: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "id", name="uq_clients_tenant_id"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Client(id={self.id}, tenant={self.tenant}, type={self.type}, cluster_id={self.cluster_id})>"


class OrgUnit(Base):
    """Organizational units (teams/departments) with hierarchy support."""

    __tablename__ = "org_units"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    name: Column[str] = Column(String(255), nullable=False)
    parent_id: Column[str | None] = Column(UUID(as_uuid=False), nullable=True, index=True)
    description: Column[str | None] = Column(Text, nullable=True)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False, index=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_org_units_tenant_name"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<OrgUnit(id={self.id}, tenant={self.tenant}, name={self.name})>"


class Device(Base):
    """Devices enrolled and managed by WaddlePerf cluster."""

    __tablename__ = "devices"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    org_unit_id: Column[str | None] = Column(UUID(as_uuid=False), nullable=True, index=True)
    user_id: Column[str | None] = Column(UUID(as_uuid=False), nullable=True, index=True)
    name: Column[str] = Column(String(255), nullable=False)
    serial: Column[str] = Column(String(255), nullable=False)
    hostname: Column[str | None] = Column(String(255), nullable=True)
    os: Column[str | None] = Column(String(100), nullable=True)
    status: Column[str] = Column(String(50), default="offline", nullable=False, index=True)
    last_heartbeat: Column[datetime | None] = Column(DateTime, nullable=True)
    device_metadata: Column[dict] = Column("metadata", JSON, nullable=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "serial", name="uq_devices_tenant_serial"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Device(id={self.id}, tenant={self.tenant}, serial={self.serial})>"


class DeviceApiKey(Base):
    """API keys for device authentication."""

    __tablename__ = "device_api_keys"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    device_id: Column[str] = Column(UUID(as_uuid=False), nullable=False, index=True)
    api_key_hash: Column[str] = Column(String(255), nullable=False, index=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    revoked_at: Column[datetime | None] = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<DeviceApiKey(id={self.id}, tenant={self.tenant}, device_id={self.device_id})>"


class DeviceEnrollmentSecret(Base):
    """Enrollment secrets for secure device onboarding."""

    __tablename__ = "device_enrollment_secrets"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    org_unit_id: Column[str | None] = Column(UUID(as_uuid=False), nullable=True, index=True)
    secret_hash: Column[str] = Column(String(255), nullable=False, index=True)
    expires_at: Column[datetime | None] = Column(DateTime, nullable=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    created_by: Column[str | None] = Column(UUID(as_uuid=False), nullable=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<DeviceEnrollmentSecret(id={self.id}, tenant={self.tenant})>"


class PerfTestResult(Base):
    """Performance test results from WaddlePerf devices."""

    __tablename__ = "perf_test_results"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    device_id: Column[str] = Column(UUID(as_uuid=False), nullable=False, index=True)
    test_type: Column[str] = Column(String(50), nullable=False, index=True)
    status: Column[str] = Column(String(50), default="pending", nullable=False)
    target: Column[str | None] = Column(String(255), nullable=True)
    started_at: Column[datetime | None] = Column(DateTime, nullable=True)
    completed_at: Column[datetime | None] = Column(DateTime, nullable=True)
    latency_ms: Column[float | None] = Column(Float, nullable=True)
    throughput: Column[float | None] = Column(Float, nullable=True)
    test_output: Column[str | None] = Column(Text, nullable=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<PerfTestResult(id={self.id}, tenant={self.tenant}, device_id={self.device_id})>"


class ClientConfig(Base):
    """Client configurations for WaddlePerf devices."""

    __tablename__ = "client_configs"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    org_unit_id: Column[str | None] = Column(UUID(as_uuid=False), nullable=True, index=True)
    config: Column[dict] = Column(JSON, nullable=True)
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Column[str | None] = Column(UUID(as_uuid=False), nullable=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<ClientConfig(id={self.id}, tenant={self.tenant})>"


class ServerKey(Base):
    """Server keys for service-to-service authentication."""

    __tablename__ = "server_keys"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    key_id: Column[str] = Column(String(255), nullable=False, index=True)
    public_key: Column[str] = Column(Text, nullable=False)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<ServerKey(id={self.id}, tenant={self.tenant}, key_id={self.key_id})>"


class TestSchedule(Base):
    """Test schedules for WaddlePerf client testing."""

    __tablename__ = "test_schedules"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    org_unit_id: Column[str | None] = Column(UUID(as_uuid=False), nullable=True, index=True)
    test_type: Column[str] = Column(String(50), nullable=False)
    target: Column[str] = Column(String(255), nullable=False)
    interval_seconds: Column[int] = Column(Integer, nullable=False)
    enabled: Column[bool] = Column(Boolean, default=True, nullable=False)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "org_unit_id", "test_type", "target", name="uq_test_schedules_tenant_ou_type_target"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<TestSchedule(id={self.id}, tenant={self.tenant}, test_type={self.test_type})>"


class C2CEndpoint(Base):
    """Cluster-to-cluster test endpoints."""

    __tablename__ = "c2c_endpoints"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    region: Column[str] = Column(String(100), nullable=False, index=True)
    name: Column[str] = Column(String(255), nullable=False)
    engine_url: Column[str] = Column(String(500), nullable=False)
    target: Column[str] = Column(String(500), nullable=False)
    api_key_hash: Column[str | None] = Column(String(255), nullable=True, index=True)
    enabled: Column[bool] = Column(Boolean, default=True, nullable=False)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant", "region", "name", name="uq_c2c_endpoints_tenant_region_name"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<C2CEndpoint(id={self.id}, tenant={self.tenant}, region={self.region}, name={self.name})>"


class C2CMatrixRun(Base):
    """Cluster-to-cluster matrix test runs."""

    __tablename__ = "c2c_matrix_runs"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    status: Column[str] = Column(String(20), default="pending", nullable=False)
    test_types: Column[dict] = Column(JSON, nullable=True)
    total_pairs: Column[int] = Column(Integer, default=0, nullable=False)
    completed_pairs: Column[int] = Column(Integer, default=0, nullable=False)
    failed_pairs: Column[int] = Column(Integer, default=0, nullable=False)
    created_by: Column[str | None] = Column(UUID(as_uuid=False), nullable=True)
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    started_at: Column[datetime | None] = Column(DateTime, nullable=True)
    completed_at: Column[datetime | None] = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<C2CMatrixRun(id={self.id}, tenant={self.tenant}, status={self.status})>"


class C2CPairResult(Base):
    """Cluster-to-cluster pair test results."""

    __tablename__ = "c2c_pair_results"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(255), nullable=False, index=True)
    run_id: Column[str] = Column(UUID(as_uuid=False), nullable=False, index=True)
    source_endpoint_id: Column[str] = Column(UUID(as_uuid=False), nullable=False)
    dest_endpoint_id: Column[str] = Column(UUID(as_uuid=False), nullable=False)
    source_region: Column[str] = Column(String(100), nullable=False)
    dest_region: Column[str] = Column(String(100), nullable=False)
    test_type: Column[str] = Column(String(50), nullable=False)
    status: Column[str] = Column(String(20), nullable=False)
    latency_ms: Column[float | None] = Column(Float, nullable=True)
    throughput: Column[float | None] = Column(Float, nullable=True)
    loss_pct: Column[float | None] = Column(Float, nullable=True)
    test_output: Column[str | None] = Column(Text, nullable=True)
    measured_at: Column[datetime | None] = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant", "run_id", "source_endpoint_id", "dest_endpoint_id", "test_type",
            name="uq_c2c_pair_results_tenant_run_endpoints_type",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<C2CPairResult(id={self.id}, tenant={self.tenant}, run_id={self.run_id})>"


class ScheduledJob(Base):
    """DB-backed dynamic schedule row dispatched by the core scheduler sweep."""

    __tablename__ = "scheduled_jobs"

    id: Column[str] = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(36), nullable=False, index=True)
    module: Column[str] = Column(String(64), nullable=False)
    job_type: Column[str] = Column(String(64), nullable=False)
    payload: Column[str] = Column(Text, nullable=False)
    interval_seconds: Column[int] = Column(Integer, nullable=False)
    enabled: Column[bool] = Column(Boolean, nullable=False, server_default="true")
    last_run_at: Column[datetime | None] = Column(DateTime, nullable=True)
    next_run_at: Column[datetime] = Column(DateTime, nullable=False, index=True)
    created_at: Column[datetime] = Column(DateTime, nullable=False)
    updated_at: Column[datetime] = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<ScheduledJob(id={self.id}, module={self.module}, job_type={self.job_type})>"


class NotificationChannel(Base):
    """Notification delivery channel (email or webhook)."""

    __tablename__ = "notification_channels"

    id: Column[str] = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(36), nullable=False, index=True)
    name: Column[str] = Column(String(128), nullable=False)
    kind: Column[str] = Column(String(16), nullable=False)
    config: Column[str] = Column(Text, nullable=False)
    enabled: Column[bool] = Column(Boolean, nullable=False, server_default="true")
    created_at: Column[datetime] = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<NotificationChannel(id={self.id}, tenant={self.tenant}, kind={self.kind})>"


class NotificationDelivery(Base):
    """Record of a delivery attempt for a notification."""

    __tablename__ = "notification_deliveries"

    id: Column[str] = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(36), nullable=False, index=True)
    channel_id: Column[str] = Column(String(36), nullable=False)
    subject: Column[str] = Column(String(256), nullable=False)
    status: Column[str] = Column(String(16), nullable=False)
    error: Column[str | None] = Column(Text, nullable=True)
    created_at: Column[datetime] = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<NotificationDelivery(id={self.id}, channel_id={self.channel_id}, status={self.status})>"


class AlertRule(Base):
    """Alert rule for threshold-based notifications."""

    __tablename__ = "alert_rules"

    id: Column[str] = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(36), nullable=False, index=True)
    name: Column[str] = Column(String(128), nullable=False)
    metric: Column[str] = Column(String(64), nullable=False)
    comparator: Column[str] = Column(String(8), nullable=False)
    threshold: Column[float] = Column(Float, nullable=False)
    window_seconds: Column[int] = Column(Integer, nullable=False, server_default="300")
    device_id: Column[str | None] = Column(String(36), nullable=True)
    test_type: Column[str | None] = Column(String(32), nullable=True)
    channel_id: Column[str | None] = Column(String(36), nullable=True)
    enabled: Column[bool] = Column(Boolean, nullable=False, server_default="true")
    created_at: Column[datetime] = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<AlertRule(id={self.id}, tenant={self.tenant}, metric={self.metric}, comparator={self.comparator})>"


class AlertEvent(Base):
    """Alert event fired when a rule is breached."""

    __tablename__ = "alert_events"

    id: Column[str] = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
    )
    tenant: Column[str] = Column(String(36), nullable=False, index=True)
    rule_id: Column[str] = Column(String(36), nullable=False)
    device_id: Column[str | None] = Column(String(36), nullable=True)
    observed_value: Column[float] = Column(Float, nullable=False)
    fired_at: Column[datetime] = Column(DateTime, nullable=False)
    notified: Column[bool] = Column(Boolean, nullable=False, server_default="false")

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<AlertEvent(id={self.id}, rule_id={self.rule_id}, observed_value={self.observed_value})>"


__all__ = [
    "User",
    "RefreshToken",
    "PasswordResetToken",
    "Session",
    "FirewallRule",
    "VRF",
    "OSPFArea",
    "OSPFNeighbor",
    "PortRange",
    "Cluster",
    "Client",
    "OrgUnit",
    "Device",
    "DeviceApiKey",
    "DeviceEnrollmentSecret",
    "PerfTestResult",
    "ClientConfig",
    "ServerKey",
    "TestSchedule",
    "C2CEndpoint",
    "C2CMatrixRun",
    "C2CPairResult",
    "ScheduledJob",
    "NotificationChannel",
    "NotificationDelivery",
    "AlertRule",
    "AlertEvent",
]
