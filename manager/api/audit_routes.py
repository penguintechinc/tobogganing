"""Audit logging and compliance reporting API endpoints."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from py4web import action, request, response, abort, URL, HTTP
from py4web.utils.cors import cors

from database import get_db
from ..audit import audit_logger, AuditEventType, ComplianceFramework
from ..audit.compliance import compliance_reporter
from ..security.middleware import security_fixture, require_admin_role

logger = logging.getLogger(__name__)


@action('api/audit/events', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_audit_events():
    """Get audit events with filtering and pagination."""
    try:
        # Parse query parameters
        page = int(request.query.get('page', 1))
        limit = min(int(request.query.get('limit', 100)), 1000)  # Max 1000 events
        offset = (page - 1) * limit
        
        # Date filters
        start_date_str = request.query.get('start_date')
        end_date_str = request.query.get('end_date')
        
        start_date = None
        end_date = None
        
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        
        # Other filters
        user_id = request.query.get('user_id')
        event_types_str = request.query.get('event_types')
        severity_filter_str = request.query.get('severity')
        compliance_framework_str = request.query.get('compliance_framework')
        
        # Parse event types
        event_types = None
        if event_types_str:
            try:
                event_type_names = event_types_str.split(',')
                event_types = [AuditEventType(name.strip()) for name in event_type_names]
            except ValueError as e:
                return {
                    'success': False,
                    'error': f'Invalid event type: {e}'
                }
        
        # Parse severity filter
        severity_filter = None
        if severity_filter_str:
            severity_filter = [s.strip() for s in severity_filter_str.split(',')]
        
        # Parse compliance framework
        compliance_framework = None
        if compliance_framework_str:
            try:
                compliance_framework = ComplianceFramework(compliance_framework_str)
            except ValueError:
                return {
                    'success': False,
                    'error': f'Invalid compliance framework: {compliance_framework_str}'
                }
        
        # Get events
        events = audit_logger.get_audit_events(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            event_types=event_types,
            compliance_framework=compliance_framework,
            severity_filter=severity_filter,
            limit=limit,
            offset=offset
        )
        
        # Get total count for pagination
        db = get_db()
        query = db.audit_events.archived == False
        
        if start_date:
            query &= (db.audit_events.timestamp >= start_date)
        if end_date:
            query &= (db.audit_events.timestamp <= end_date)
        if user_id:
            query &= (db.audit_events.user_id == user_id)
        if event_types:
            type_values = [et.value for et in event_types]
            query &= db.audit_events.event_type.belongs(type_values)
        if severity_filter:
            query &= db.audit_events.severity.belongs(severity_filter)
        
        total_count = db(query).count()
        total_pages = (total_count + limit - 1) // limit
        
        return {
            'success': True,
            'data': {
                'events': events,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': total_pages
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get audit events: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/audit/events', method=['POST'])
@action.uses(security_fixture, cors())
def log_audit_event():
    """Log a new audit event."""
    try:
        data = request.json or {}
        
        # Validate required fields
        if 'event_type' not in data:
            return {
                'success': False,
                'error': 'event_type is required'
            }
        
        if 'action' not in data:
            return {
                'success': False,
                'error': 'action is required'
            }
        
        # Parse event type
        try:
            event_type = AuditEventType(data['event_type'])
        except ValueError:
            return {
                'success': False,
                'error': f'Invalid event type: {data["event_type"]}'
            }
        
        # Extract client IP
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', 
                                       request.environ.get('HTTP_X_REAL_IP',
                                       request.environ.get('REMOTE_ADDR', 'unknown')))
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        
        # Log the event
        event_id = audit_logger.log_event(
            event_type=event_type,
            user_id=data.get('user_id'),
            user_email=data.get('user_email'),
            ip_address=ip_address,
            user_agent=request.environ.get('HTTP_USER_AGENT', ''),
            resource_type=data.get('resource_type'),
            resource_id=data.get('resource_id'),
            action=data['action'],
            details=data.get('details', {}),
            severity=data.get('severity', 'info'),
            session_id=data.get('session_id'),
            request_id=data.get('request_id'),
            outcome=data.get('outcome', 'success'),
            custom_risk_score=data.get('risk_score')
        )
        
        return {
            'success': True,
            'data': {
                'event_id': event_id
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/audit/statistics', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_audit_statistics():
    """Get audit statistics for a time period."""
    try:
        # Parse query parameters
        start_date_str = request.query.get('start_date')
        end_date_str = request.query.get('end_date')
        compliance_framework_str = request.query.get('compliance_framework')
        
        # Default to last 30 days if no dates provided
        if not start_date_str:
            start_date = datetime.utcnow() - timedelta(days=30)
        else:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        
        if not end_date_str:
            end_date = datetime.utcnow()
        else:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        
        # Parse compliance framework
        compliance_framework = None
        if compliance_framework_str:
            try:
                compliance_framework = ComplianceFramework(compliance_framework_str)
            except ValueError:
                return {
                    'success': False,
                    'error': f'Invalid compliance framework: {compliance_framework_str}'
                }
        
        # Get statistics
        stats = audit_logger.get_audit_statistics(start_date, end_date, compliance_framework)
        
        return {
            'success': True,
            'data': stats
        }
    
    except Exception as e:
        logger.error(f"Failed to get audit statistics: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/audit/integrity/verify', method=['POST'])
@action.uses(security_fixture, cors())
@require_admin_role
def verify_audit_integrity():
    """Verify audit trail integrity for a date range."""
    try:
        data = request.json or {}
        
        # Parse dates
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        if not start_date_str or not end_date_str:
            return {
                'success': False,
                'error': 'start_date and end_date are required'
            }
        
        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).date()
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
        
        # Verify integrity
        integrity_result = audit_logger.verify_audit_integrity(start_date, end_date)
        
        return {
            'success': True,
            'data': integrity_result
        }
    
    except Exception as e:
        logger.error(f"Failed to verify audit integrity: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/audit/compliance/reports', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_compliance_reports():
    """Get list of compliance reports."""
    try:
        db = get_db()
        
        # Parse query parameters
        framework = request.query.get('framework')
        status = request.query.get('status')
        page = int(request.query.get('page', 1))
        limit = min(int(request.query.get('limit', 50)), 100)
        offset = (page - 1) * limit
        
        # Build query
        query = db.compliance_reports.id > 0
        
        if framework:
            query &= (db.compliance_reports.framework == framework)
        if status:
            query &= (db.compliance_reports.status == status)
        
        # Get reports
        reports = db(query).select(
            orderby=~db.compliance_reports.created_at,
            limitby=(offset, offset + limit)
        )
        
        # Get total count
        total_count = db(query).count()
        total_pages = (total_count + limit - 1) // limit
        
        # Format reports
        formatted_reports = []
        for report in reports:
            formatted_reports.append({
                'report_id': report.report_id,
                'framework': report.framework,
                'report_type': report.report_type,
                'start_date': report.start_date.isoformat() if report.start_date else None,
                'end_date': report.end_date.isoformat() if report.end_date else None,
                'generated_by': report.generated_by,
                'status': report.status,
                'created_at': report.created_at.isoformat() if report.created_at else None,
                'completed_at': report.completed_at.isoformat() if report.completed_at else None,
                'file_path': report.file_path
            })
        
        return {
            'success': True,
            'data': {
                'reports': formatted_reports,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': total_pages
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get compliance reports: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/audit/compliance/reports', method=['POST'])
@action.uses(security_fixture, cors())
@require_admin_role
def generate_compliance_report():
    """Generate a new compliance report."""
    try:
        data = request.json or {}
        
        # Validate required fields
        required_fields = ['framework', 'start_date', 'end_date']
        for field in required_fields:
            if field not in data:
                return {
                    'success': False,
                    'error': f'{field} is required'
                }
        
        # Parse framework
        framework = data['framework'].upper()
        if framework not in ['SOC2', 'GDPR', 'HIPAA', 'PCI_DSS']:
            return {
                'success': False,
                'error': f'Unsupported framework: {framework}'
            }
        
        # Parse dates
        start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
        
        # Get user info
        user = request.environ.get('user', {})
        generated_by = user.get('username', 'unknown')
        
        # Generate report based on framework
        if framework == 'SOC2':
            report_id = compliance_reporter.generate_soc2_report(start_date, end_date, generated_by)
        elif framework == 'GDPR':
            report_id = compliance_reporter.generate_gdpr_report(start_date, end_date, generated_by)
        elif framework == 'HIPAA':
            report_id = compliance_reporter.generate_hipaa_report(start_date, end_date, generated_by)
        elif framework == 'PCI_DSS':
            report_id = compliance_reporter.generate_pci_dss_report(start_date, end_date, generated_by)
        
        # Log the report generation
        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_ACTION,
            user_id=user.get('id'),
            user_email=user.get('email'),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown'),
            user_agent=request.environ.get('HTTP_USER_AGENT', ''),
            resource_type='compliance_report',
            resource_id=report_id,
            action=f'generate_{framework}_report',
            details={
                'framework': framework,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            severity='info',
            outcome='success'
        )
        
        return {
            'success': True,
            'data': {
                'report_id': report_id,
                'message': f'{framework} compliance report generated successfully'
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to generate compliance report: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/audit/compliance/reports/<report_id>', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_compliance_report(report_id):
    """Get a specific compliance report."""
    try:
        db = get_db()
        
        # Get report metadata
        report = db(db.compliance_reports.report_id == report_id).select().first()
        
        if not report:
            return {
                'success': False,
                'error': 'Report not found'
            }
        
        # Read report data from file if available
        report_data = None
        if report.file_path and os.path.exists(report.file_path):
            try:
                with open(report.file_path, 'r') as f:
                    report_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not read report file: {e}")
        
        # Format response
        response_data = {
            'report_id': report.report_id,
            'framework': report.framework,
            'report_type': report.report_type,
            'start_date': report.start_date.isoformat() if report.start_date else None,
            'end_date': report.end_date.isoformat() if report.end_date else None,
            'generated_by': report.generated_by,
            'status': report.status,
            'created_at': report.created_at.isoformat() if report.created_at else None,
            'completed_at': report.completed_at.isoformat() if report.completed_at else None,
            'summary': json.loads(report.report_data) if report.report_data else {},
            'full_report': report_data
        }
        
        return {
            'success': True,
            'data': response_data
        }
    
    except Exception as e:
        logger.error(f"Failed to get compliance report: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/audit/compliance/frameworks', method=['GET'])
@action.uses(security_fixture, cors())
def get_compliance_frameworks():
    """Get list of supported compliance frameworks."""
    frameworks = [
        {
            'code': 'SOC2',
            'name': 'SOC 2',
            'description': 'Service Organization Control 2 - Security, Availability, Confidentiality'
        },
        {
            'code': 'GDPR',
            'name': 'GDPR',
            'description': 'General Data Protection Regulation - EU Privacy Law'
        },
        {
            'code': 'HIPAA',
            'name': 'HIPAA',
            'description': 'Health Insurance Portability and Accountability Act'
        },
        {
            'code': 'PCI_DSS',
            'name': 'PCI DSS',
            'description': 'Payment Card Industry Data Security Standard'
        },
        {
            'code': 'ISO27001',
            'name': 'ISO 27001',
            'description': 'Information Security Management Systems'
        },
        {
            'code': 'NIST',
            'name': 'NIST Cybersecurity Framework',
            'description': 'National Institute of Standards and Technology Framework'
        }
    ]
    
    return {
        'success': True,
        'data': {
            'frameworks': frameworks
        }
    }


@action('api/audit/event-types', method=['GET'])
@action.uses(security_fixture, cors())
def get_audit_event_types():
    """Get list of audit event types."""
    event_types = []
    
    for event_type in AuditEventType:
        event_types.append({
            'code': event_type.value,
            'name': event_type.name,
            'description': event_type.value.replace('_', ' ').title()
        })
    
    return {
        'success': True,
        'data': {
            'event_types': event_types
        }
    }