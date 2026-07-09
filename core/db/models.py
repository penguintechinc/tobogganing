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


__all__ = ["User", "RefreshToken", "PasswordResetToken", "FirewallRule"]
