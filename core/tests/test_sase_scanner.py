"""Tests for SASE security scanner module."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.modules.sase.security.scanner.core import (
    ScanFinding,
    ScanSeverity,
    ScanType,
    SecurityScanner,
)
from core.modules.sase.security.scanner.parsers import (
    count_findings_by_severity,
    parse_docker_bench_results,
    parse_govulncheck_results,
    parse_safety_results,
    parse_trivy_results,
)
from core.modules.sase.security.scanner.scans import (
    _extract_domains_from_log,
    _extract_ips_from_log,
)


class TestScanEnums:
    """Test scan type and severity enums."""

    def test_scan_types_exist(self) -> None:
        """Verify all scan types are defined."""
        assert ScanType.VULNERABILITY_SCAN.value == "vulnerability_scan"
        assert ScanType.PORT_SCAN.value == "port_scan"
        assert ScanType.DEPENDENCY_SCAN.value == "dependency_scan"
        assert ScanType.CONTAINER_SCAN.value == "container_scan"
        assert ScanType.CONFIGURATION_SCAN.value == "configuration_scan"
        assert ScanType.THREAT_INTEL_SCAN.value == "threat_intel_scan"
        assert ScanType.COMPLIANCE_SCAN.value == "compliance_scan"

    def test_severity_levels_exist(self) -> None:
        """Verify all severity levels are defined."""
        assert ScanSeverity.CRITICAL.value == "critical"
        assert ScanSeverity.HIGH.value == "high"
        assert ScanSeverity.MEDIUM.value == "medium"
        assert ScanSeverity.LOW.value == "low"
        assert ScanSeverity.INFO.value == "info"


class TestScanFinding:
    """Test ScanFinding dataclass."""

    def test_scan_finding_creation(self) -> None:
        """Test creating a ScanFinding."""
        now = datetime.utcnow()
        finding = ScanFinding(
            scan_id="scan_123",
            finding_type="vulnerability",
            severity=ScanSeverity.HIGH,
            title="Test Vulnerability",
            description="Test description",
            affected_component="test-component",
            recommendation="Fix it",
            cve_ids=["CVE-2021-1234"],
            cvss_score=7.5,
            confidence=85,
            first_seen=now,
            last_seen=now,
            metadata={"test": "data"},
        )

        assert finding.scan_id == "scan_123"
        assert finding.finding_type == "vulnerability"
        assert finding.severity == ScanSeverity.HIGH
        assert finding.cvss_score == 7.5

    def test_scan_finding_slots(self) -> None:
        """Test that ScanFinding uses slots for memory efficiency."""
        finding = ScanFinding(
            scan_id="scan_123",
            finding_type="vulnerability",
            severity=ScanSeverity.HIGH,
            title="Test",
            description="Test",
            affected_component="test",
            recommendation="Fix",
            cve_ids=[],
            cvss_score=5.0,
            confidence=80,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            metadata={},
        )

        # Should not be able to add arbitrary attributes due to slots
        with pytest.raises(AttributeError):
            finding.extra_attr = "value"  # type: ignore


class TestSecurityScanner:
    """Test SecurityScanner class."""

    def test_scanner_initialization(self) -> None:
        """Test scanner initialization."""
        mock_db = MagicMock()
        scanner = SecurityScanner(mock_db, tenant_id="tenant_123")

        assert scanner.db == mock_db
        assert scanner.tenant_id == "tenant_123"
        assert len(scanner.scan_configs) == 7

    def test_scanner_init_without_tenant(self) -> None:
        """Test scanner initialization without tenant."""
        mock_db = MagicMock()
        scanner = SecurityScanner(mock_db)

        assert scanner.db == mock_db
        assert scanner.tenant_id is None

    def test_scan_configs_structure(self) -> None:
        """Test that scan configurations are properly structured."""
        mock_db = MagicMock()
        scanner = SecurityScanner(mock_db)

        for scan_type, config in scanner.scan_configs.items():
            assert "tools" in config
            assert "schedule" in config
            assert "timeout" in config
            assert "enabled" in config
            assert isinstance(config["tools"], list)
            assert isinstance(config["timeout"], int)


class TestParsers:
    """Test result parsers."""

    def test_parse_trivy_results(self) -> None:
        """Test parsing Trivy vulnerability results."""
        trivy_output = {
            "Results": [
                {
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2021-1234",
                            "Title": "Test Vulnerability",
                            "Description": "Test description",
                            "Severity": "HIGH",
                            "PkgName": "test-package",
                            "InstalledVersion": "1.0.0",
                            "FixedVersion": "1.1.0",
                            "CVSS": {"nvd": {"V3Score": 7.5}},
                            "References": ["https://example.com"],
                        }
                    ]
                }
            ]
        }

        findings = parse_trivy_results("scan_123", trivy_output, "target_image")

        assert len(findings) == 1
        assert findings[0].finding_type == "vulnerability"
        assert findings[0].severity == ScanSeverity.HIGH
        assert findings[0].cvss_score == 7.5
        assert "test-package" in findings[0].affected_component

    def test_parse_safety_results(self) -> None:
        """Test parsing Safety dependency results."""
        safety_output = [
            {
                "package": "vulnerable-lib",
                "installed_version": "1.0.0",
                "safe_version": "1.2.0",
                "advisory": "Security vulnerability in lib",
                "cve": "CVE-2021-5678",
                "v": "12345",
            }
        ]

        findings = parse_safety_results("scan_123", safety_output)

        assert len(findings) == 1
        assert findings[0].finding_type == "dependency_vulnerability"
        assert "vulnerable-lib" in findings[0].affected_component
        assert findings[0].severity == ScanSeverity.HIGH

    def test_parse_govulncheck_results(self) -> None:
        """Test parsing govulncheck results."""
        output = "GO Vulnerability: module.v1\nVulnerability ID: GO-2021-0000"

        findings = parse_govulncheck_results("scan_123", output)

        assert any(f.finding_type == "go_dependency_vulnerability" for f in findings)

    def test_parse_docker_bench_results(self) -> None:
        """Test parsing Docker Bench results."""
        output = "[WARN] 1.1.1 Check warning\n[FAIL] 2.1.1 Check failure\n[PASS] 3.1.1 Check passed"

        findings = parse_docker_bench_results("scan_123", output)

        warnings = [f for f in findings if f.severity == ScanSeverity.MEDIUM]
        failures = [f for f in findings if f.severity == ScanSeverity.HIGH]

        assert len(warnings) == 1
        assert len(failures) == 1

    def test_count_findings_by_severity(self) -> None:
        """Test counting findings by severity."""
        now = datetime.utcnow()
        findings = [
            ScanFinding(
                scan_id="scan_123",
                finding_type="vuln",
                severity=ScanSeverity.CRITICAL,
                title="C1",
                description="",
                affected_component="",
                recommendation="",
                cve_ids=[],
                cvss_score=0,
                confidence=0,
                first_seen=now,
                last_seen=now,
                metadata={},
            ),
            ScanFinding(
                scan_id="scan_123",
                finding_type="vuln",
                severity=ScanSeverity.HIGH,
                title="H1",
                description="",
                affected_component="",
                recommendation="",
                cve_ids=[],
                cvss_score=0,
                confidence=0,
                first_seen=now,
                last_seen=now,
                metadata={},
            ),
            ScanFinding(
                scan_id="scan_123",
                finding_type="vuln",
                severity=ScanSeverity.HIGH,
                title="H2",
                description="",
                affected_component="",
                recommendation="",
                cve_ids=[],
                cvss_score=0,
                confidence=0,
                first_seen=now,
                last_seen=now,
                metadata={},
            ),
        ]

        counts = count_findings_by_severity(findings)

        assert counts["critical"] == 1
        assert counts["high"] == 2


class TestLogExtraction:
    """Test log line parsing utilities."""

    def test_extract_ips_from_log(self) -> None:
        """Test IP extraction from log lines."""
        log_line = "Connection from 192.168.1.1 to 10.0.0.5"
        ips = _extract_ips_from_log(log_line)

        assert "192.168.1.1" in ips
        assert "10.0.0.5" in ips

    def test_extract_domains_from_log(self) -> None:
        """Test domain extraction from log lines."""
        log_line = "Request to example.com and test-domain.org from client"
        domains = _extract_domains_from_log(log_line)

        assert "example.com" in domains
        assert "test-domain.org" in domains

    def test_extract_no_ips(self) -> None:
        """Test extraction when no IPs present."""
        log_line = "Normal log message without IPs"
        ips = _extract_ips_from_log(log_line)

        assert len(ips) == 0

    def test_extract_no_domains(self) -> None:
        """Test extraction when no domains present."""
        log_line = "Log message with 192.168.1.1 but no domains"
        domains = _extract_domains_from_log(log_line)

        assert len(domains) == 0


class TestScannerAsync:
    """Test async scanner functionality."""

    @pytest.mark.asyncio
    async def test_should_run_scan_on_first_run(self) -> None:
        """Test that scan should run if never run before."""
        mock_db = AsyncMock()
        mock_db.execute_query = AsyncMock(return_value=[])

        scanner = SecurityScanner(mock_db, tenant_id="tenant_123")
        config = scanner.scan_configs[ScanType.VULNERABILITY_SCAN]

        should_run = await scanner._should_run_scan(ScanType.VULNERABILITY_SCAN, config)

        assert should_run is True



class TestTenantScoping:
    """Test tenant scoping in scanner operations."""

    def test_scanner_tenant_scoping_on_init(self) -> None:
        """Test that tenant_id is stored for scoped queries."""
        mock_db = MagicMock()
        tenant_id = "org_abc123"
        scanner = SecurityScanner(mock_db, tenant_id=tenant_id)

        assert scanner.tenant_id == tenant_id

