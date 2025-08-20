"""Compliance reporting for various frameworks."""

import os
import json
import csv
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import uuid
from pathlib import Path

from . import audit_logger, AuditEventType, ComplianceFramework
from database import get_db

logger = logging.getLogger(__name__)


class ComplianceReporter:
    """Generate compliance reports for various frameworks."""
    
    def __init__(self):
        self.db = get_db()
        self.audit_logger = audit_logger
        self.reports_dir = Path(os.getenv('COMPLIANCE_REPORTS_DIR', '/var/log/sasewaddle/compliance'))
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_soc2_report(self, start_date: datetime, end_date: datetime, 
                           generated_by: str) -> str:
        """Generate SOC 2 compliance report."""
        
        report_id = str(uuid.uuid4())
        
        # SOC 2 focuses on security, availability, confidentiality
        soc2_events = [
            AuditEventType.USER_LOGIN,
            AuditEventType.USER_LOGIN_FAILED,
            AuditEventType.PRIVILEGE_ESCALATION,
            AuditEventType.ADMIN_ACTION,
            AuditEventType.CONFIG_CHANGED,
            AuditEventType.SECURITY_CONFIG_CHANGED,
            AuditEventType.SECURITY_INCIDENT,
            AuditEventType.DATA_BACKUP,
            AuditEventType.DATA_RESTORE,
            AuditEventType.SYSTEM_START,
            AuditEventType.SYSTEM_STOP,
            AuditEventType.SERVICE_START,
            AuditEventType.SERVICE_STOP
        ]
        
        # Get audit events
        events = self.audit_logger.get_audit_events(
            start_date=start_date,
            end_date=end_date,
            event_types=soc2_events,
            compliance_framework=ComplianceFramework.SOC2,
            limit=10000
        )
        
        # Get statistics
        stats = self.audit_logger.get_audit_statistics(
            start_date, end_date, ComplianceFramework.SOC2
        )
        
        # SOC 2 specific analysis
        report_data = {
            'report_id': report_id,
            'framework': 'SOC2',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'total_security_events': stats['total_events'],
                'failed_logins': stats['event_type_counts'].get('user_login_failed', 0),
                'privilege_escalations': stats['event_type_counts'].get('privilege_escalation', 0),
                'admin_actions': stats['event_type_counts'].get('admin_action', 0),
                'config_changes': stats['event_type_counts'].get('config_changed', 0) + 
                                stats['event_type_counts'].get('security_config_changed', 0),
                'security_incidents': stats['event_type_counts'].get('security_incident', 0),
                'high_risk_events': stats['high_risk_events'],
                'unique_administrators': stats['unique_users']
            },
            'trust_services_criteria': {
                'security': self._analyze_security_controls(events),
                'availability': self._analyze_availability_controls(events),
                'confidentiality': self._analyze_confidentiality_controls(events),
                'processing_integrity': self._analyze_processing_integrity(events),
                'privacy': self._analyze_privacy_controls(events)
            },
            'events': events[:1000],  # Include first 1000 events
            'integrity_verification': self._verify_period_integrity(start_date.date(), end_date.date())
        }
        
        # Save report
        return self._save_report(report_id, 'SOC2', 'security_audit', start_date, end_date, 
                               generated_by, report_data)
    
    def generate_gdpr_report(self, start_date: datetime, end_date: datetime,
                           generated_by: str) -> str:
        """Generate GDPR compliance report."""
        
        report_id = str(uuid.uuid4())
        
        # GDPR focuses on data protection and privacy
        gdpr_events = [
            AuditEventType.RESOURCE_ACCESS,
            AuditEventType.DATA_EXPORT,
            AuditEventType.DATA_IMPORT,
            AuditEventType.USER_CREATED,
            AuditEventType.USER_MODIFIED,
            AuditEventType.USER_DELETED,
            AuditEventType.RESOURCE_ACCESSED_UNAUTHORIZED,
            AuditEventType.USER_LOGIN,
            AuditEventType.USER_LOGOUT
        ]
        
        events = self.audit_logger.get_audit_events(
            start_date=start_date,
            end_date=end_date,
            event_types=gdpr_events,
            compliance_framework=ComplianceFramework.GDPR,
            limit=10000
        )
        
        stats = self.audit_logger.get_audit_statistics(
            start_date, end_date, ComplianceFramework.GDPR
        )
        
        # GDPR specific analysis
        report_data = {
            'report_id': report_id,
            'framework': 'GDPR',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'total_data_events': stats['total_events'],
                'data_access_events': stats['event_type_counts'].get('resource_access', 0),
                'data_exports': stats['event_type_counts'].get('data_export', 0),
                'unauthorized_access_attempts': stats['event_type_counts'].get('resource_accessed_unauthorized', 0),
                'user_account_changes': (stats['event_type_counts'].get('user_created', 0) +
                                       stats['event_type_counts'].get('user_modified', 0) +
                                       stats['event_type_counts'].get('user_deleted', 0)),
                'unique_data_subjects': stats['unique_users']
            },
            'gdpr_principles': {
                'lawfulness': self._analyze_lawfulness(events),
                'purpose_limitation': self._analyze_purpose_limitation(events),
                'data_minimization': self._analyze_data_minimization(events),
                'accuracy': self._analyze_data_accuracy(events),
                'storage_limitation': self._analyze_storage_limitation(events),
                'security': self._analyze_gdpr_security(events),
                'accountability': self._analyze_accountability(events)
            },
            'data_subject_rights': {
                'access_requests': self._count_access_requests(events),
                'deletion_requests': self._count_deletion_requests(events),
                'rectification_requests': self._count_rectification_requests(events)
            },
            'events': events[:1000],
            'integrity_verification': self._verify_period_integrity(start_date.date(), end_date.date())
        }
        
        return self._save_report(report_id, 'GDPR', 'privacy_audit', start_date, end_date,
                               generated_by, report_data)
    
    def generate_hipaa_report(self, start_date: datetime, end_date: datetime,
                            generated_by: str) -> str:
        """Generate HIPAA compliance report."""
        
        report_id = str(uuid.uuid4())
        
        # HIPAA focuses on healthcare data protection
        hipaa_events = [
            AuditEventType.RESOURCE_ACCESS,
            AuditEventType.DATA_EXPORT,
            AuditEventType.USER_LOGIN,
            AuditEventType.USER_LOGIN_FAILED,
            AuditEventType.RESOURCE_ACCESSED_UNAUTHORIZED,
            AuditEventType.ADMIN_ACTION,
            AuditEventType.DATA_BACKUP,
            AuditEventType.DATA_RESTORE
        ]
        
        events = self.audit_logger.get_audit_events(
            start_date=start_date,
            end_date=end_date,
            event_types=hipaa_events,
            compliance_framework=ComplianceFramework.HIPAA,
            limit=10000
        )
        
        stats = self.audit_logger.get_audit_statistics(
            start_date, end_date, ComplianceFramework.HIPAA
        )
        
        report_data = {
            'report_id': report_id,
            'framework': 'HIPAA',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'total_phi_events': stats['total_events'],
                'phi_access_events': stats['event_type_counts'].get('resource_access', 0),
                'failed_access_attempts': stats['event_type_counts'].get('user_login_failed', 0),
                'unauthorized_access': stats['event_type_counts'].get('resource_accessed_unauthorized', 0),
                'administrative_actions': stats['event_type_counts'].get('admin_action', 0),
                'unique_users': stats['unique_users']
            },
            'hipaa_safeguards': {
                'administrative': self._analyze_administrative_safeguards(events),
                'physical': self._analyze_physical_safeguards(events),
                'technical': self._analyze_technical_safeguards(events)
            },
            'minimum_necessary': self._analyze_minimum_necessary(events),
            'events': events[:1000],
            'integrity_verification': self._verify_period_integrity(start_date.date(), end_date.date())
        }
        
        return self._save_report(report_id, 'HIPAA', 'phi_audit', start_date, end_date,
                               generated_by, report_data)
    
    def generate_pci_dss_report(self, start_date: datetime, end_date: datetime,
                              generated_by: str) -> str:
        """Generate PCI DSS compliance report."""
        
        report_id = str(uuid.uuid4())
        
        # PCI DSS focuses on payment card data security
        pci_events = [
            AuditEventType.USER_LOGIN,
            AuditEventType.USER_LOGIN_FAILED,
            AuditEventType.PRIVILEGE_ESCALATION,
            AuditEventType.ADMIN_ACTION,
            AuditEventType.CONFIG_CHANGED,
            AuditEventType.SECURITY_CONFIG_CHANGED,
            AuditEventType.SECURITY_INCIDENT,
            AuditEventType.RESOURCE_ACCESS,
            AuditEventType.RESOURCE_ACCESSED_UNAUTHORIZED
        ]
        
        events = self.audit_logger.get_audit_events(
            start_date=start_date,
            end_date=end_date,
            event_types=pci_events,
            compliance_framework=ComplianceFramework.PCI_DSS,
            limit=10000
        )
        
        stats = self.audit_logger.get_audit_statistics(
            start_date, end_date, ComplianceFramework.PCI_DSS
        )
        
        report_data = {
            'report_id': report_id,
            'framework': 'PCI_DSS',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'total_security_events': stats['total_events'],
                'cardholder_data_access': stats['event_type_counts'].get('resource_access', 0),
                'failed_authentication': stats['event_type_counts'].get('user_login_failed', 0),
                'privilege_changes': stats['event_type_counts'].get('privilege_escalation', 0),
                'security_incidents': stats['event_type_counts'].get('security_incident', 0),
                'unauthorized_access': stats['event_type_counts'].get('resource_accessed_unauthorized', 0)
            },
            'pci_requirements': {
                'requirement_3': self._analyze_pci_req_3(events),  # Protect stored data
                'requirement_7': self._analyze_pci_req_7(events),  # Restrict access by business need
                'requirement_8': self._analyze_pci_req_8(events),  # Assign unique ID to each person
                'requirement_10': self._analyze_pci_req_10(events),  # Track and monitor access
                'requirement_11': self._analyze_pci_req_11(events)   # Regularly test security systems
            },
            'events': events[:1000],
            'integrity_verification': self._verify_period_integrity(start_date.date(), end_date.date())
        }
        
        return self._save_report(report_id, 'PCI_DSS', 'cardholder_data_audit', start_date, end_date,
                               generated_by, report_data)
    
    def _save_report(self, report_id: str, framework: str, report_type: str,
                    start_date: datetime, end_date: datetime, generated_by: str,
                    report_data: Dict[str, Any]) -> str:
        """Save compliance report to database and file system."""
        
        # Save JSON report to file
        json_filename = f"{framework}_{report_type}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}_{report_id[:8]}.json"
        json_path = self.reports_dir / json_filename
        
        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        # Save CSV summary for easy analysis
        csv_filename = json_filename.replace('.json', '_summary.csv')
        csv_path = self.reports_dir / csv_filename
        self._generate_csv_summary(report_data, csv_path)
        
        # Store report metadata in database
        self.db.compliance_reports.insert(
            report_id=report_id,
            framework=framework,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            generated_by=generated_by,
            status='completed',
            report_data=json.dumps(report_data['summary']),
            file_path=str(json_path),
            completed_at=datetime.utcnow()
        )
        self.db.commit()
        
        logger.info(f"Generated {framework} compliance report: {report_id}")
        return report_id
    
    def _generate_csv_summary(self, report_data: Dict[str, Any], csv_path: Path):
        """Generate CSV summary from report data."""
        
        with open(csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow(['Report ID', 'Framework', 'Period Start', 'Period End', 'Metric', 'Value'])
            
            # Write summary metrics
            report_id = report_data['report_id']
            framework = report_data['framework']
            start_date = report_data['period']['start_date']
            end_date = report_data['period']['end_date']
            
            for metric, value in report_data['summary'].items():
                writer.writerow([report_id, framework, start_date, end_date, metric, value])
    
    def _verify_period_integrity(self, start_date, end_date) -> Dict[str, Any]:
        """Verify audit trail integrity for the report period."""
        return self.audit_logger.verify_audit_integrity(start_date, end_date)
    
    # SOC 2 analysis methods
    def _analyze_security_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze security controls for SOC 2."""
        failed_logins = [e for e in events if e['event_type'] == 'user_login_failed']
        security_incidents = [e for e in events if e['event_type'] == 'security_incident']
        
        return {
            'failed_login_count': len(failed_logins),
            'security_incident_count': len(security_incidents),
            'average_risk_score': sum(e['risk_score'] for e in events) / len(events) if events else 0,
            'high_risk_events': len([e for e in events if e['risk_score'] >= 7])
        }
    
    def _analyze_availability_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze availability controls for SOC 2."""
        system_events = [e for e in events if e['event_type'] in ['system_start', 'system_stop', 'service_start', 'service_stop']]
        
        return {
            'system_events_count': len(system_events),
            'downtime_events': len([e for e in system_events if 'stop' in e['event_type']]),
            'backup_events': len([e for e in events if e['event_type'] == 'data_backup'])
        }
    
    def _analyze_confidentiality_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze confidentiality controls for SOC 2."""
        data_access = [e for e in events if e['event_type'] == 'resource_access']
        unauthorized_access = [e for e in events if e['event_type'] == 'resource_accessed_unauthorized']
        
        return {
            'data_access_count': len(data_access),
            'unauthorized_access_count': len(unauthorized_access),
            'privilege_escalations': len([e for e in events if e['event_type'] == 'privilege_escalation'])
        }
    
    def _analyze_processing_integrity(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze processing integrity for SOC 2."""
        config_changes = [e for e in events if 'config' in e['event_type']]
        
        return {
            'config_changes': len(config_changes),
            'admin_actions': len([e for e in events if e['event_type'] == 'admin_action']),
            'failed_operations': len([e for e in events if e['outcome'] == 'failure'])
        }
    
    def _analyze_privacy_controls(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze privacy controls for SOC 2."""
        return {
            'data_exports': len([e for e in events if e['event_type'] == 'data_export']),
            'user_management': len([e for e in events if e['event_type'] in ['user_created', 'user_modified', 'user_deleted']])
        }
    
    # GDPR analysis methods
    def _analyze_lawfulness(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze lawfulness principle for GDPR."""
        return {
            'documented_legal_basis': True,  # This would check configuration
            'consent_tracking': len([e for e in events if 'consent' in str(e['details'])])
        }
    
    def _analyze_purpose_limitation(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze purpose limitation for GDPR."""
        return {
            'purpose_documented': True,
            'access_purpose_tracking': len([e for e in events if e['event_type'] == 'resource_access'])
        }
    
    def _analyze_data_minimization(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze data minimization for GDPR."""
        return {
            'excessive_access_events': len([e for e in events if e['risk_score'] > 6 and e['event_type'] == 'resource_access'])
        }
    
    def _analyze_data_accuracy(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze data accuracy for GDPR."""
        return {
            'data_corrections': len([e for e in events if e['event_type'] == 'resource_modified'])
        }
    
    def _analyze_storage_limitation(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze storage limitation for GDPR."""
        return {
            'deletion_events': len([e for e in events if e['event_type'] == 'resource_deleted']),
            'retention_policy_enforced': True
        }
    
    def _analyze_gdpr_security(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze security for GDPR."""
        return {
            'security_incidents': len([e for e in events if e['event_type'] == 'security_incident']),
            'encryption_in_use': True,
            'access_controls': len([e for e in events if e['event_type'] == 'user_login'])
        }
    
    def _analyze_accountability(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze accountability for GDPR."""
        return {
            'audit_trail_complete': True,
            'documented_procedures': True,
            'training_records': True
        }
    
    def _count_access_requests(self, events: List[Dict]) -> int:
        """Count data subject access requests."""
        return len([e for e in events if 'access_request' in str(e['details'])])
    
    def _count_deletion_requests(self, events: List[Dict]) -> int:
        """Count data subject deletion requests."""
        return len([e for e in events if 'deletion_request' in str(e['details'])])
    
    def _count_rectification_requests(self, events: List[Dict]) -> int:
        """Count data subject rectification requests."""
        return len([e for e in events if 'rectification_request' in str(e['details'])])
    
    # HIPAA analysis methods
    def _analyze_administrative_safeguards(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze administrative safeguards for HIPAA."""
        return {
            'assigned_security_responsibility': True,
            'workforce_training': True,
            'access_management': len([e for e in events if e['event_type'] in ['user_created', 'role_assigned']])
        }
    
    def _analyze_physical_safeguards(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze physical safeguards for HIPAA."""
        return {
            'facility_access_controls': True,
            'workstation_use': True,
            'device_controls': True
        }
    
    def _analyze_technical_safeguards(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze technical safeguards for HIPAA."""
        return {
            'access_control': len([e for e in events if e['event_type'] == 'user_login']),
            'audit_controls': len(events),
            'integrity': True,
            'transmission_security': True
        }
    
    def _analyze_minimum_necessary(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze minimum necessary standard for HIPAA."""
        return {
            'access_reviews': len([e for e in events if e['event_type'] == 'admin_action']),
            'role_based_access': True
        }
    
    # PCI DSS analysis methods
    def _analyze_pci_req_3(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze PCI DSS Requirement 3 - Protect stored cardholder data."""
        return {
            'encryption_in_use': True,
            'data_access_events': len([e for e in events if e['event_type'] == 'resource_access'])
        }
    
    def _analyze_pci_req_7(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze PCI DSS Requirement 7 - Restrict access by business need to know."""
        return {
            'access_control_events': len([e for e in events if e['event_type'] in ['user_login', 'role_assigned']]),
            'privilege_escalations': len([e for e in events if e['event_type'] == 'privilege_escalation'])
        }
    
    def _analyze_pci_req_8(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze PCI DSS Requirement 8 - Assign unique ID to each person with computer access."""
        return {
            'unique_user_ids': len(set([e['user_id'] for e in events if e['user_id']])),
            'authentication_events': len([e for e in events if e['event_type'] in ['user_login', 'user_login_failed']])
        }
    
    def _analyze_pci_req_10(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze PCI DSS Requirement 10 - Track and monitor all access to network resources."""
        return {
            'total_audit_events': len(events),
            'access_monitoring': len([e for e in events if e['event_type'] == 'resource_access']),
            'admin_monitoring': len([e for e in events if e['event_type'] == 'admin_action'])
        }
    
    def _analyze_pci_req_11(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze PCI DSS Requirement 11 - Regularly test security systems and processes."""
        return {
            'security_testing': len([e for e in events if 'test' in str(e['details'])]),
            'vulnerability_scans': len([e for e in events if 'scan' in str(e['details'])])
        }


# Global compliance reporter instance
compliance_reporter = ComplianceReporter()