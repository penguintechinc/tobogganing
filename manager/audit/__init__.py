"""Audit logging and compliance reporting for SASEWaddle Manager."""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

from database import get_db

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Audit event types for compliance tracking."""
    
    # Authentication and authorization
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_LOGIN_FAILED = "user_login_failed"
    USER_SESSION_EXPIRED = "user_session_expired"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    
    # Resource access
    RESOURCE_ACCESS = "resource_access"
    RESOURCE_CREATED = "resource_created"
    RESOURCE_MODIFIED = "resource_modified"
    RESOURCE_DELETED = "resource_deleted"
    RESOURCE_ACCESSED_UNAUTHORIZED = "resource_accessed_unauthorized"
    
    # Configuration changes
    CONFIG_CHANGED = "config_changed"
    SYSTEM_CONFIG_CHANGED = "system_config_changed"
    SECURITY_CONFIG_CHANGED = "security_config_changed"
    
    # Administrative actions
    ADMIN_ACTION = "admin_action"
    USER_CREATED = "user_created"
    USER_MODIFIED = "user_modified"
    USER_DELETED = "user_deleted"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REVOKED = "role_revoked"
    
    # Security events
    SECURITY_INCIDENT = "security_incident"
    IP_BLOCKED = "ip_blocked"
    IP_UNBLOCKED = "ip_unblocked"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DDOS_DETECTED = "ddos_detected"
    
    # Data access and changes
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    DATA_BACKUP = "data_backup"
    DATA_RESTORE = "data_restore"
    
    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    SERVICE_START = "service_start"
    SERVICE_STOP = "service_stop"


class ComplianceFramework(Enum):
    """Supported compliance frameworks."""
    
    SOC2 = "soc2"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO27001 = "iso27001"
    NIST = "nist"


@dataclass
class AuditEvent:
    """Audit event structure for compliance logging."""
    
    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    user_id: Optional[str]
    user_email: Optional[str]
    ip_address: str
    user_agent: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    action: str
    details: Dict[str, Any]
    severity: str
    compliance_frameworks: List[ComplianceFramework]
    session_id: Optional[str]
    request_id: Optional[str]
    outcome: str  # success, failure, partial
    risk_score: int  # 1-10 scale


class AuditLogger:
    """Comprehensive audit logging system for compliance requirements."""
    
    def __init__(self):
        self.db = get_db()
        self._ensure_audit_tables()
        
        # Initialize compliance mapping
        self.compliance_mapping = self._load_compliance_mapping()
    
    def _ensure_audit_tables(self):
        """Create audit-related database tables."""
        
        # Main audit log table
        if 'audit_events' not in self.db.tables:
            self.db.define_table('audit_events',
                self.db.Field('event_id', 'string', length=36, required=True, unique=True),
                self.db.Field('event_type', 'string', length=64, required=True),
                self.db.Field('timestamp', 'datetime', required=True),
                self.db.Field('user_id', 'string', length=64),
                self.db.Field('user_email', 'string', length=255),
                self.db.Field('ip_address', 'string', length=45, required=True),
                self.db.Field('user_agent', 'text'),
                self.db.Field('resource_type', 'string', length=64),
                self.db.Field('resource_id', 'string', length=255),
                self.db.Field('action', 'string', length=255, required=True),
                self.db.Field('details', 'json'),
                self.db.Field('severity', 'string', length=16),
                self.db.Field('compliance_frameworks', 'json'),
                self.db.Field('session_id', 'string', length=64),
                self.db.Field('request_id', 'string', length=64),
                self.db.Field('outcome', 'string', length=16),
                self.db.Field('risk_score', 'integer'),
                self.db.Field('created_at', 'datetime', default=datetime.utcnow),
                self.db.Field('archived', 'boolean', default=False)
            )
            
            # Create indexes for performance and compliance queries
            try:
                self.db.executesql('CREATE INDEX idx_audit_events_timestamp ON audit_events(timestamp)')
                self.db.executesql('CREATE INDEX idx_audit_events_user_id ON audit_events(user_id)')
                self.db.executesql('CREATE INDEX idx_audit_events_event_type ON audit_events(event_type)')
                self.db.executesql('CREATE INDEX idx_audit_events_ip_address ON audit_events(ip_address)')
                self.db.executesql('CREATE INDEX idx_audit_events_resource ON audit_events(resource_type, resource_id)')
                self.db.executesql('CREATE INDEX idx_audit_events_compliance ON audit_events(compliance_frameworks(255))')
                logger.info("Created indexes for audit_events table")
            except Exception as e:
                logger.warning(f"Could not create audit indexes (may already exist): {e}")
        
        # Compliance reports table
        if 'compliance_reports' not in self.db.tables:
            self.db.define_table('compliance_reports',
                self.db.Field('report_id', 'string', length=36, required=True, unique=True),
                self.db.Field('framework', 'string', length=32, required=True),
                self.db.Field('report_type', 'string', length=32, required=True),
                self.db.Field('start_date', 'datetime', required=True),
                self.db.Field('end_date', 'datetime', required=True),
                self.db.Field('generated_by', 'string', length=64, required=True),
                self.db.Field('status', 'string', length=16, default='pending'),
                self.db.Field('report_data', 'json'),
                self.db.Field('file_path', 'string', length=512),
                self.db.Field('created_at', 'datetime', default=datetime.utcnow),
                self.db.Field('completed_at', 'datetime')
            )
        
        # Audit trail integrity table (for tamper detection)
        if 'audit_integrity' not in self.db.tables:
            self.db.define_table('audit_integrity',
                self.db.Field('day_date', 'date', required=True, unique=True),
                self.db.Field('event_count', 'integer', required=True),
                self.db.Field('checksum', 'string', length=64, required=True),
                self.db.Field('previous_checksum', 'string', length=64),
                self.db.Field('created_at', 'datetime', default=datetime.utcnow)
            )
        
        self.db.commit()
        logger.info("Audit tables ensured")
    
    def _load_compliance_mapping(self) -> Dict[AuditEventType, List[ComplianceFramework]]:
        """Load mapping of audit events to compliance frameworks."""
        
        return {
            # Authentication events - all frameworks care about these
            AuditEventType.USER_LOGIN: [ComplianceFramework.SOC2, ComplianceFramework.GDPR, 
                                       ComplianceFramework.HIPAA, ComplianceFramework.PCI_DSS, 
                                       ComplianceFramework.ISO27001, ComplianceFramework.NIST],
            AuditEventType.USER_LOGOUT: [ComplianceFramework.SOC2, ComplianceFramework.GDPR,
                                        ComplianceFramework.HIPAA, ComplianceFramework.ISO27001],
            AuditEventType.USER_LOGIN_FAILED: [ComplianceFramework.SOC2, ComplianceFramework.PCI_DSS,
                                              ComplianceFramework.ISO27001, ComplianceFramework.NIST],
            AuditEventType.PRIVILEGE_ESCALATION: [ComplianceFramework.SOC2, ComplianceFramework.PCI_DSS,
                                                 ComplianceFramework.ISO27001, ComplianceFramework.NIST],
            
            # Data access events - GDPR and HIPAA focus
            AuditEventType.RESOURCE_ACCESS: [ComplianceFramework.GDPR, ComplianceFramework.HIPAA,
                                           ComplianceFramework.SOC2],
            AuditEventType.DATA_EXPORT: [ComplianceFramework.GDPR, ComplianceFramework.HIPAA,
                                        ComplianceFramework.SOC2, ComplianceFramework.ISO27001],
            AuditEventType.DATA_IMPORT: [ComplianceFramework.GDPR, ComplianceFramework.HIPAA,
                                        ComplianceFramework.SOC2],
            
            # Administrative actions - SOC2 and ISO27001 focus
            AuditEventType.ADMIN_ACTION: [ComplianceFramework.SOC2, ComplianceFramework.ISO27001,
                                         ComplianceFramework.NIST],
            AuditEventType.CONFIG_CHANGED: [ComplianceFramework.SOC2, ComplianceFramework.PCI_DSS,
                                          ComplianceFramework.ISO27001, ComplianceFramework.NIST],
            AuditEventType.SECURITY_CONFIG_CHANGED: [ComplianceFramework.SOC2, ComplianceFramework.PCI_DSS,
                                                   ComplianceFramework.ISO27001, ComplianceFramework.NIST],
            
            # Security events - all frameworks
            AuditEventType.SECURITY_INCIDENT: [ComplianceFramework.SOC2, ComplianceFramework.PCI_DSS,
                                              ComplianceFramework.ISO27001, ComplianceFramework.NIST],
            AuditEventType.DDOS_DETECTED: [ComplianceFramework.SOC2, ComplianceFramework.PCI_DSS,
                                         ComplianceFramework.ISO27001, ComplianceFramework.NIST],
            
            # Backup/restore - SOC2 and ISO27001 focus
            AuditEventType.DATA_BACKUP: [ComplianceFramework.SOC2, ComplianceFramework.ISO27001],
            AuditEventType.DATA_RESTORE: [ComplianceFramework.SOC2, ComplianceFramework.ISO27001,
                                         ComplianceFramework.NIST],
        }
    
    def log_event(self, event_type: AuditEventType, user_id: Optional[str] = None,
                  user_email: Optional[str] = None, ip_address: str = "unknown",
                  user_agent: str = "", resource_type: Optional[str] = None,
                  resource_id: Optional[str] = None, action: str = "",
                  details: Optional[Dict[str, Any]] = None, severity: str = "info",
                  session_id: Optional[str] = None, request_id: Optional[str] = None,
                  outcome: str = "success", custom_risk_score: Optional[int] = None) -> str:
        """
        Log an audit event with full compliance tracking.
        
        Returns:
            event_id: Unique identifier for the audit event
        """
        
        # Generate unique event ID
        event_id = str(uuid.uuid4())
        
        # Determine compliance frameworks for this event type
        compliance_frameworks = self.compliance_mapping.get(event_type, [])
        
        # Calculate risk score if not provided
        risk_score = custom_risk_score or self._calculate_risk_score(event_type, severity, outcome)
        
        # Create audit event
        audit_event = AuditEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details or {},
            severity=severity,
            compliance_frameworks=compliance_frameworks,
            session_id=session_id,
            request_id=request_id,
            outcome=outcome,
            risk_score=risk_score
        )
        
        # Store in database
        try:
            self.db.audit_events.insert(
                event_id=audit_event.event_id,
                event_type=audit_event.event_type.value,
                timestamp=audit_event.timestamp,
                user_id=audit_event.user_id,
                user_email=audit_event.user_email,
                ip_address=audit_event.ip_address,
                user_agent=audit_event.user_agent,
                resource_type=audit_event.resource_type,
                resource_id=audit_event.resource_id,
                action=audit_event.action,
                details=json.dumps(audit_event.details),
                severity=audit_event.severity,
                compliance_frameworks=json.dumps([f.value for f in audit_event.compliance_frameworks]),
                session_id=audit_event.session_id,
                request_id=audit_event.request_id,
                outcome=audit_event.outcome,
                risk_score=audit_event.risk_score
            )
            self.db.commit()
            
            # Log to application logs as well
            log_level = {
                'debug': logger.debug,
                'info': logger.info,
                'warning': logger.warning,
                'error': logger.error,
                'critical': logger.critical
            }.get(severity, logger.info)
            
            log_level(f"AUDIT: {event_type.value} - User: {user_id} - Action: {action} - Outcome: {outcome}")
            
            return event_id
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            # Still log to application logs as fallback
            logger.error(f"AUDIT_FALLBACK: {event_type.value} - User: {user_id} - Action: {action}")
            raise
    
    def _calculate_risk_score(self, event_type: AuditEventType, severity: str, outcome: str) -> int:
        """Calculate risk score (1-10) based on event characteristics."""
        
        base_scores = {
            # High-risk events
            AuditEventType.PRIVILEGE_ESCALATION: 8,
            AuditEventType.SECURITY_INCIDENT: 9,
            AuditEventType.DDOS_DETECTED: 7,
            AuditEventType.RESOURCE_ACCESSED_UNAUTHORIZED: 9,
            AuditEventType.DATA_EXPORT: 6,
            
            # Medium-risk events
            AuditEventType.USER_LOGIN_FAILED: 5,
            AuditEventType.ADMIN_ACTION: 5,
            AuditEventType.CONFIG_CHANGED: 4,
            AuditEventType.SECURITY_CONFIG_CHANGED: 6,
            
            # Low-risk events
            AuditEventType.USER_LOGIN: 2,
            AuditEventType.USER_LOGOUT: 1,
            AuditEventType.RESOURCE_ACCESS: 2,
        }
        
        base_score = base_scores.get(event_type, 3)
        
        # Adjust based on severity
        severity_multipliers = {
            'debug': 0.5,
            'info': 1.0,
            'warning': 1.3,
            'error': 1.6,
            'critical': 2.0
        }
        
        # Adjust based on outcome
        outcome_multipliers = {
            'success': 1.0,
            'partial': 1.2,
            'failure': 1.5
        }
        
        final_score = base_score * severity_multipliers.get(severity, 1.0) * outcome_multipliers.get(outcome, 1.0)
        
        # Clamp to 1-10 range
        return max(1, min(10, int(final_score)))
    
    def get_audit_events(self, start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None,
                        user_id: Optional[str] = None,
                        event_types: Optional[List[AuditEventType]] = None,
                        compliance_framework: Optional[ComplianceFramework] = None,
                        severity_filter: Optional[List[str]] = None,
                        limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieve audit events with filtering for compliance reporting."""
        
        # Build query
        query = self.db.audit_events.archived == False
        
        if start_date:
            query &= (self.db.audit_events.timestamp >= start_date)
        if end_date:
            query &= (self.db.audit_events.timestamp <= end_date)
        if user_id:
            query &= (self.db.audit_events.user_id == user_id)
        if event_types:
            type_values = [et.value for et in event_types]
            query &= self.db.audit_events.event_type.belongs(type_values)
        if severity_filter:
            query &= self.db.audit_events.severity.belongs(severity_filter)
        
        # Execute query
        events = self.db(query).select(
            orderby=~self.db.audit_events.timestamp,
            limitby=(offset, offset + limit)
        )
        
        result = []
        for event in events:
            event_data = {
                'event_id': event.event_id,
                'event_type': event.event_type,
                'timestamp': event.timestamp.isoformat() if event.timestamp else None,
                'user_id': event.user_id,
                'user_email': event.user_email,
                'ip_address': event.ip_address,
                'user_agent': event.user_agent,
                'resource_type': event.resource_type,
                'resource_id': event.resource_id,
                'action': event.action,
                'details': json.loads(event.details) if event.details else {},
                'severity': event.severity,
                'compliance_frameworks': json.loads(event.compliance_frameworks) if event.compliance_frameworks else [],
                'session_id': event.session_id,
                'request_id': event.request_id,
                'outcome': event.outcome,
                'risk_score': event.risk_score,
                'created_at': event.created_at.isoformat() if event.created_at else None
            }
            
            # Filter by compliance framework if specified
            if compliance_framework:
                frameworks = event_data['compliance_frameworks']
                if compliance_framework.value not in frameworks:
                    continue
            
            result.append(event_data)
        
        return result
    
    def get_audit_statistics(self, start_date: datetime, end_date: datetime,
                           compliance_framework: Optional[ComplianceFramework] = None) -> Dict[str, Any]:
        """Get audit statistics for compliance reporting."""
        
        query = (self.db.audit_events.timestamp >= start_date) & \
                (self.db.audit_events.timestamp <= end_date) & \
                (self.db.audit_events.archived == False)
        
        # Total events
        total_events = self.db(query).count()
        
        # Events by type
        event_types = self.db(query).select(
            self.db.audit_events.event_type,
            self.db.audit_events.id.count(),
            groupby=self.db.audit_events.event_type
        )
        
        event_type_counts = {}
        for row in event_types:
            event_type_counts[row.audit_events.event_type] = row._extra[self.db.audit_events.id.count()]
        
        # Events by severity
        severities = self.db(query).select(
            self.db.audit_events.severity,
            self.db.audit_events.id.count(),
            groupby=self.db.audit_events.severity
        )
        
        severity_counts = {}
        for row in severities:
            severity_counts[row.audit_events.severity] = row._extra[self.db.audit_events.id.count()]
        
        # High-risk events (risk_score >= 7)
        high_risk_events = self.db(query & (self.db.audit_events.risk_score >= 7)).count()
        
        # Failed events
        failed_events = self.db(query & (self.db.audit_events.outcome == 'failure')).count()
        
        # Unique users
        unique_users = len(self.db(query & (self.db.audit_events.user_id != None)).select(
            self.db.audit_events.user_id,
            groupby=self.db.audit_events.user_id
        ))
        
        # Unique IP addresses
        unique_ips = len(self.db(query).select(
            self.db.audit_events.ip_address,
            groupby=self.db.audit_events.ip_address
        ))
        
        return {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'total_events': total_events,
            'event_type_counts': event_type_counts,
            'severity_counts': severity_counts,
            'high_risk_events': high_risk_events,
            'failed_events': failed_events,
            'unique_users': unique_users,
            'unique_ip_addresses': unique_ips,
            'compliance_framework': compliance_framework.value if compliance_framework else None
        }
    
    def calculate_daily_integrity(self, date: datetime.date) -> str:
        """Calculate daily integrity checksum for audit trail tamper detection."""
        
        # Get all events for the day
        start_datetime = datetime.combine(date, datetime.min.time())
        end_datetime = datetime.combine(date, datetime.max.time())
        
        events = self.db(
            (self.db.audit_events.timestamp >= start_datetime) &
            (self.db.audit_events.timestamp <= end_datetime)
        ).select(orderby=self.db.audit_events.timestamp)
        
        # Create checksum from all event data
        checksum_data = ""
        event_count = 0
        
        for event in events:
            event_string = f"{event.event_id}{event.event_type}{event.timestamp}{event.user_id}{event.action}"
            checksum_data += event_string
            event_count += 1
        
        # Calculate SHA-256 checksum
        checksum = hashlib.sha256(checksum_data.encode()).hexdigest()
        
        # Get previous day's checksum for chaining
        previous_date = date - timedelta(days=1)
        previous_integrity = self.db(self.db.audit_integrity.day_date == previous_date).select().first()
        previous_checksum = previous_integrity.checksum if previous_integrity else ""
        
        # Store integrity record
        self.db.audit_integrity.insert(
            day_date=date,
            event_count=event_count,
            checksum=checksum,
            previous_checksum=previous_checksum
        )
        self.db.commit()
        
        return checksum
    
    def verify_audit_integrity(self, start_date: datetime.date, end_date: datetime.date) -> Dict[str, Any]:
        """Verify audit trail integrity for compliance audits."""
        
        results = {
            'verified_dates': [],
            'failed_dates': [],
            'missing_dates': [],
            'total_events_verified': 0,
            'integrity_status': 'passed'
        }
        
        current_date = start_date
        while current_date <= end_date:
            # Check if integrity record exists
            integrity_record = self.db(self.db.audit_integrity.day_date == current_date).select().first()
            
            if not integrity_record:
                results['missing_dates'].append(current_date.isoformat())
                results['integrity_status'] = 'failed'
                current_date += timedelta(days=1)
                continue
            
            # Recalculate checksum for verification
            calculated_checksum = self._recalculate_daily_checksum(current_date)
            
            if calculated_checksum == integrity_record.checksum:
                results['verified_dates'].append(current_date.isoformat())
                results['total_events_verified'] += integrity_record.event_count
            else:
                results['failed_dates'].append(current_date.isoformat())
                results['integrity_status'] = 'failed'
            
            current_date += timedelta(days=1)
        
        return results
    
    def _recalculate_daily_checksum(self, date: datetime.date) -> str:
        """Recalculate checksum for a specific date."""
        
        start_datetime = datetime.combine(date, datetime.min.time())
        end_datetime = datetime.combine(date, datetime.max.time())
        
        events = self.db(
            (self.db.audit_events.timestamp >= start_datetime) &
            (self.db.audit_events.timestamp <= end_datetime)
        ).select(orderby=self.db.audit_events.timestamp)
        
        checksum_data = ""
        for event in events:
            event_string = f"{event.event_id}{event.event_type}{event.timestamp}{event.user_id}{event.action}"
            checksum_data += event_string
        
        return hashlib.sha256(checksum_data.encode()).hexdigest()


# Global audit logger instance
audit_logger = AuditLogger()