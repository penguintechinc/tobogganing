"""Integration tests for backup, scanner, and ratelimit using real_dal fixture."""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from hub_api.core.backup.manager import BackupManager
from hub_api.modules.sase.security.protection.ratelimit import RateLimiter
from hub_api.modules.sase.security.scanner.core import ScanFinding, ScanSeverity, ScanType, SecurityScanner


@pytest.mark.asyncio
async def test_backup_create_and_restore(real_dal: Any) -> None:
    """Test backup create and restore operations with real_dal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = BackupManager(real_dal, backup_dir=tmpdir)

        # Create backup
        backup_result = await manager.create_backup(
            backup_name="test_backup_001",
            compress=False,
            encrypt=False,
            tenant_id="test-tenant-1",
        )

        assert backup_result["backup_name"] == "test_backup_001"
        assert backup_result["compressed"] is False
        assert backup_result["encrypted"] is False
        assert "file_path" in backup_result

        # List backups
        backups = manager.list_backups(include_s3=False, tenant_id="test-tenant-1")
        assert len(backups) > 0
        assert any(b["backup_name"] == "test_backup_001" for b in backups)

        # Restore backup
        restore_result = await manager.restore_backup(
            backup_path=backup_result["file_path"],
            decrypt=False,
            from_s3=False,
            tenant_id="test-tenant-1",
        )

        assert restore_result["total_rows_restored"] >= 0
        assert "tables_restored" in restore_result


@pytest.mark.asyncio
async def test_backup_tenant_isolation(real_dal: Any) -> None:
    """Test backup tenant isolation - different tenants cannot access each other's backups."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager1 = BackupManager(real_dal, backup_dir=tmpdir)
        manager2 = BackupManager(real_dal, backup_dir=tmpdir)

        # Create backup for tenant-1
        result1 = await manager1.create_backup(
            backup_name="tenant1_backup",
            compress=False,
            tenant_id="tenant-1",
        )

        # List backups for tenant-1
        backups_t1 = manager1.list_backups(include_s3=False, tenant_id="tenant-1")
        assert any(b["backup_name"] == "tenant1_backup" for b in backups_t1)

        # List backups for tenant-2 (should not see tenant-1's backup)
        backups_t2 = manager2.list_backups(include_s3=False, tenant_id="tenant-2")
        assert not any(b["backup_name"] == "tenant1_backup" for b in backups_t2)


@pytest.mark.asyncio
async def test_security_scanner_store_finding(real_dal: Any) -> None:
    """Test security scanner storing findings in real_dal."""
    scanner = SecurityScanner(real_dal, tenant_id="test-tenant-1")

    # Create and store a finding
    finding = ScanFinding(
        scan_id="scan_test_001",
        finding_type="vulnerability",
        severity=ScanSeverity.HIGH,
        title="Test Vulnerability",
        description="This is a test vulnerability",
        affected_component="test-component",
        recommendation="Fix immediately",
        cve_ids=["CVE-2025-0001"],
        cvss_score=8.5,
        confidence=90,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        metadata={"source": "test"},
    )

    await scanner._store_finding(finding)

    # Verify finding was stored (query the database)
    findings = await real_dal(
        (real_dal.security_findings.scan_id == "scan_test_001")
        & (real_dal.security_findings.tenant_id == "test-tenant-1")
    ).select()

    stored_finding = findings.first()
    assert stored_finding is not None
    assert stored_finding.finding_type == "vulnerability"
    assert stored_finding.severity == "high"


@pytest.mark.asyncio
async def test_security_scanner_tenant_isolation(real_dal: Any) -> None:
    """Test security scanner tenant isolation."""
    scanner1 = SecurityScanner(real_dal, tenant_id="tenant-1")
    scanner2 = SecurityScanner(real_dal, tenant_id="tenant-2")

    # Store finding for tenant-1
    finding1 = ScanFinding(
        scan_id="scan_tenant1",
        finding_type="vulnerability",
        severity=ScanSeverity.CRITICAL,
        title="Critical Issue",
        description="Critical issue in tenant-1",
        affected_component="component-1",
        recommendation="Fix",
        cve_ids=[],
        cvss_score=9.0,
        confidence=95,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        metadata={},
    )

    await scanner1._store_finding(finding1)

    # Query findings for tenant-1
    findings_t1 = await real_dal(
        real_dal.security_findings.tenant_id == "tenant-1"
    ).select()
    assert findings_t1.first() is not None

    # Query findings for tenant-2 (should be empty)
    findings_t2 = await real_dal(
        real_dal.security_findings.tenant_id == "tenant-2"
    ).select()
    assert findings_t2.first() is None


@pytest.mark.asyncio
async def test_rate_limiter_load_custom_rules(real_dal: Any) -> None:
    """Test rate limiter loading custom rules from database."""
    limiter = RateLimiter(real_dal, tenant_id="test-tenant")

    # Insert a custom rule
    rule_id = str(uuid4())
    await real_dal.rate_limit_rules.async_insert(
        name="custom_strict_rule",
        max_requests=5,
        window_seconds=60,
        block_duration=600,
        endpoints=["/api/custom/"],
        exempt_ips=["127.0.0.1"],
        priority=1,
        enabled=True,
        tenant_id="test-tenant",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Load custom rules
    await limiter.load_custom_rules()

    # Verify custom rule was loaded
    rule_names = [r.name for r in limiter.rules]
    assert "custom_strict_rule" in rule_names


@pytest.mark.asyncio
async def test_rate_limiter_log_security_event(real_dal: Any) -> None:
    """Test rate limiter logging security events to database."""
    limiter = RateLimiter(real_dal, tenant_id="test-tenant")

    # Log a security event
    await limiter._log_security_event(
        event_type="rate_limit_violation",
        ip_address="192.168.1.100",
        endpoint="/api/test/",
        user_agent="Mozilla/5.0",
        severity="high",
        details={"rule": "test_rule", "requests": 100},
    )

    # Verify event was stored
    events = await real_dal(
        (real_dal.security_events.event_type == "rate_limit_violation")
        & (real_dal.security_events.tenant_id == "test-tenant")
    ).select()

    event = events.first()
    assert event is not None
    assert event.ip_address == "192.168.1.100"
    assert event.severity == "high"


@pytest.mark.asyncio
async def test_rate_limiter_tenant_isolation(real_dal: Any) -> None:
    """Test rate limiter tenant isolation for security events."""
    limiter1 = RateLimiter(real_dal, tenant_id="tenant-1")
    limiter2 = RateLimiter(real_dal, tenant_id="tenant-2")

    # Log event for tenant-1
    await limiter1._log_security_event(
        event_type="test_event",
        ip_address="10.0.0.1",
        endpoint="/test/",
        user_agent="test",
        severity="medium",
        details={},
    )

    # Query events for tenant-1
    events_t1 = await real_dal(
        real_dal.security_events.tenant_id == "tenant-1"
    ).select()
    assert events_t1.first() is not None

    # Query events for tenant-2 (should not see tenant-1's event)
    events_t2 = await real_dal(
        real_dal.security_events.tenant_id == "tenant-2"
    ).select()
    # Tenant-2 should not have any events from tenant-1
    for event in events_t2:
        assert event.ip_address != "10.0.0.1"


@pytest.mark.asyncio
async def test_backup_with_datetime_handling(real_dal: Any) -> None:
    """Test backup handles datetime serialization/deserialization correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = BackupManager(real_dal, backup_dir=tmpdir)

        # Create backup
        backup_result = await manager.create_backup(
            backup_name="datetime_test",
            compress=False,
        )

        assert "file_path" in backup_result
        backup_file = Path(backup_result["file_path"])

        # Read backup file and verify datetime serialization
        with open(backup_file, "r") as f:
            backup_data = json.load(f)

        # Verify metadata timestamps are ISO format strings
        assert "metadata" in backup_data
        assert "created_at" in backup_data["metadata"]
        assert isinstance(backup_data["metadata"]["created_at"], str)
        # Should be parseable as ISO datetime
        datetime.fromisoformat(backup_data["metadata"]["created_at"])


@pytest.mark.asyncio
async def test_rate_limiter_is_allowed_basic(real_dal: Any) -> None:
    """Test rate limiter is_allowed basic functionality."""
    limiter = RateLimiter(real_dal, tenant_id="test-tenant")

    # Make a single request - should be allowed
    allowed, rule, retry_after = await limiter.is_allowed(
        "203.0.113.50",
        "/api/auth/login",  # This endpoint matches the auth_strict rule (max 5 requests per 60s)
        "test-agent",
    )

    assert allowed is True
    assert retry_after == 0
    assert rule is None  # No rule violated
