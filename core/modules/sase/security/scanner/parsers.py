"""Security scan result parsers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog

from .core import ScanFinding, ScanSeverity

logger = structlog.get_logger()


def parse_trivy_results(scan_id: str, trivy_results: dict[str, Any], target: str) -> list[ScanFinding]:
    """Parse Trivy scan results.

    Args:
        scan_id: Scan ID.
        trivy_results: Trivy output in JSON format.
        target: Target that was scanned.

    Returns:
        List of findings from Trivy results.
    """
    findings = []

    try:
        results = trivy_results.get("Results", [])
        for result in results:
            vulnerabilities = result.get("Vulnerabilities", [])

            for vuln in vulnerabilities:
                severity_map = {
                    "CRITICAL": ScanSeverity.CRITICAL,
                    "HIGH": ScanSeverity.HIGH,
                    "MEDIUM": ScanSeverity.MEDIUM,
                    "LOW": ScanSeverity.LOW,
                    "UNKNOWN": ScanSeverity.INFO,
                }

                findings.append(
                    ScanFinding(
                        scan_id=scan_id,
                        finding_type="vulnerability",
                        severity=severity_map.get(vuln.get("Severity", "UNKNOWN"), ScanSeverity.INFO),
                        title=vuln.get("Title", "Unknown Vulnerability"),
                        description=vuln.get("Description", ""),
                        affected_component=f"{target}:{vuln.get('PkgName', 'unknown')}",
                        recommendation=vuln.get("FixedVersion", "Update to latest version"),
                        cve_ids=[vuln.get("VulnerabilityID", "")],
                        cvss_score=float(vuln.get("CVSS", {}).get("nvd", {}).get("V3Score", 0)),
                        confidence=90,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        metadata={
                            "package": vuln.get("PkgName"),
                            "installed_version": vuln.get("InstalledVersion"),
                            "fixed_version": vuln.get("FixedVersion"),
                            "references": vuln.get("References", []),
                        },
                    )
                )

    except Exception as e:
        logger.error("Error parsing Trivy results", error=str(e), exc_info=True)

    return findings


def parse_safety_results(scan_id: str, safety_results: list[dict[str, Any]]) -> list[ScanFinding]:
    """Parse Safety dependency check results.

    Args:
        scan_id: Scan ID.
        safety_results: Safety output.

    Returns:
        List of findings from Safety results.
    """
    findings = []

    try:
        for vuln in safety_results:
            findings.append(
                ScanFinding(
                    scan_id=scan_id,
                    finding_type="dependency_vulnerability",
                    severity=ScanSeverity.HIGH,
                    title=f"Vulnerable dependency: {vuln.get('package', 'unknown')}",
                    description=vuln.get("advisory", ""),
                    affected_component=f"python:{vuln.get('package', 'unknown')}",
                    recommendation=f"Update {vuln.get('package')} to version {vuln.get('safe_version', 'latest')}",
                    cve_ids=[vuln.get("cve", "")],
                    cvss_score=7.0,
                    confidence=85,
                    first_seen=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                    metadata={
                        "package": vuln.get("package"),
                        "installed_version": vuln.get("installed_version"),
                        "safe_version": vuln.get("safe_version"),
                        "vulnerability_id": vuln.get("v"),
                    },
                )
            )

    except Exception as e:
        logger.error("Error parsing Safety results", error=str(e), exc_info=True)

    return findings


def parse_govulncheck_results(scan_id: str, output: str) -> list[ScanFinding]:
    """Parse govulncheck results.

    Args:
        scan_id: Scan ID.
        output: govulncheck output text.

    Returns:
        List of findings from govulncheck results.
    """
    findings = []

    try:
        # Parse govulncheck text output
        lines = output.split("\n")
        for line in lines:
            if "Vulnerability" in line or "vulnerability" in line:
                findings.append(
                    ScanFinding(
                        scan_id=scan_id,
                        finding_type="go_dependency_vulnerability",
                        severity=ScanSeverity.HIGH,
                        title="Go dependency vulnerability detected",
                        description=line,
                        affected_component="go",
                        recommendation="Review and update vulnerable dependencies",
                        cve_ids=[],
                        cvss_score=7.0,
                        confidence=80,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        metadata={"raw_output": line},
                    )
                )

    except Exception as e:
        logger.error("Error parsing govulncheck results", error=str(e), exc_info=True)

    return findings


def parse_docker_bench_results(scan_id: str, output: str) -> list[ScanFinding]:
    """Parse Docker Bench Security results.

    Args:
        scan_id: Scan ID.
        output: Docker Bench output text.

    Returns:
        List of findings from Docker Bench results.
    """
    findings = []

    try:
        lines = output.split("\n")
        current_section = None

        for line in lines:
            # Parse docker-bench output format
            if line.startswith("[WARN]"):
                findings.append(
                    ScanFinding(
                        scan_id=scan_id,
                        finding_type="docker_configuration",
                        severity=ScanSeverity.MEDIUM,
                        title="Docker security warning",
                        description=line.replace("[WARN]", "").strip(),
                        affected_component="docker",
                        recommendation="Review and fix Docker configuration",
                        cve_ids=[],
                        cvss_score=5.0,
                        confidence=85,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        metadata={"raw_line": line},
                    )
                )
            elif line.startswith("[FAIL]"):
                findings.append(
                    ScanFinding(
                        scan_id=scan_id,
                        finding_type="docker_configuration",
                        severity=ScanSeverity.HIGH,
                        title="Docker security failure",
                        description=line.replace("[FAIL]", "").strip(),
                        affected_component="docker",
                        recommendation="Immediately fix Docker security issue",
                        cve_ids=[],
                        cvss_score=7.0,
                        confidence=90,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        metadata={"raw_line": line},
                    )
                )

    except Exception as e:
        logger.error("Error parsing Docker Bench results", error=str(e), exc_info=True)

    return findings


def count_findings_by_severity(findings: list[ScanFinding]) -> dict[str, int]:
    """Count findings by severity level.

    Args:
        findings: List of scan findings.

    Returns:
        Dictionary with severity counts.
    """
    counts = {}
    for finding in findings:
        severity = finding.severity.value
        counts[severity] = counts.get(severity, 0) + 1
    return counts
