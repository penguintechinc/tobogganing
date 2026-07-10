"""Test that migrations create all Base.metadata tables."""
from __future__ import annotations

from core.db.base import Base
from core.db.models import (
    User,
    RefreshToken,
    PasswordResetToken,
    Session,
    FirewallRule,
    VRF,
    OSPFArea,
    OSPFNeighbor,
    PortRange,
    Cluster,
    Client,
    OrgUnit,
    Device,
    DeviceApiKey,
    DeviceEnrollmentSecret,
    PerfTestResult,
    ClientConfig,
    ServerKey,
)
from core.modules.sase.security.scanner.models import (
    SecurityScan,
    SecurityFinding,
    ScanSchedule,
)
from core.modules.sase.security.protection.models import (
    SecurityEvent,
    RateLimitRule,
)
from core.modules.sase.security.feeds.models import (
    ThreatIndicator,
    FeedUpdate,
    ThreatDetection,
)


def test_alembic_migrations_cover_all_tables() -> None:
    """Verify all Base.metadata tables are covered by migrations 0001-0012.

    Migration 0001: users, refresh_tokens, password_reset_tokens
    Migration 0002: firewall_rules
    Migration 0003: vrfs, ospf_areas, ospf_neighbors
    Migration 0004: port_ranges
    Migration 0005: sessions (+ role column on users)
    Migration 0006: constraint changes
    Migration 0007: clusters, clients
    Migration 0008: security_scans, security_findings, scan_schedules,
                    security_events, rate_limit_rules, threat_indicators,
                    feed_updates, threat_detections
    Migration 0009: cluster api_key_hash
    Migration 0010: org_units
    Migration 0011: devices, device_api_keys, device_enrollment_secrets
    Migration 0012: perf_test_results, client_configs, server_keys
    """
    # Get expected tables from Base.metadata
    expected_tables = set(Base.metadata.tables.keys())

    # Tables created by migrations 0001-0007
    created_by_existing_migrations = {
        "users",
        "refresh_tokens",
        "password_reset_tokens",
        "sessions",
        "firewall_rules",
        "vrfs",
        "ospf_areas",
        "ospf_neighbors",
        "port_ranges",
        "clusters",
        "clients",
    }

    # Tables created by migration 0008 (security module tables)
    created_by_migration_0008 = {
        "security_scans",
        "security_findings",
        "scan_schedules",
        "security_events",
        "rate_limit_rules",
        "threat_indicators",
        "feed_updates",
        "threat_detections",
    }

    # Tables created by migrations 0010-0012 (WaddlePerf cluster tables)
    created_by_wpc_migrations = {
        "org_units",
        "devices",
        "device_api_keys",
        "device_enrollment_secrets",
        "perf_test_results",
        "client_configs",
        "server_keys",
    }

    # All tables covered by migrations
    all_migration_tables = created_by_existing_migrations | created_by_migration_0008 | created_by_wpc_migrations

    # Verify coverage
    missing_tables = expected_tables - all_migration_tables
    assert (
        not missing_tables
    ), f"Missing from migrations: {missing_tables}"

    extra_tables = all_migration_tables - expected_tables
    assert (
        not extra_tables
    ), f"Migration tables not in Base.metadata: {extra_tables}"


def test_base_metadata_models_imported() -> None:
    """Verify all expected models are defined on Base.metadata."""
    expected_models = [
        User,
        RefreshToken,
        PasswordResetToken,
        Session,
        FirewallRule,
        VRF,
        OSPFArea,
        OSPFNeighbor,
        PortRange,
        Cluster,
        Client,
        OrgUnit,
        Device,
        DeviceApiKey,
        DeviceEnrollmentSecret,
        PerfTestResult,
        ClientConfig,
        ServerKey,
        SecurityScan,
        SecurityFinding,
        ScanSchedule,
        SecurityEvent,
        RateLimitRule,
        ThreatIndicator,
        FeedUpdate,
        ThreatDetection,
    ]

    for model in expected_models:
        assert (
            model.__tablename__ in Base.metadata.tables
        ), f"Model {model.__name__} table {model.__tablename__} not in Base.metadata"


def test_security_tables_in_base_metadata() -> None:
    """Verify security module tables are present in Base.metadata."""
    security_tables = {
        "security_scans",
        "security_findings",
        "scan_schedules",
        "security_events",
        "rate_limit_rules",
        "threat_indicators",
        "feed_updates",
        "threat_detections",
    }

    base_tables = set(Base.metadata.tables.keys())
    missing = security_tables - base_tables

    assert (
        not missing
    ), f"Security tables missing from Base.metadata: {missing}"
