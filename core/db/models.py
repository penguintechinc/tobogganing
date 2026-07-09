"""SQLAlchemy table models for core database."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UUID
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
    email: Column[str] = Column(String(255), unique=True, nullable=False, index=True)
    username: Column[str] = Column(String(255), unique=True, nullable=False, index=True)
    password_hash: Column[str] = Column(String(255), nullable=False)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False)
    mfa_enabled: Column[bool] = Column(Boolean, default=False, nullable=False)
    mfa_secret: Column[str | None] = Column(String(255), nullable=True)
    tenant: Column[str] = Column(
        String(255), nullable=False, index=True
    )  # MANDATORY tenant column
    created_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Column[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
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
    name: Column[str] = Column(String(255), nullable=False, unique=True, index=True)
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


__all__ = [
    "User",
    "RefreshToken",
    "PasswordResetToken",
    "FirewallRule",
    "VRF",
    "OSPFArea",
    "OSPFNeighbor",
    "PortRange",
]
