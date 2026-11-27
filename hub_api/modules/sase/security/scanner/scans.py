"""Security scan implementations."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess  # nosec B404 - fixed-argv scanner tool invocations only
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from . import host_checks
from .core import ScanFinding, ScanSeverity, ScanType
from .host_checks import CheckIssue, CheckNotApplicable
from .parsers import (
    parse_docker_bench_results,
    parse_govulncheck_results,
    parse_safety_results,
    parse_trivy_results,
)
from .telemetry import (
    CHECK_RESULTS,
    INDICATORS_TRUNCATED,
    LOOKUP_DURATION,
    THREAT_LOOKUPS,
    ScannerDependencyError,
)

logger = structlog.get_logger()


async def execute_scan_by_type(
    scan_type: ScanType, scan_id: str, scanner: Any
) -> list[ScanFinding]:
    """Execute scan based on type.

    Args:
        scan_type: Type of scan to execute.
        scan_id: Unique scan ID.
        scanner: SecurityScanner instance.

    Returns:
        List of findings from the scan.
    """
    if scan_type == ScanType.VULNERABILITY_SCAN:
        return await _run_vulnerability_scan(scan_id, scanner)
    elif scan_type == ScanType.PORT_SCAN:
        return await _run_port_scan(scan_id, scanner)
    elif scan_type == ScanType.DEPENDENCY_SCAN:
        return await _run_dependency_scan(scan_id, scanner)
    elif scan_type == ScanType.CONTAINER_SCAN:
        return await _run_container_scan(scan_id, scanner)
    elif scan_type == ScanType.CONFIGURATION_SCAN:
        return await _run_configuration_scan(scan_id, scanner)
    elif scan_type == ScanType.THREAT_INTEL_SCAN:
        return await _run_threat_intel_scan(scan_id, scanner)
    elif scan_type == ScanType.COMPLIANCE_SCAN:
        return await _run_compliance_scan(scan_id, scanner)
    else:
        return []


async def _run_vulnerability_scan(scan_id: str, scanner: Any) -> list[ScanFinding]:
    """Run vulnerability scan using Trivy and other tools.

    Args:
        scan_id: Scan ID.
        scanner: SecurityScanner instance.

    Returns:
        List of vulnerability findings.
    """
    findings = []

    try:
        # Scan container images
        if scanner.docker_client:
            images = scanner.docker_client.images.list()
            for image in images[:5]:  # Limit to first 5 images
                try:
                    # Run Trivy scan
                    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, tools resolved via PATH in scanner image
                        ["trivy", "image", "--format", "json", "--quiet", image.id],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )

                    if result.returncode == 0 and result.stdout:
                        trivy_results = json.loads(result.stdout)
                        findings.extend(parse_trivy_results(scan_id, trivy_results, image.id))
                except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
                    logger.warning("Failed to scan image", image_id=image.id, error=str(e))
                except Exception as e:
                    logger.warning(
                        "Unexpected error scanning image", image_id=image.id, error=str(e)
                    )

        # Scan filesystem
        try:
            result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, tools resolved via PATH in scanner image
                ["trivy", "fs", "--format", "json", "--quiet", "/"],
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode == 0 and result.stdout:
                trivy_results = json.loads(result.stdout)
                findings.extend(parse_trivy_results(scan_id, trivy_results, "filesystem"))
        except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            logger.warning("Failed to scan filesystem", error=str(e))
        except Exception as e:
            logger.warning("Unexpected error in filesystem scan", error=str(e))

    except Exception as e:
        logger.error("Vulnerability scan failed", error=str(e))

    return findings


async def _run_port_scan(scan_id: str, scanner: Any) -> list[ScanFinding]:
    """Run port scan using Nmap.

    Args:
        scan_id: Scan ID.
        scanner: SecurityScanner instance.

    Returns:
        List of port scan findings.
    """
    findings = []

    try:
        try:
            import nmap
        except ImportError:
            logger.warning("nmap module not available")
            return findings

        nm = nmap.PortScanner()

        # Scan localhost
        nm.scan("127.0.0.1", "22,80,443,3306,6379,8080,8443")

        for host in nm.all_hosts():
            for protocol in nm[host].all_protocols():
                ports = nm[host][protocol].keys()

                for port in ports:
                    port_info = nm[host][protocol][port]

                    if port_info["state"] == "open":
                        # Check for potentially risky open ports
                        if port in [22, 3306, 6379] and host != "127.0.0.1":
                            findings.append(
                                ScanFinding(
                                    scan_id=scan_id,
                                    finding_type="open_port",
                                    severity=ScanSeverity.MEDIUM,
                                    title=f"Open {port_info.get('name', 'unknown')} port",
                                    description=f"Port {port} is open on {host}",
                                    affected_component=f"{host}:{port}",
                                    recommendation="Ensure port is properly secured and necessary",
                                    cve_ids=[],
                                    cvss_score=5.0,
                                    confidence=90,
                                    first_seen=datetime.utcnow(),
                                    last_seen=datetime.utcnow(),
                                    metadata={
                                        "host": host,
                                        "port": port,
                                        "protocol": protocol,
                                        "service": port_info.get("name", "unknown"),
                                        "state": port_info["state"],
                                    },
                                )
                            )

    except Exception as e:
        logger.error("Port scan failed", error=str(e))

    return findings


async def _run_dependency_scan(scan_id: str, scanner: Any) -> list[ScanFinding]:
    """Run dependency vulnerability scan.

    Args:
        scan_id: Scan ID.
        scanner: SecurityScanner instance.

    Returns:
        List of dependency scan findings.
    """
    findings = []

    try:
        # Check Python dependencies
        try:
            result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, tools resolved via PATH in scanner image
                ["safety", "check", "--json"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.stdout:
                safety_results = json.loads(result.stdout)
                findings.extend(parse_safety_results(scan_id, safety_results))
        except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            logger.warning("Safety check failed", error=str(e))
        except Exception as e:
            logger.warning("Unexpected error in safety check", error=str(e))

        # Check Go dependencies
        go_mod_path = Path("/go.mod")
        if go_mod_path.exists():
            try:
                result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, tools resolved via PATH in scanner image
                    ["govulncheck", "./..."],
                    cwd=go_mod_path.parent,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.stdout:
                    findings.extend(parse_govulncheck_results(scan_id, result.stdout))
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning("Govulncheck failed", error=str(e))
            except Exception as e:
                logger.warning("Unexpected error in govulncheck", error=str(e))

    except Exception as e:
        logger.error("Dependency scan failed", error=str(e))

    return findings


async def _run_container_scan(scan_id: str, scanner: Any) -> list[ScanFinding]:
    """Run container security scan.

    Args:
        scan_id: Scan ID.
        scanner: SecurityScanner instance.

    Returns:
        List of container scan findings.
    """
    findings = []

    try:
        # Run Docker Bench Security if available
        try:
            result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, tools resolved via PATH in scanner image
                [
                    "docker",
                    "run",
                    "--rm",
                    "--net",
                    "host",
                    "--pid",
                    "host",
                    "--userns",
                    "host",
                    "--cap-add",
                    "audit_control",
                    "-e",
                    f"DOCKER_CONTENT_TRUST={os.getenv('DOCKER_CONTENT_TRUST', '')}",
                    "-v",
                    "/etc:/etc:ro",
                    "-v",
                    "/var/lib:/var/lib:ro",
                    "-v",
                    "/var/run/docker.sock:/var/run/docker.sock:ro",
                    "docker/docker-bench-security",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.stdout:
                findings.extend(parse_docker_bench_results(scan_id, result.stdout))
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Docker bench scan failed", error=str(e))
        except Exception as e:
            logger.warning("Unexpected error in docker bench scan", error=str(e))

    except Exception as e:
        logger.error("Container scan failed", error=str(e))

    return findings


_CheckFn = Callable[[], list[CheckIssue]]

#: Configuration checks: (name, severity, function).
CONFIG_CHECKS: list[tuple[str, ScanSeverity, _CheckFn]] = [
    ("SSH Configuration", ScanSeverity.HIGH, lambda: host_checks.check_ssh_configuration()),
    ("File Permissions", ScanSeverity.MEDIUM, lambda: host_checks.check_file_permissions()),
    (
        "Service Configuration",
        ScanSeverity.MEDIUM,
        lambda: host_checks.check_service_configuration(),
    ),
]

#: Compliance controls: (framework, control, description, function).
COMPLIANCE_CHECKS: list[tuple[str, str, str, _CheckFn]] = [
    (
        "CIS",
        "1.1.1.1",
        "Ensure mounting of freevxfs filesystems is disabled",
        lambda: host_checks.check_cis_freevxfs_disabled(),
    ),
    ("NIST", "AC-2", "Account Management", lambda: host_checks.check_nist_ac2_accounts()),
    (
        "SOC2",
        "CC6.1",
        "Logical and Physical Access Controls",
        lambda: host_checks.check_soc2_cc61_logical_access(),
    ),
]

#: Tenant under which scheduled (global) threat feeds are stored by SecurityFeedsManager.
GLOBAL_FEED_TENANT = "00000000-0000-0000-0000-000000000000"

THREAT_LOG_FILES = [
    "/var/log/auth.log",
    "/var/log/nginx/access.log",
    "/var/log/app.log",
]


def _run_check(name: str, fn: _CheckFn, errors: list[str]) -> list[CheckIssue]:
    """Run one host check, recording its outcome as a metric and collecting errors.

    Not-applicable checks return no issues; any other exception is appended to
    ``errors`` so the caller can fail the scan after running the remaining checks.
    """
    try:
        issues = fn()
    except CheckNotApplicable as e:
        logger.info("scanner_check_not_applicable", check=name, reason=str(e))
        CHECK_RESULTS.add(1, {"check": name, "status": "not_applicable"})
        return []
    except Exception as e:  # noqa: BLE001 - recorded and re-raised by caller
        logger.error("scanner_check_error", check=name, error=str(e))
        CHECK_RESULTS.add(1, {"check": name, "status": "error"})
        errors.append(f"{name}: {e}")
        return []
    CHECK_RESULTS.add(1, {"check": name, "status": "fail" if issues else "pass"})
    return issues


async def _run_configuration_scan(scan_id: str, scanner: Any) -> list[ScanFinding]:
    """Run host configuration checks (sshd, account-file modes, Docker socket).

    Raises:
        ScannerDependencyError: if any check could not run (scan is recorded failed).
    """
    findings: list[ScanFinding] = []
    errors: list[str] = []
    now = datetime.utcnow()
    for name, severity, fn in CONFIG_CHECKS:
        for issue in _run_check(name, fn, errors):
            findings.append(
                ScanFinding(
                    scan_id=scan_id,
                    finding_type="configuration",
                    severity=severity,
                    title=f"Configuration Issue: {name}: {issue.title}",
                    description=issue.description,
                    affected_component=issue.component,
                    recommendation=issue.recommendation,
                    cve_ids=[],
                    cvss_score=7.0 if severity == ScanSeverity.HIGH else 5.0,
                    confidence=90,
                    first_seen=now,
                    last_seen=now,
                    metadata={"check": name, **issue.metadata},
                )
            )
    if errors:
        raise ScannerDependencyError("configuration checks failed: " + "; ".join(errors))
    return findings


#: Bytes read from the end of each log file per scan (bounded I/O).
LOG_TAIL_BYTES = 256 * 1024
#: Maximum unique indicators looked up per scan; excess is dropped loudly (metric + finding).
#: Sized above what 3 x 256KB tails can yield (~7 bytes per shortest IPv4 token) since
#: lookups are batched.
MAX_INDICATORS_PER_SCAN = 120_000
#: Maximum parent domains checked besides the exact name; the registrable end is always kept.
MAX_PARENT_DEPTH = 5
#: Values per ``IN (...)`` query chunk.
LOOKUP_BATCH_SIZE = 1000


def _normalize_domain(value: str) -> str | None:
    """Normalize a domain the way feed ingest stores it (lower-case, no trailing dot, IDNA).

    Returns None for values that cannot be IDNA-encoded.
    """
    name = value.strip().lower().rstrip(".")
    if not name:
        return None
    try:
        return name.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def _normalize_ip(value: str) -> str | None:
    """Return the canonical text form of an IP address, or None if invalid."""
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _domain_candidates(domain: str) -> list[str]:
    """Return ``domain`` plus its shortest parent domains (down to 2 labels).

    At most MAX_PARENT_DEPTH parents are kept, always the ones nearest the registrable
    end, so a deep subdomain still checks e.g. ``evil.com``.
    """
    labels = domain.split(".")
    parents = [".".join(labels[i:]) for i in range(1, len(labels) - 1)]
    return [domain] + parents[-MAX_PARENT_DEPTH:]


def _read_tail(path: str, max_bytes: int = LOG_TAIL_BYTES) -> list[str]:
    """Read at most ``max_bytes`` from the end of ``path`` and return whole lines."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        start = max(0, size - max_bytes)
        f.seek(start)
        data = f.read(max_bytes)
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # first line is partial
    return lines


def _row_to_match(row: Any) -> dict[str, Any]:
    """Convert a threat_indicators row into a match dict (value, types, source, confidence)."""
    raw_types = row.get("threat_types") if hasattr(row, "get") else row["threat_types"]
    try:
        types = json.loads(raw_types) if raw_types else []
    except (TypeError, ValueError):
        types = []
    return {
        "value": row["value"],
        "threat_types": types,
        "source": row["source"],
        "confidence": row["confidence"],
    }


async def _batch_lookup(
    db: Any, tenants: list[str], values: list[str], indicator_type: str
) -> dict[str, list[dict[str, Any]]]:
    """Look up ``values`` with one ``value IN (...)`` query per chunk across ``tenants``.

    Raises:
        ScannerDependencyError: when the threat-indicator store cannot be queried.
    """
    hits: dict[str, list[dict[str, Any]]] = {}
    if not values:
        return hits
    table = db.threat_indicators
    start = time.monotonic()
    try:
        for i in range(0, len(values), LOOKUP_BATCH_SIZE):
            chunk = values[i : i + LOOKUP_BATCH_SIZE]
            query = (
                table.value.belongs(chunk)
                & (table.active == True)  # noqa: E712 - DAL expression
                & table.tenant_id.belongs(tenants)
                & (table.indicator_type == indicator_type)
            )
            for row in await db(query).select():
                match = _row_to_match(row)
                hits.setdefault(match["value"], []).append(match)
    except Exception as e:
        THREAT_LOOKUPS.add(1, {"indicator_type": indicator_type, "result": "error"})
        raise ScannerDependencyError(f"threat-feed lookup failed: {e}") from e
    finally:
        LOOKUP_DURATION.record(time.monotonic() - start, {"indicator_type": indicator_type})
    return hits


def _threat_finding(
    scan_id: str, value: str, indicator_type: str, log_file: str, matches: list[dict[str, Any]]
) -> ScanFinding:
    """Build a finding for an indicator observed in a log that matches threat feeds."""
    confidence = max(int(m.get("confidence") or 0) for m in matches)
    threat_types = sorted({t for m in matches for t in (m.get("threat_types") or [])})
    severity = ScanSeverity.HIGH if confidence >= 90 else ScanSeverity.MEDIUM
    now = datetime.utcnow()
    return ScanFinding(
        scan_id=scan_id,
        finding_type="threat_indicator",
        severity=severity,
        title=f"Known malicious {indicator_type} observed in logs",
        description=f"{indicator_type} {value} in {log_file} matches threat feed(s)",
        affected_component=log_file,
        recommendation="Investigate the connection and block the indicator",
        cve_ids=[],
        cvss_score=7.5 if severity == ScanSeverity.HIGH else 5.0,
        confidence=confidence,
        first_seen=now,
        last_seen=now,
        metadata={
            "indicator": value,
            "indicator_type": indicator_type,
            "log_file": log_file,
            "matched_values": sorted({str(m.get("value")) for m in matches}),
            "sources": sorted({str(m.get("source")) for m in matches}),
            "threat_types": threat_types,
        },
    )


def _collect_indicators(lines: list[str]) -> list[tuple[str, str]]:
    """Return unique normalized (value, type) indicators from ``lines``, newest line first."""
    seen: dict[tuple[str, str], None] = {}
    for line in reversed(lines):
        for raw_ip in _extract_ips_from_log(line):
            ip = _normalize_ip(raw_ip)
            if ip:
                seen.setdefault((ip, "ip"), None)
        for raw_domain in _extract_domains_from_log(line):  # TLD is alphabetic: never an IP
            domain = _normalize_domain(raw_domain)
            if domain:
                seen.setdefault((domain, "domain"), None)
    return list(seen)


def _allocate_fairly(
    per_file: dict[str, list[tuple[str, str]]], cap: int
) -> tuple[dict[tuple[str, str], str], int]:
    """Round-robin newest-first indicators across files up to ``cap``.

    Returns the kept indicators (mapped to their first source file) and the number of
    unique indicators dropped, so one padded log cannot crowd out the others.
    """
    kept: dict[tuple[str, str], str] = {}
    total = len({k for items in per_file.values() for k in items})
    iters = {f: iter(items) for f, items in per_file.items()}
    while iters and len(kept) < cap:
        for f in list(iters):
            if len(kept) >= cap:
                break
            for key in iters[f]:
                if key not in kept:
                    kept[key] = f
                    break
            else:
                del iters[f]
    return kept, total - len(kept)


def _truncation_finding(scan_id: str, total: int, dropped: int) -> ScanFinding:
    """Build the finding that reports incomplete threat-intel coverage for this scan."""
    now = datetime.utcnow()
    return ScanFinding(
        scan_id=scan_id,
        finding_type="threat_intel_coverage",
        severity=ScanSeverity.MEDIUM,
        title="Threat-intel coverage truncated",
        description=(
            f"{dropped} of {total} indicators in log tails were not checked "
            f"(cap {MAX_INDICATORS_PER_SCAN}); logs may be padded to hide activity"
        ),
        affected_component="threat_intel_scan",
        recommendation="Investigate log volume spikes; review log sources for padding",
        cve_ids=[],
        cvss_score=5.0,
        confidence=100,
        first_seen=now,
        last_seen=now,
        metadata={"observed": total, "dropped": dropped, "limit": MAX_INDICATORS_PER_SCAN},
    )


async def _run_threat_intel_scan(scan_id: str, scanner: Any) -> list[ScanFinding]:
    """Scan log tails for IPs/domains and batch-check them against the threat-feed store.

    Indicators are normalized like feed ingest, domains also match parent-domain feed
    entries, and lookups cover the scanner's tenant plus the global feed tenant.

    Raises:
        ScannerDependencyError: no DB, or the threat-indicator store is unreachable.
    """
    db = getattr(scanner, "db", None)
    if db is None:
        raise ScannerDependencyError("threat intel scan requires a database (scanner.db is None)")
    tenants = [GLOBAL_FEED_TENANT]
    tenant_id = getattr(scanner, "tenant_id", None)
    if tenant_id and tenant_id != GLOBAL_FEED_TENANT:
        tenants.insert(0, tenant_id)

    per_file = {
        log_file: _collect_indicators(_read_tail(log_file))
        for log_file in THREAT_LOG_FILES
        if os.path.exists(log_file)
    }
    observed, dropped = _allocate_fairly(per_file, MAX_INDICATORS_PER_SCAN)
    findings: list[ScanFinding] = []
    if dropped:
        logger.warning(
            "threat_intel_indicators_truncated",
            observed=len(observed) + dropped,
            limit=MAX_INDICATORS_PER_SCAN,
            dropped=dropped,
        )
        INDICATORS_TRUNCATED.add(dropped)
        findings.append(_truncation_finding(scan_id, len(observed) + dropped, dropped))

    ips = [v for v, t in observed if t == "ip"]
    domains = [v for v, t in observed if t == "domain"]
    domain_lookup = sorted({c for d in domains for c in _domain_candidates(d)})
    ip_hits = await _batch_lookup(db, tenants, ips, "ip")
    domain_hits = await _batch_lookup(db, tenants, domain_lookup, "domain")

    for (value, indicator_type), log_file in observed.items():
        if indicator_type == "ip":
            matches = ip_hits.get(value, [])
        else:
            matches = [m for c in _domain_candidates(value) for m in domain_hits.get(c, [])]
        THREAT_LOOKUPS.add(
            1, {"indicator_type": indicator_type, "result": "hit" if matches else "miss"}
        )
        if matches:
            logger.warning(
                "threat_indicator_observed",
                indicator_type=indicator_type,
                log_file=log_file,
                matches=len(matches),
            )
            findings.append(_threat_finding(scan_id, value, indicator_type, log_file, matches))
    logger.info(
        "threat_intel_scan_complete", indicators_checked=len(observed), findings=len(findings)
    )
    return findings


async def _run_compliance_scan(scan_id: str, scanner: Any) -> list[ScanFinding]:
    """Evaluate CIS / NIST / SOC2 controls against host state; one finding per failing control.

    Raises:
        ScannerDependencyError: if any control could not be evaluated.
    """
    findings: list[ScanFinding] = []
    errors: list[str] = []
    now = datetime.utcnow()
    for framework, control, description, fn in COMPLIANCE_CHECKS:
        issues = _run_check(f"{framework} {control}", fn, errors)
        if issues:
            findings.append(
                ScanFinding(
                    scan_id=scan_id,
                    finding_type="compliance",
                    severity=ScanSeverity.MEDIUM,
                    title=f"Compliance Violation: {framework} {control}",
                    description=f"{description}: " + "; ".join(i.description for i in issues),
                    affected_component=issues[0].component,
                    recommendation="; ".join(i.recommendation for i in issues),
                    cve_ids=[],
                    cvss_score=4.0,
                    confidence=85,
                    first_seen=now,
                    last_seen=now,
                    metadata={
                        "framework": framework,
                        "control": control,
                        "issues": [i.metadata for i in issues],
                    },
                )
            )
    if errors:
        raise ScannerDependencyError("compliance checks failed: " + "; ".join(errors))
    return findings


def _extract_ips_from_log(log_line: str) -> list[str]:
    """Extract IP addresses from log line.

    Args:
        log_line: Log line to parse.

    Returns:
        List of IP addresses found.
    """
    ip_pattern = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
    return re.findall(ip_pattern, log_line)


def _extract_domains_from_log(log_line: str) -> list[str]:
    """Extract domain names from log line.

    Args:
        log_line: Log line to parse.

    Returns:
        List of domains found.
    """
    domain_pattern = r"\b(?:[^\W_](?:[\w-]{0,61}[^\W_])?\.)+[^\W\d_]{2,}\b"
    return re.findall(domain_pattern, log_line)
