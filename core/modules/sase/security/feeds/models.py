"""SQLAlchemy models for security threat feeds."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, JSON, Index, UniqueConstraint, ForeignKey
)

from core.db.base import Base


class ThreatIndicator(Base):
    """Security threat indicator model."""

    __tablename__ = "threat_indicators"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    indicator_type = Column(String(16), nullable=False, index=True)  # domain/ip
    value = Column(String(255), nullable=False)
    threat_types = Column(JSON, nullable=False)
    source = Column(String(32), nullable=False, index=True)
    confidence = Column(Integer, nullable=False)
    first_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    ttl = Column(Integer, default=3600)
    threat_metadata = Column(JSON, name="metadata")
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("value", "source", "tenant_id", name="uq_threat_indicators_value_source_tenant"),
        Index("ix_threat_indicators_tenant_id", "tenant_id"),
    )


class FeedUpdate(Base):
    """Security feed update history model."""

    __tablename__ = "feed_updates"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    source = Column(String(32), nullable=False)
    update_type = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False)
    indicators_added = Column(Integer, default=0)
    indicators_updated = Column(Integer, default=0)
    indicators_removed = Column(Integer, default=0)
    error_message = Column(String(500))
    duration_seconds = Column(Integer)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_feed_updates_tenant_id", "tenant_id"),
        Index("ix_feed_updates_source", "source"),
    )


class ThreatDetection(Base):
    """Threat detection event log model."""

    __tablename__ = "threat_detections"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    client_ip = Column(String(45), nullable=False)
    requested_domain = Column(String(255))
    requested_ip = Column(String(45))
    threat_indicator_id = Column(String(36), ForeignKey("threat_indicators.id"))
    action_taken = Column(String(32), nullable=False)
    threat_types = Column(JSON)
    confidence = Column(Integer)
    source = Column(String(32))
    detection_metadata = Column(JSON, name="metadata")
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_threat_detections_tenant_id", "tenant_id"),
        Index("ix_threat_detections_client_ip", "client_ip"),
        Index("ix_threat_detections_detected_at", "detected_at"),
    )
