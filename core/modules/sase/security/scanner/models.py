"""SQLAlchemy models for security scanner."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship

from core.db.base import Base


class SecurityScan(Base):
    """Security scan record."""

    __tablename__ = "security_scans"

    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), unique=True, nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    scan_type = Column(String(32), nullable=False, index=True)
    target = Column(String(255), nullable=False)
    tools_used = Column(JSON, nullable=True)
    status = Column(String(16), default="pending", nullable=False, index=True)
    findings_count = Column(Integer, default=0)
    critical_findings = Column(Integer, default=0)
    high_findings = Column(Integer, default=0)
    medium_findings = Column(Integer, default=0)
    low_findings = Column(Integer, default=0)
    scan_duration = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    triggered_by = Column(String(64), nullable=True)
    scan_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship to findings
    findings = relationship("SecurityFinding", back_populates="scan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_security_scans_tenant_status", "tenant_id", "status"),
        Index("idx_security_scans_scan_type", "scan_type"),
    )


class SecurityFinding(Base):
    """Security finding record."""

    __tablename__ = "security_findings"

    id = Column(String(36), primary_key=True)
    finding_id = Column(String(36), unique=True, nullable=False, index=True)
    scan_id = Column(String(36), ForeignKey("security_scans.scan_id"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    finding_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    affected_component = Column(String(255), nullable=True)
    recommendation = Column(Text, nullable=True)
    cve_ids = Column(JSON, nullable=True)
    cvss_score = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=True)
    status = Column(String(16), default="open", nullable=False, index=True)
    remediated_at = Column(DateTime, nullable=True)
    false_positive = Column(Boolean, default=False)
    first_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    finding_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship to scan
    scan = relationship("SecurityScan", back_populates="findings")

    __table_args__ = (
        Index("idx_security_findings_tenant_severity", "tenant_id", "severity"),
        Index("idx_security_findings_finding_type", "finding_type"),
        Index("idx_security_findings_status", "status"),
    )


class ScanSchedule(Base):
    """Scheduled security scan definition."""

    __tablename__ = "scan_schedules"

    id = Column(String(36), primary_key=True)
    schedule_id = Column(String(36), unique=True, nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    scan_type = Column(String(32), nullable=False)
    target_pattern = Column(String(255), nullable=False)
    cron_schedule = Column(String(32), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_scan_schedules_tenant_enabled", "tenant_id", "enabled"),
    )
