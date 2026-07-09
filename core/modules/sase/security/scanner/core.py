"""Core security scanner class."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class ScanType(Enum):
    """Types of security scans."""

    VULNERABILITY_SCAN = "vulnerability_scan"
    PORT_SCAN = "port_scan"
    DEPENDENCY_SCAN = "dependency_scan"
    CONTAINER_SCAN = "container_scan"
    CONFIGURATION_SCAN = "configuration_scan"
    THREAT_INTEL_SCAN = "threat_intel_scan"
    COMPLIANCE_SCAN = "compliance_scan"


class ScanSeverity(Enum):
    """Security scan severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(slots=True)
class ScanFinding:
    """Security scan finding."""

    scan_id: str
    finding_type: str
    severity: ScanSeverity
    title: str
    description: str
    affected_component: str
    recommendation: str
    cve_ids: list[str]
    cvss_score: float
    confidence: int
    first_seen: datetime
    last_seen: datetime
    metadata: dict[str, Any]


class SecurityScanner:
    """Automated security scanning pipeline."""

    def __init__(self, db: Any, tenant_id: str | None = None) -> None:
        """Initialize security scanner.

        Args:
            db: penguin-dal DAL instance for database operations.
            tenant_id: Optional tenant ID for scoped operations.
        """
        self.db = db
        self.tenant_id = tenant_id
        self.docker_client = None

        # Scanner configurations
        self.scan_configs = {
            ScanType.VULNERABILITY_SCAN: {
                "tools": ["trivy", "grype", "clair"],
                "schedule": "0 2 * * *",  # Daily at 2 AM
                "timeout": 3600,  # 1 hour
                "enabled": True,
            },
            ScanType.PORT_SCAN: {
                "tools": ["nmap"],
                "schedule": "0 3 * * 0",  # Weekly on Sunday at 3 AM
                "timeout": 1800,  # 30 minutes
                "enabled": True,
            },
            ScanType.DEPENDENCY_SCAN: {
                "tools": ["safety", "audit", "govulncheck"],
                "schedule": "0 1 * * *",  # Daily at 1 AM
                "timeout": 900,  # 15 minutes
                "enabled": True,
            },
            ScanType.CONTAINER_SCAN: {
                "tools": ["trivy", "docker-bench"],
                "schedule": "0 4 * * *",  # Daily at 4 AM
                "timeout": 1800,  # 30 minutes
                "enabled": True,
            },
            ScanType.CONFIGURATION_SCAN: {
                "tools": ["kube-bench", "inspec"],
                "schedule": "0 5 * * 0",  # Weekly on Sunday at 5 AM
                "timeout": 900,  # 15 minutes
                "enabled": True,
            },
            ScanType.THREAT_INTEL_SCAN: {
                "tools": ["custom"],
                "schedule": "*/15 * * * *",  # Every 15 minutes
                "timeout": 300,  # 5 minutes
                "enabled": True,
            },
            ScanType.COMPLIANCE_SCAN: {
                "tools": ["kube-bench", "docker-bench", "inspec"],
                "schedule": "0 6 * * 0",  # Weekly on Sunday at 6 AM
                "timeout": 1800,  # 30 minutes
                "enabled": True,
            },
        }

        # Initialize Docker client (optional)
        try:
            import docker

            self.docker_client = docker.from_env()
        except Exception:
            logger.warning("Could not initialize Docker client", exc_info=True)

    async def start_scanning_pipeline(self) -> None:
        """Start the automated security scanning pipeline."""
        logger.info("Starting automated security scanning pipeline")

        # Start background tasks
        tasks = [
            self._schedule_scans(),
            self._monitor_infrastructure(),
            self._process_threat_intelligence(),
        ]

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("Scanning pipeline cancelled")

    async def _schedule_scans(self) -> None:
        """Schedule and execute security scans."""
        while True:
            try:
                # Run scans based on configuration
                for scan_type, config in self.scan_configs.items():
                    if not config.get("enabled", True):
                        continue

                    # Check if it's time to run this scan type
                    if await self._should_run_scan(scan_type, config):
                        await self._execute_scan(scan_type, config)

                # Wait before next check
                await asyncio.sleep(300)  # 5 minutes

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in scan scheduler", error=str(e), exc_info=True)
                await asyncio.sleep(60)

    async def _monitor_infrastructure(self) -> None:
        """Monitor infrastructure for new components to scan."""
        while True:
            try:
                # Monitor Docker containers
                if self.docker_client:
                    await self._scan_new_containers()

                # Monitor Kubernetes resources
                await self._scan_kubernetes_resources()

                # Monitor network services
                await self._scan_network_services()

                # Wait before next monitoring cycle
                await asyncio.sleep(1800)  # 30 minutes

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in infrastructure monitoring", error=str(e), exc_info=True)
                await asyncio.sleep(300)

    async def _process_threat_intelligence(self) -> None:
        """Process threat intelligence and scan for indicators."""
        while True:
            try:
                # Scan logs for threat indicators
                await self._scan_logs_for_threats()

                # Scan network traffic for threats
                await self._scan_network_threats()

                # Cross-reference with threat feeds
                await self._correlate_with_threat_feeds()

                # Wait before next threat intel cycle
                await asyncio.sleep(900)  # 15 minutes

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in threat intelligence processing",
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(300)

    async def _should_run_scan(self, scan_type: ScanType, config: dict[str, Any]) -> bool:
        """Check if a scan should be run based on schedule.

        Args:
            scan_type: Type of scan to check.
            config: Scan configuration.

        Returns:
            True if scan should run, False otherwise.
        """
        # Get last scan time - tenant-scoped query
        try:
            query_filters = [
                ("scan_type", "==", scan_type.value),
                ("status", "==", "completed"),
            ]
            if self.tenant_id:
                query_filters.append(("tenant_id", "==", self.tenant_id))

            last_scan = await self.db.execute_query(
                "security_scans",
                filters=query_filters,
                order_by="-completed_at",
                limit=1,
            )

            if not last_scan:
                return True  # Never run before

            # Calculate next run time based on schedule
            schedule = config.get("schedule", "0 2 * * *")  # Default daily at 2 AM
            last_completed = last_scan[0].get("completed_at") or datetime.utcnow()

            # Simple schedule parsing
            if schedule == "0 2 * * *":  # Daily
                next_run = last_completed + timedelta(days=1)
            elif schedule == "0 3 * * 0":  # Weekly
                next_run = last_completed + timedelta(weeks=1)
            elif schedule == "*/15 * * * *":  # Every 15 minutes
                next_run = last_completed + timedelta(minutes=15)
            else:
                next_run = last_completed + timedelta(hours=24)  # Default daily

            return datetime.utcnow() >= next_run

        except Exception as e:
            logger.error("Error checking scan schedule", error=str(e), exc_info=True)
            return True

    async def _execute_scan(self, scan_type: ScanType, config: dict[str, Any]) -> None:
        """Execute a security scan.

        Args:
            scan_type: Type of scan to execute.
            config: Scan configuration.
        """
        from .scans import execute_scan_by_type
        from .parsers import count_findings_by_severity
        from .models import SecurityScan, SecurityFinding

        scan_id = f"scan_{scan_type.value}_{int(datetime.utcnow().timestamp())}"

        try:
            logger.info("Starting scan", scan_type=scan_type.value, scan_id=scan_id)

            # Record scan start
            scan_start = datetime.utcnow()
            scan_record = {
                "scan_id": scan_id,
                "tenant_id": self.tenant_id or "system",
                "scan_type": scan_type.value,
                "target": "infrastructure",
                "tools_used": json.dumps(config.get("tools", [])),
                "status": "running",
                "started_at": scan_start,
                "triggered_by": "automated",
                "metadata": json.dumps({"config": config}),
            }

            try:
                await self.db.execute_insert("security_scans", scan_record)
            except Exception:
                logger.debug("Could not record scan start", exc_info=True)

            # Execute scan based on type
            findings = await execute_scan_by_type(scan_type, scan_id, self)

            # Store findings
            for finding in findings:
                await self._store_finding(finding)

            # Update scan record
            severity_counts = count_findings_by_severity(findings)
            scan_duration = int((datetime.utcnow() - scan_start).total_seconds())

            try:
                await self.db.execute_update(
                    "security_scans",
                    filters=[("scan_id", "==", scan_id)],
                    values={
                        "status": "completed",
                        "findings_count": len(findings),
                        "critical_findings": severity_counts.get("critical", 0),
                        "high_findings": severity_counts.get("high", 0),
                        "medium_findings": severity_counts.get("medium", 0),
                        "low_findings": severity_counts.get("low", 0),
                        "completed_at": datetime.utcnow(),
                        "scan_duration": scan_duration,
                    },
                )
            except Exception:
                logger.debug("Could not update scan record", exc_info=True)

            logger.info(
                "Completed scan",
                scan_type=scan_type.value,
                scan_id=scan_id,
                findings_count=len(findings),
            )

        except Exception as e:
            logger.error("Failed scan", scan_type=scan_type.value, scan_id=scan_id, error=str(e))

            # Update scan record with error
            try:
                await self.db.execute_update(
                    "security_scans",
                    filters=[("scan_id", "==", scan_id)],
                    values={
                        "status": "failed",
                        "error_message": str(e),
                        "completed_at": datetime.utcnow(),
                    },
                )
            except Exception:
                logger.debug("Could not update failed scan record", exc_info=True)

    async def _store_finding(self, finding: ScanFinding) -> None:
        """Store a security finding in the database.

        Args:
            finding: Finding to store.
        """
        try:
            finding_id = f"finding_{finding.scan_id}_{hash(finding.title)}_{int(datetime.utcnow().timestamp())}"

            record = {
                "finding_id": finding_id,
                "scan_id": finding.scan_id,
                "tenant_id": self.tenant_id or "system",
                "finding_type": finding.finding_type,
                "severity": finding.severity.value,
                "title": finding.title,
                "description": finding.description,
                "affected_component": finding.affected_component,
                "recommendation": finding.recommendation,
                "cve_ids": json.dumps(finding.cve_ids),
                "cvss_score": finding.cvss_score,
                "confidence": finding.confidence,
                "first_seen": finding.first_seen,
                "last_seen": finding.last_seen,
                "metadata": json.dumps(finding.metadata),
            }

            await self.db.execute_insert("security_findings", record)

        except Exception as e:
            logger.error("Failed to store finding", error=str(e), exc_info=True)

    # Placeholder methods for infrastructure monitoring
    async def _scan_new_containers(self) -> None:
        """Scan for new containers."""

    async def _scan_kubernetes_resources(self) -> None:
        """Scan Kubernetes resources."""

    async def _scan_network_services(self) -> None:
        """Scan network services."""

    async def _scan_logs_for_threats(self) -> None:
        """Scan logs for threat indicators."""

    async def _scan_network_threats(self) -> None:
        """Scan network traffic for threats."""

    async def _correlate_with_threat_feeds(self) -> None:
        """Correlate findings with threat feeds."""
