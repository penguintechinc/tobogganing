"""Test that migrations create all Base.metadata tables."""

from __future__ import annotations

from hub_api.db.base import Base
from hub_api.db.models import (
    VRF,
    AlertEvent,
    AlertRule,
    AutoCheckIn,
    AutoCheckInState,
    AutoPerfPolicy,
    AutoPerfState,
    C2CEndpoint,
    C2CMatrixRun,
    C2CPairResult,
    Client,
    ClientConfig,
    Cluster,
    Device,
    DeviceApiKey,
    DeviceEnrollmentSecret,
    DNSConfigVersion,
    DNSRecord,
    DNSResolverToken,
    DNSServer,
    DNSServerMetrics,
    DNSZone,
    FirewallRule,
    OrgUnit,
    OSPFArea,
    OSPFNeighbor,
    PasswordResetToken,
    PerfTestResult,
    PortRange,
    RefreshToken,
    ServerKey,
    Session,
    TestSchedule,
    User,
)
from hub_api.modules.sase.security.protection.models import (
    RateLimitRule,
    SecurityEvent,
)
from hub_api.modules.sase.security.scanner.models import (
    ScanSchedule,
    SecurityFinding,
    SecurityScan,
)
from hub_api.modules.threatintel.feeds.models import (
    FeedUpdate,
    ThreatDetection,
    ThreatIndicator,
)


def test_alembic_migrations_cover_all_tables() -> None:
    """Verify all Base.metadata tables are covered by migrations 0001-0025.

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
    Migration 0013: test_schedules
    Migration 0014: c2c_endpoints
    Migration 0015: c2c_matrix_runs, c2c_pair_results
    Migration 0016: scheduled_jobs
    Migration 0017: notification_channels, notification_deliveries
    Migration 0018: alert_rules, alert_events
    Migration 0019: autoperf_policies, autoperf_state
    Migration 0025: dns_zones, dns_records, dns_servers, dns_server_metrics,
                    dns_resolver_tokens, dns_config_versions
    Migration 0026: threatintel_feed_sources
    Migration 0027: auto_checkins, auto_checkin_state
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

    # Tables created by migrations 0010-0015 (WaddlePerf cluster tables + C2C)
    created_by_wpc_migrations = {
        "org_units",
        "devices",
        "device_api_keys",
        "device_enrollment_secrets",
        "perf_test_results",
        "client_configs",
        "server_keys",
        "test_schedules",
        "c2c_endpoints",
        "c2c_matrix_runs",
        "c2c_pair_results",
    }

    # Tables created by migrations 0016-0019 (core scheduler + notifications + alerts + autoperf)
    created_by_scheduler_migrations = {
        "scheduled_jobs",
        "notification_channels",
        "notification_deliveries",
        "alert_rules",
        "alert_events",
        "autoperf_policies",
        "autoperf_state",
    }

    # Tables created by migration 0025 (netsvcs control plane)
    created_by_migration_0025 = {
        "dns_zones",
        "dns_records",
        "dns_servers",
        "dns_server_metrics",
        "dns_resolver_tokens",
        "dns_config_versions",
    }

    # Tables created by migration 0026 (threatintel feed source management —
    # squawk-merge P5 wave A; regression: this test's table registry wasn't
    # updated when the migration landed, see hub_api/migrations/versions/
    # 0026_threatintel_feed_sources.py)
    created_by_migration_0026 = {
        "threatintel_feed_sources",
    }

    # Tables created by migration 0027 (Auto Check-in tier cascade — W2)
    created_by_migration_0027 = {
        "auto_checkins",
        "auto_checkin_state",
    }

    # All tables covered by migrations
    all_migration_tables = (
        created_by_existing_migrations
        | created_by_migration_0008
        | created_by_wpc_migrations
        | created_by_scheduler_migrations
        | created_by_migration_0025
        | created_by_migration_0026
        | created_by_migration_0027
    )

    # Verify coverage
    missing_tables = expected_tables - all_migration_tables
    assert not missing_tables, f"Missing from migrations: {missing_tables}"

    extra_tables = all_migration_tables - expected_tables
    assert not extra_tables, f"Migration tables not in Base.metadata: {extra_tables}"


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
        TestSchedule,
        C2CEndpoint,
        C2CMatrixRun,
        C2CPairResult,
        AlertRule,
        AlertEvent,
        AutoPerfPolicy,
        AutoPerfState,
        AutoCheckIn,
        AutoCheckInState,
        SecurityScan,
        SecurityFinding,
        ScanSchedule,
        SecurityEvent,
        RateLimitRule,
        ThreatIndicator,
        FeedUpdate,
        ThreatDetection,
        DNSZone,
        DNSRecord,
        DNSServer,
        DNSServerMetrics,
        DNSResolverToken,
        DNSConfigVersion,
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

    assert not missing, f"Security tables missing from Base.metadata: {missing}"
