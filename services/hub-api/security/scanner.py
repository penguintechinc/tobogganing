"""Automated security scanning pipeline for SASEWaddle."""

import os
import json
import logging
import asyncio
import subprocess
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import docker
import nmap
import requests
import yaml

from database import get_db
from ..audit import audit_logger, AuditEventType
from .feeds import security_feeds_manager, ThreatType

logger = logging.getLogger(__name__)


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


@dataclass
class ScanFinding:
    """Security scan finding."""
    scan_id: str
    finding_type: str
    severity: ScanSeverity
    title: str
    description: str
    affected_component: str
    recommendation: str
    cve_ids: List[str]
    cvss_score: float
    confidence: int
    first_seen: datetime
    last_seen: datetime
    metadata: Dict[str, Any]


class SecurityScanner:
    """Automated security scanning pipeline."""
    
    def __init__(self):
        self.db = get_db()
        self.docker_client = None
        self._ensure_scanner_tables()
        
        # Scanner configurations
        self.scan_configs = {
            ScanType.VULNERABILITY_SCAN: {
                'tools': ['trivy', 'grype', 'clair'],
                'schedule': '0 2 * * *',  # Daily at 2 AM
                'timeout': 3600,  # 1 hour
                'enabled': True
            },
            ScanType.PORT_SCAN: {
                'tools': ['nmap'],
                'schedule': '0 3 * * 0',  # Weekly on Sunday at 3 AM
                'timeout': 1800,  # 30 minutes
                'enabled': True
            },
            ScanType.DEPENDENCY_SCAN: {
                'tools': ['safety', 'audit', 'govulncheck'],
                'schedule': '0 1 * * *',  # Daily at 1 AM
                'timeout': 900,  # 15 minutes
                'enabled': True
            },
            ScanType.CONTAINER_SCAN: {
                'tools': ['trivy', 'docker-bench'],
                'schedule': '0 4 * * *',  # Daily at 4 AM
                'timeout': 1800,  # 30 minutes
                'enabled': True
            },
            ScanType.CONFIGURATION_SCAN: {
                'tools': ['kube-bench', 'inspec'],
                'schedule': '0 5 * * 0',  # Weekly on Sunday at 5 AM
                'timeout': 900,  # 15 minutes
                'enabled': True
            },
            ScanType.THREAT_INTEL_SCAN: {
                'tools': ['custom'],
                'schedule': '*/15 * * * *',  # Every 15 minutes
                'timeout': 300,  # 5 minutes
                'enabled': True
            },
            ScanType.COMPLIANCE_SCAN: {
                'tools': ['kube-bench', 'docker-bench', 'inspec'],
                'schedule': '0 6 * * 0',  # Weekly on Sunday at 6 AM
                'timeout': 1800,  # 30 minutes
                'enabled': True
            }
        }
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Could not initialize Docker client: {e}")
    
    def _ensure_scanner_tables(self):
        """Create security scanner database tables."""
        
        # Security scans table
        if 'security_scans' not in self.db.tables:
            self.db.define_table('security_scans',
                self.db.Field('scan_id', 'string', length=36, required=True, unique=True),
                self.db.Field('scan_type', 'string', length=32, required=True),
                self.db.Field('target', 'string', length=255, required=True),
                self.db.Field('tools_used', 'json'),
                self.db.Field('status', 'string', length=16, default='pending'),
                self.db.Field('findings_count', 'integer', default=0),
                self.db.Field('critical_findings', 'integer', default=0),
                self.db.Field('high_findings', 'integer', default=0),
                self.db.Field('medium_findings', 'integer', default=0),
                self.db.Field('low_findings', 'integer', default=0),
                self.db.Field('scan_duration', 'integer'),
                self.db.Field('error_message', 'text'),
                self.db.Field('started_at', 'datetime', required=True),
                self.db.Field('completed_at', 'datetime'),
                self.db.Field('triggered_by', 'string', length=64),
                self.db.Field('metadata', 'json')
            )
        
        # Security findings table
        if 'security_findings' not in self.db.tables:
            self.db.define_table('security_findings',
                self.db.Field('finding_id', 'string', length=36, required=True, unique=True),
                self.db.Field('scan_id', 'reference security_scans', required=True),
                self.db.Field('finding_type', 'string', length=64, required=True),
                self.db.Field('severity', 'string', length=16, required=True),
                self.db.Field('title', 'string', length=255, required=True),
                self.db.Field('description', 'text'),
                self.db.Field('affected_component', 'string', length=255),
                self.db.Field('recommendation', 'text'),
                self.db.Field('cve_ids', 'json'),
                self.db.Field('cvss_score', 'double'),
                self.db.Field('confidence', 'integer'),
                self.db.Field('status', 'string', length=16, default='open'),
                self.db.Field('remediated_at', 'datetime'),
                self.db.Field('false_positive', 'boolean', default=False),
                self.db.Field('first_seen', 'datetime', required=True),
                self.db.Field('last_seen', 'datetime', required=True),
                self.db.Field('metadata', 'json')
            )
            
            # Create indexes
            try:
                self.db.executesql('CREATE INDEX idx_security_findings_severity ON security_findings(severity)')
                self.db.executesql('CREATE INDEX idx_security_findings_type ON security_findings(finding_type)')
                self.db.executesql('CREATE INDEX idx_security_findings_status ON security_findings(status)')
                self.db.executesql('CREATE INDEX idx_security_findings_scan_id ON security_findings(scan_id)')
                logger.info("Created indexes for security_findings table")
            except Exception as e:
                logger.warning(f"Could not create security findings indexes: {e}")
        
        # Scan schedules table
        if 'scan_schedules' not in self.db.tables:
            self.db.define_table('scan_schedules',
                self.db.Field('schedule_id', 'string', length=36, required=True, unique=True),
                self.db.Field('scan_type', 'string', length=32, required=True),
                self.db.Field('target_pattern', 'string', length=255, required=True),
                self.db.Field('cron_schedule', 'string', length=32, required=True),
                self.db.Field('enabled', 'boolean', default=True),
                self.db.Field('last_run', 'datetime'),
                self.db.Field('next_run', 'datetime'),
                self.db.Field('created_at', 'datetime', default=datetime.utcnow),
                self.db.Field('created_by', 'string', length=64)
            )
        
        self.db.commit()
        logger.info("Security scanner tables ensured")
    
    async def start_scanning_pipeline(self):
        """Start the automated security scanning pipeline."""
        logger.info("Starting automated security scanning pipeline")
        
        # Start background tasks
        tasks = []
        
        # Schedule regular scans
        tasks.append(self._schedule_scans())
        
        # Monitor for new containers and services
        tasks.append(self._monitor_infrastructure())
        
        # Process threat intelligence
        tasks.append(self._process_threat_intelligence())
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _schedule_scans(self):
        """Schedule and execute security scans."""
        while True:
            try:
                # Check for scheduled scans that need to run
                now = datetime.utcnow()
                
                # Run scans based on configuration
                for scan_type, config in self.scan_configs.items():
                    if not config.get('enabled', True):
                        continue
                    
                    # Check if it's time to run this scan type
                    if await self._should_run_scan(scan_type, config):
                        await self._execute_scan(scan_type, config)
                
                # Wait before next check
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scan scheduler: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _monitor_infrastructure(self):
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
                logger.error(f"Error in infrastructure monitoring: {e}")
                await asyncio.sleep(300)  # Wait before retrying
    
    async def _process_threat_intelligence(self):
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
                logger.error(f"Error in threat intelligence processing: {e}")
                await asyncio.sleep(300)  # Wait before retrying
    
    async def _should_run_scan(self, scan_type: ScanType, config: Dict[str, Any]) -> bool:
        """Check if a scan should be run based on schedule."""
        # For now, implement simple time-based checks
        # In production, this would use a proper cron scheduler
        
        # Get last scan time
        last_scan = self.db(
            (self.db.security_scans.scan_type == scan_type.value) &
            (self.db.security_scans.status == 'completed')
        ).select(
            orderby=~self.db.security_scans.completed_at,
            limitby=(0, 1)
        ).first()
        
        if not last_scan:
            return True  # Never run before
        
        # Calculate next run time based on schedule
        schedule = config.get('schedule', '0 2 * * *')  # Default daily at 2 AM
        
        # Simple schedule parsing (in production, use croniter library)
        if schedule == '0 2 * * *':  # Daily
            next_run = last_scan.completed_at + timedelta(days=1)
        elif schedule == '0 3 * * 0':  # Weekly
            next_run = last_scan.completed_at + timedelta(weeks=1)
        elif schedule == '*/15 * * * *':  # Every 15 minutes
            next_run = last_scan.completed_at + timedelta(minutes=15)
        else:
            next_run = last_scan.completed_at + timedelta(hours=24)  # Default daily
        
        return datetime.utcnow() >= next_run
    
    async def _execute_scan(self, scan_type: ScanType, config: Dict[str, Any]):
        """Execute a security scan."""
        scan_id = f"scan_{scan_type.value}_{int(datetime.utcnow().timestamp())}"
        
        try:
            logger.info(f"Starting {scan_type.value} scan: {scan_id}")
            
            # Record scan start
            scan_record_id = self.db.security_scans.insert(
                scan_id=scan_id,
                scan_type=scan_type.value,
                target='infrastructure',
                tools_used=json.dumps(config.get('tools', [])),
                status='running',
                started_at=datetime.utcnow(),
                triggered_by='automated',
                metadata=json.dumps({'config': config})
            )
            self.db.commit()
            
            # Execute scan based on type
            findings = []
            if scan_type == ScanType.VULNERABILITY_SCAN:
                findings = await self._run_vulnerability_scan(scan_id)
            elif scan_type == ScanType.PORT_SCAN:
                findings = await self._run_port_scan(scan_id)
            elif scan_type == ScanType.DEPENDENCY_SCAN:
                findings = await self._run_dependency_scan(scan_id)
            elif scan_type == ScanType.CONTAINER_SCAN:
                findings = await self._run_container_scan(scan_id)
            elif scan_type == ScanType.CONFIGURATION_SCAN:
                findings = await self._run_configuration_scan(scan_id)
            elif scan_type == ScanType.THREAT_INTEL_SCAN:
                findings = await self._run_threat_intel_scan(scan_id)
            elif scan_type == ScanType.COMPLIANCE_SCAN:
                findings = await self._run_compliance_scan(scan_id)
            
            # Store findings
            for finding in findings:
                await self._store_finding(finding)
            
            # Update scan record
            severity_counts = self._count_findings_by_severity(findings)
            self.db(self.db.security_scans.id == scan_record_id).update(
                status='completed',
                findings_count=len(findings),
                critical_findings=severity_counts.get('critical', 0),
                high_findings=severity_counts.get('high', 0),
                medium_findings=severity_counts.get('medium', 0),
                low_findings=severity_counts.get('low', 0),
                completed_at=datetime.utcnow(),
                scan_duration=int((datetime.utcnow() - 
                                 self.db(self.db.security_scans.id == scan_record_id).select().first().started_at
                                ).total_seconds())
            )
            self.db.commit()
            
            # Log audit event
            audit_logger.log_event(
                event_type=AuditEventType.ADMIN_ACTION,
                action=f'security_scan_{scan_type.value}',
                details={
                    'scan_id': scan_id,
                    'scan_type': scan_type.value,
                    'findings_count': len(findings),
                    'critical_findings': severity_counts.get('critical', 0),
                    'high_findings': severity_counts.get('high', 0),
                    'tools_used': config.get('tools', [])
                },
                severity='info' if len(findings) == 0 else 'warning',
                outcome='success'
            )
            
            logger.info(f"Completed {scan_type.value} scan: {scan_id} - {len(findings)} findings")
            
        except Exception as e:
            # Update scan record with error
            self.db(self.db.security_scans.scan_id == scan_id).update(
                status='failed',
                error_message=str(e),
                completed_at=datetime.utcnow()
            )
            self.db.commit()
            
            # Log audit event
            audit_logger.log_event(
                event_type=AuditEventType.ADMIN_ACTION,
                action=f'security_scan_{scan_type.value}',
                details={
                    'scan_id': scan_id,
                    'scan_type': scan_type.value,
                    'error': str(e)
                },
                severity='error',
                outcome='failure'
            )
            
            logger.error(f"Failed {scan_type.value} scan: {scan_id} - {e}")
    
    async def _run_vulnerability_scan(self, scan_id: str) -> List[ScanFinding]:
        """Run vulnerability scan using Trivy and other tools."""
        findings = []
        
        try:
            # Scan container images
            if self.docker_client:
                images = self.docker_client.images.list()
                for image in images[:5]:  # Limit to first 5 images
                    try:
                        # Run Trivy scan
                        result = subprocess.run([
                            'trivy', 'image', '--format', 'json', '--quiet',
                            image.id
                        ], capture_output=True, text=True, timeout=300)
                        
                        if result.returncode == 0:
                            trivy_results = json.loads(result.stdout)
                            findings.extend(self._parse_trivy_results(scan_id, trivy_results, image.id))
                    except Exception as e:
                        logger.warning(f"Failed to scan image {image.id}: {e}")
            
            # Scan filesystem
            try:
                result = subprocess.run([
                    'trivy', 'fs', '--format', 'json', '--quiet',
                    '/workspaces/SASEWaddle'
                ], capture_output=True, text=True, timeout=600)
                
                if result.returncode == 0:
                    trivy_results = json.loads(result.stdout)
                    findings.extend(self._parse_trivy_results(scan_id, trivy_results, 'filesystem'))
            except Exception as e:
                logger.warning(f"Failed to scan filesystem: {e}")
        
        except Exception as e:
            logger.error(f"Vulnerability scan failed: {e}")
        
        return findings
    
    async def _run_port_scan(self, scan_id: str) -> List[ScanFinding]:
        """Run port scan using Nmap."""
        findings = []
        
        try:
            # Scan common service ports
            nm = nmap.PortScanner()
            
            # Scan localhost
            nm.scan('127.0.0.1', '22,80,443,3306,6379,8080,8443')
            
            for host in nm.all_hosts():
                for protocol in nm[host].all_protocols():
                    ports = nm[host][protocol].keys()
                    
                    for port in ports:
                        port_info = nm[host][protocol][port]
                        
                        if port_info['state'] == 'open':
                            # Check for potentially risky open ports
                            if port in [22, 3306, 6379] and host != '127.0.0.1':
                                findings.append(ScanFinding(
                                    scan_id=scan_id,
                                    finding_type='open_port',
                                    severity=ScanSeverity.MEDIUM,
                                    title=f'Open {port_info.get("name", "unknown")} port',
                                    description=f'Port {port} is open on {host}',
                                    affected_component=f'{host}:{port}',
                                    recommendation='Ensure port is properly secured and necessary',
                                    cve_ids=[],
                                    cvss_score=5.0,
                                    confidence=90,
                                    first_seen=datetime.utcnow(),
                                    last_seen=datetime.utcnow(),
                                    metadata={
                                        'host': host,
                                        'port': port,
                                        'protocol': protocol,
                                        'service': port_info.get('name', 'unknown'),
                                        'state': port_info['state']
                                    }
                                ))
        
        except Exception as e:
            logger.error(f"Port scan failed: {e}")
        
        return findings
    
    async def _run_dependency_scan(self, scan_id: str) -> List[ScanFinding]:
        """Run dependency vulnerability scan."""
        findings = []
        
        try:
            # Check Python dependencies
            try:
                result = subprocess.run([
                    'safety', 'check', '--json'
                ], capture_output=True, text=True, timeout=120)
                
                if result.stdout:
                    safety_results = json.loads(result.stdout)
                    findings.extend(self._parse_safety_results(scan_id, safety_results))
            except Exception as e:
                logger.warning(f"Safety check failed: {e}")
            
            # Check Go dependencies
            go_mod_path = Path('/workspaces/SASEWaddle/headend/proxy/go.mod')
            if go_mod_path.exists():
                try:
                    result = subprocess.run([
                        'govulncheck', './...'
                    ], cwd=go_mod_path.parent, capture_output=True, text=True, timeout=120)
                    
                    if result.stdout:
                        findings.extend(self._parse_govulncheck_results(scan_id, result.stdout))
                except Exception as e:
                    logger.warning(f"Govulncheck failed: {e}")
        
        except Exception as e:
            logger.error(f"Dependency scan failed: {e}")
        
        return findings
    
    async def _run_container_scan(self, scan_id: str) -> List[ScanFinding]:
        """Run container security scan."""
        findings = []
        
        try:
            # Run Docker Bench Security if available
            try:
                result = subprocess.run([
                    'docker', 'run', '--rm', '--net', 'host', '--pid', 'host',
                    '--userns', 'host', '--cap-add', 'audit_control',
                    '-e', 'DOCKER_CONTENT_TRUST=$DOCKER_CONTENT_TRUST',
                    '-v', '/etc:/etc:ro',
                    '-v', '/var/lib:/var/lib:ro',
                    '-v', '/var/run/docker.sock:/var/run/docker.sock:ro',
                    'docker/docker-bench-security'
                ], capture_output=True, text=True, timeout=300)
                
                if result.stdout:
                    findings.extend(self._parse_docker_bench_results(scan_id, result.stdout))
            except Exception as e:
                logger.warning(f"Docker bench scan failed: {e}")
        
        except Exception as e:
            logger.error(f"Container scan failed: {e}")
        
        return findings
    
    async def _run_configuration_scan(self, scan_id: str) -> List[ScanFinding]:
        """Run configuration security scan."""
        findings = []
        
        try:
            # Check basic security configurations
            config_checks = [
                {
                    'name': 'SSH Configuration',
                    'check': self._check_ssh_config,
                    'severity': ScanSeverity.HIGH
                },
                {
                    'name': 'File Permissions',
                    'check': self._check_file_permissions,
                    'severity': ScanSeverity.MEDIUM
                },
                {
                    'name': 'Service Configuration',
                    'check': self._check_service_config,
                    'severity': ScanSeverity.MEDIUM
                }
            ]
            
            for check in config_checks:
                try:
                    result = await check['check']()
                    if result:
                        findings.append(ScanFinding(
                            scan_id=scan_id,
                            finding_type='configuration',
                            severity=check['severity'],
                            title=f"Configuration Issue: {check['name']}",
                            description=result['description'],
                            affected_component=result['component'],
                            recommendation=result['recommendation'],
                            cve_ids=[],
                            cvss_score=result.get('cvss_score', 5.0),
                            confidence=result.get('confidence', 80),
                            first_seen=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                            metadata=result.get('metadata', {})
                        ))
                except Exception as e:
                    logger.warning(f"Configuration check {check['name']} failed: {e}")
        
        except Exception as e:
            logger.error(f"Configuration scan failed: {e}")
        
        return findings
    
    async def _run_threat_intel_scan(self, scan_id: str) -> List[ScanFinding]:
        """Run threat intelligence scan."""
        findings = []
        
        try:
            # Scan recent logs for threat indicators
            logs_to_scan = [
                '/var/log/auth.log',
                '/var/log/nginx/access.log',
                '/var/log/sasewaddle/proxy.log'
            ]
            
            for log_file in logs_to_scan:
                if os.path.exists(log_file):
                    try:
                        # Read recent log entries
                        with open(log_file, 'r') as f:
                            lines = f.readlines()[-1000:]  # Last 1000 lines
                        
                        for line in lines:
                            # Extract IP addresses and domains
                            ips = self._extract_ips_from_log(line)
                            domains = self._extract_domains_from_log(line)
                            
                            # Check against threat feeds
                            for ip in ips:
                                is_threat, threat_details = security_feeds_manager.check_threat_indicator(ip, 'ip')
                                if is_threat:
                                    findings.append(self._create_threat_finding(scan_id, ip, 'ip', threat_details, line))
                            
                            for domain in domains:
                                is_threat, threat_details = security_feeds_manager.check_threat_indicator(domain, 'domain')
                                if is_threat:
                                    findings.append(self._create_threat_finding(scan_id, domain, 'domain', threat_details, line))
                    
                    except Exception as e:
                        logger.warning(f"Failed to scan log file {log_file}: {e}")
        
        except Exception as e:
            logger.error(f"Threat intelligence scan failed: {e}")
        
        return findings
    
    async def _run_compliance_scan(self, scan_id: str) -> List[ScanFinding]:
        """Run compliance security scan."""
        findings = []
        
        try:
            # Basic compliance checks
            compliance_checks = [
                {
                    'framework': 'CIS',
                    'control': '1.1.1.1',
                    'description': 'Ensure mounting of freevxfs filesystems is disabled',
                    'check': lambda: self._check_filesystem_mounting('freevxfs')
                },
                {
                    'framework': 'NIST',
                    'control': 'AC-2',
                    'description': 'Account Management',
                    'check': lambda: self._check_account_management()
                },
                {
                    'framework': 'SOC2',
                    'control': 'CC6.1',
                    'description': 'Logical and Physical Access Controls',
                    'check': lambda: self._check_access_controls()
                }
            ]
            
            for check in compliance_checks:
                try:
                    result = await check['check']()
                    if not result['compliant']:
                        findings.append(ScanFinding(
                            scan_id=scan_id,
                            finding_type='compliance',
                            severity=ScanSeverity.MEDIUM,
                            title=f"Compliance Violation: {check['framework']} {check['control']}",
                            description=check['description'],
                            affected_component=result.get('component', 'system'),
                            recommendation=result.get('recommendation', 'Review compliance requirements'),
                            cve_ids=[],
                            cvss_score=result.get('cvss_score', 4.0),
                            confidence=result.get('confidence', 85),
                            first_seen=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                            metadata={
                                'framework': check['framework'],
                                'control': check['control'],
                                'details': result.get('details', {})
                            }
                        ))
                except Exception as e:
                    logger.warning(f"Compliance check {check['control']} failed: {e}")
        
        except Exception as e:
            logger.error(f"Compliance scan failed: {e}")
        
        return findings
    
    def _parse_trivy_results(self, scan_id: str, trivy_results: Dict[str, Any], target: str) -> List[ScanFinding]:
        """Parse Trivy scan results."""
        findings = []
        
        results = trivy_results.get('Results', [])
        for result in results:
            vulnerabilities = result.get('Vulnerabilities', [])
            
            for vuln in vulnerabilities:
                severity_map = {
                    'CRITICAL': ScanSeverity.CRITICAL,
                    'HIGH': ScanSeverity.HIGH,
                    'MEDIUM': ScanSeverity.MEDIUM,
                    'LOW': ScanSeverity.LOW,
                    'UNKNOWN': ScanSeverity.INFO
                }
                
                findings.append(ScanFinding(
                    scan_id=scan_id,
                    finding_type='vulnerability',
                    severity=severity_map.get(vuln.get('Severity', 'UNKNOWN'), ScanSeverity.INFO),
                    title=vuln.get('Title', 'Unknown Vulnerability'),
                    description=vuln.get('Description', ''),
                    affected_component=f"{target}:{vuln.get('PkgName', 'unknown')}",
                    recommendation=vuln.get('FixedVersion', 'Update to latest version'),
                    cve_ids=[vuln.get('VulnerabilityID', '')],
                    cvss_score=float(vuln.get('CVSS', {}).get('nvd', {}).get('V3Score', 0)),
                    confidence=90,
                    first_seen=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                    metadata={
                        'package': vuln.get('PkgName'),
                        'installed_version': vuln.get('InstalledVersion'),
                        'fixed_version': vuln.get('FixedVersion'),
                        'references': vuln.get('References', [])
                    }
                ))
        
        return findings
    
    async def _store_finding(self, finding: ScanFinding):
        """Store a security finding in the database."""
        try:
            finding_id = f"finding_{finding.scan_id}_{hash(finding.title)}_{int(datetime.utcnow().timestamp())}"
            
            self.db.security_findings.insert(
                finding_id=finding_id,
                scan_id=finding.scan_id,
                finding_type=finding.finding_type,
                severity=finding.severity.value,
                title=finding.title,
                description=finding.description,
                affected_component=finding.affected_component,
                recommendation=finding.recommendation,
                cve_ids=json.dumps(finding.cve_ids),
                cvss_score=finding.cvss_score,
                confidence=finding.confidence,
                first_seen=finding.first_seen,
                last_seen=finding.last_seen,
                metadata=json.dumps(finding.metadata)
            )
        except Exception as e:
            logger.error(f"Failed to store finding: {e}")
    
    def _count_findings_by_severity(self, findings: List[ScanFinding]) -> Dict[str, int]:
        """Count findings by severity level."""
        counts = {}
        for finding in findings:
            severity = finding.severity.value
            counts[severity] = counts.get(severity, 0) + 1
        return counts
    
    # Placeholder methods for various checks (would be implemented based on specific requirements)
    
    async def _check_ssh_config(self):
        """Check SSH configuration security."""
        # Placeholder implementation
        return None
    
    async def _check_file_permissions(self):
        """Check file permissions."""
        # Placeholder implementation
        return None
    
    async def _check_service_config(self):
        """Check service configurations."""
        # Placeholder implementation
        return None
    
    def _extract_ips_from_log(self, log_line: str) -> List[str]:
        """Extract IP addresses from log line."""
        import re
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
        return re.findall(ip_pattern, log_line)
    
    def _extract_domains_from_log(self, log_line: str) -> List[str]:
        """Extract domain names from log line."""
        import re
        domain_pattern = r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b'
        return re.findall(domain_pattern, log_line)
    
    def _create_threat_finding(self, scan_id: str, indicator: str, indicator_type: str, 
                             threat_details: List[Dict[str, Any]], context: str) -> ScanFinding:
        """Create a threat intelligence finding."""
        
        # Determine severity based on threat confidence
        max_confidence = max([t.get('confidence', 0) for t in threat_details])
        if max_confidence >= 90:
            severity = ScanSeverity.CRITICAL
        elif max_confidence >= 70:
            severity = ScanSeverity.HIGH
        elif max_confidence >= 50:
            severity = ScanSeverity.MEDIUM
        else:
            severity = ScanSeverity.LOW
        
        threat_types = []
        sources = []
        for threat in threat_details:
            threat_types.extend(threat.get('threat_types', []))
            sources.append(threat.get('source', 'unknown'))
        
        return ScanFinding(
            scan_id=scan_id,
            finding_type='threat_intelligence',
            severity=severity,
            title=f'Threat Indicator Detected: {indicator}',
            description=f'Known threat indicator found in logs: {indicator}',
            affected_component=f'{indicator_type}:{indicator}',
            recommendation=f'Block {indicator} and investigate related activity',
            cve_ids=[],
            cvss_score=max_confidence / 10.0,  # Convert to 0-10 scale
            confidence=max_confidence,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            metadata={
                'indicator': indicator,
                'indicator_type': indicator_type,
                'threat_types': list(set(threat_types)),
                'sources': list(set(sources)),
                'context': context[:500],  # Truncate context
                'threat_details': threat_details
            }
        )
    
    # Additional placeholder methods
    async def _scan_new_containers(self):
        """Scan for new containers."""
        pass
    
    async def _scan_kubernetes_resources(self):
        """Scan Kubernetes resources."""
        pass
    
    async def _scan_network_services(self):
        """Scan network services."""
        pass
    
    async def _scan_logs_for_threats(self):
        """Scan logs for threat indicators."""
        pass
    
    async def _scan_network_threats(self):
        """Scan network traffic for threats."""
        pass
    
    async def _correlate_with_threat_feeds(self):
        """Correlate findings with threat feeds."""
        pass


# Global security scanner instance
security_scanner = SecurityScanner()