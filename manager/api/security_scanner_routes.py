"""Security scanner and threat feeds API endpoints."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from py4web import action, request, response, abort, URL, HTTP
from py4web.utils.cors import cors

from database import get_db
from ..security.feeds import security_feeds_manager, FeedSource, ThreatType
from ..security.scanner import security_scanner, ScanType, ScanSeverity
from ..security.middleware import security_fixture, require_admin_role
from ..audit import audit_logger, AuditEventType

logger = logging.getLogger(__name__)


# Security Feeds Endpoints

@action('api/security/feeds/status', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_feeds_status():
    """Get status of all security feeds."""
    try:
        db = get_db()
        
        # Get recent feed updates
        recent_updates = db(
            db.feed_updates.started_at > (datetime.utcnow() - timedelta(hours=24))
        ).select(orderby=~db.feed_updates.started_at, limitby=(0, 20))
        
        # Get active indicators count by source
        indicator_counts = db().select(
            db.threat_indicators.source,
            db.threat_indicators.id.count(),
            groupby=db.threat_indicators.source,
            having=(db.threat_indicators.active == True)
        )
        
        source_counts = {}
        for row in indicator_counts:
            source_counts[row.threat_indicators.source] = row._extra[db.threat_indicators.id.count()]
        
        # Format recent updates
        formatted_updates = []
        for update in recent_updates:
            formatted_updates.append({
                'source': update.source,
                'update_type': update.update_type,
                'status': update.status,
                'indicators_added': update.indicators_added,
                'indicators_updated': update.indicators_updated,
                'indicators_removed': update.indicators_removed,
                'error_message': update.error_message,
                'duration_seconds': update.duration_seconds,
                'started_at': update.started_at.isoformat() if update.started_at else None,
                'completed_at': update.completed_at.isoformat() if update.completed_at else None
            })
        
        # Get threat detection statistics
        threat_stats = security_feeds_manager.get_threat_statistics(24)
        
        return {
            'success': True,
            'data': {
                'indicators_by_source': source_counts,
                'recent_updates': formatted_updates,
                'threat_statistics': threat_stats,
                'available_sources': [source.value for source in FeedSource],
                'threat_types': [threat_type.value for threat_type in ThreatType]
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get feeds status: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/feeds/update', method=['POST'])
@action.uses(security_fixture, cors())
@require_admin_role
def update_security_feeds():
    """Manually trigger security feeds update."""
    try:
        data = request.json or {}
        source_name = data.get('source')
        
        if not source_name:
            return {
                'success': False,
                'error': 'source parameter is required'
            }
        
        try:
            source = FeedSource(source_name)
        except ValueError:
            return {
                'success': False,
                'error': f'Invalid source: {source_name}'
            }
        
        # Get user info
        user = request.environ.get('user', {})
        
        # Trigger manual update (this would be async in production)
        # For now, return success immediately
        
        # Log audit event
        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_ACTION,
            user_id=user.get('id'),
            user_email=user.get('email'),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown'),
            user_agent=request.environ.get('HTTP_USER_AGENT', ''),
            resource_type='threat_feed',
            resource_id=source_name,
            action='manual_update_trigger',
            details={
                'source': source_name,
                'trigger_type': 'manual'
            },
            severity='info',
            outcome='success'
        )
        
        return {
            'success': True,
            'message': f'Update triggered for {source_name} feed'
        }
    
    except Exception as e:
        logger.error(f"Failed to update security feeds: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/feeds/check', method=['POST'])
@action.uses(security_fixture, cors())
def check_threat_indicator():
    """Check if a value is a known threat indicator."""
    try:
        data = request.json or {}
        
        value = data.get('value')
        indicator_type = data.get('type')  # 'ip' or 'domain'
        
        if not value:
            return {
                'success': False,
                'error': 'value parameter is required'
            }
        
        # Check threat indicator
        is_threat, threat_details = security_feeds_manager.check_threat_indicator(value, indicator_type)
        
        return {
            'success': True,
            'data': {
                'value': value,
                'is_threat': is_threat,
                'threat_details': threat_details
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to check threat indicator: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/feeds/detections', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_threat_detections():
    """Get recent threat detections."""
    try:
        db = get_db()
        
        # Parse query parameters
        page = int(request.query.get('page', 1))
        limit = min(int(request.query.get('limit', 50)), 100)
        offset = (page - 1) * limit
        
        hours_back = int(request.query.get('hours_back', 24))
        since = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Get detections
        query = db.threat_detections.detected_at >= since
        
        detections = db(query).select(
            orderby=~db.threat_detections.detected_at,
            limitby=(offset, offset + limit)
        )
        
        # Get total count
        total_count = db(query).count()
        total_pages = (total_count + limit - 1) // limit
        
        # Format detections
        formatted_detections = []
        for detection in detections:
            formatted_detections.append({
                'client_ip': detection.client_ip,
                'requested_domain': detection.requested_domain,
                'requested_ip': detection.requested_ip,
                'action_taken': detection.action_taken,
                'threat_types': json.loads(detection.threat_types) if detection.threat_types else [],
                'confidence': detection.confidence,
                'source': detection.source,
                'metadata': json.loads(detection.metadata) if detection.metadata else {},
                'detected_at': detection.detected_at.isoformat() if detection.detected_at else None
            })
        
        return {
            'success': True,
            'data': {
                'detections': formatted_detections,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': total_pages
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get threat detections: {e}")
        return {
            'success': False,
            'error': str(e)
        }


# Security Scanner Endpoints

@action('api/security/scans', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_security_scans():
    """Get security scans with filtering and pagination."""
    try:
        db = get_db()
        
        # Parse query parameters
        page = int(request.query.get('page', 1))
        limit = min(int(request.query.get('limit', 50)), 100)
        offset = (page - 1) * limit
        
        scan_type = request.query.get('scan_type')
        status = request.query.get('status')
        days_back = int(request.query.get('days_back', 30))
        
        # Build query
        since = datetime.utcnow() - timedelta(days=days_back)
        query = db.security_scans.started_at >= since
        
        if scan_type:
            query &= (db.security_scans.scan_type == scan_type)
        if status:
            query &= (db.security_scans.status == status)
        
        # Get scans
        scans = db(query).select(
            orderby=~db.security_scans.started_at,
            limitby=(offset, offset + limit)
        )
        
        # Get total count
        total_count = db(query).count()
        total_pages = (total_count + limit - 1) // limit
        
        # Format scans
        formatted_scans = []
        for scan in scans:
            formatted_scans.append({
                'scan_id': scan.scan_id,
                'scan_type': scan.scan_type,
                'target': scan.target,
                'status': scan.status,
                'findings_count': scan.findings_count,
                'critical_findings': scan.critical_findings,
                'high_findings': scan.high_findings,
                'medium_findings': scan.medium_findings,
                'low_findings': scan.low_findings,
                'scan_duration': scan.scan_duration,
                'error_message': scan.error_message,
                'started_at': scan.started_at.isoformat() if scan.started_at else None,
                'completed_at': scan.completed_at.isoformat() if scan.completed_at else None,
                'triggered_by': scan.triggered_by,
                'tools_used': json.loads(scan.tools_used) if scan.tools_used else []
            })
        
        return {
            'success': True,
            'data': {
                'scans': formatted_scans,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': total_pages
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get security scans: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/scans', method=['POST'])
@action.uses(security_fixture, cors())
@require_admin_role
def trigger_security_scan():
    """Manually trigger a security scan."""
    try:
        data = request.json or {}
        
        scan_type_name = data.get('scan_type')
        target = data.get('target', 'infrastructure')
        
        if not scan_type_name:
            return {
                'success': False,
                'error': 'scan_type parameter is required'
            }
        
        try:
            scan_type = ScanType(scan_type_name)
        except ValueError:
            return {
                'success': False,
                'error': f'Invalid scan type: {scan_type_name}'
            }
        
        # Get user info
        user = request.environ.get('user', {})
        
        # For now, just record the scan request
        # In production, this would trigger the actual scan
        scan_id = f"manual_{scan_type_name}_{int(datetime.utcnow().timestamp())}"
        
        db = get_db()
        scan_record_id = db.security_scans.insert(
            scan_id=scan_id,
            scan_type=scan_type.value,
            target=target,
            status='pending',
            started_at=datetime.utcnow(),
            triggered_by=user.get('username', 'unknown'),
            metadata=json.dumps({'trigger_type': 'manual', 'user': user.get('username')})
        )
        db.commit()
        
        # Log audit event
        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_ACTION,
            user_id=user.get('id'),
            user_email=user.get('email'),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown'),
            user_agent=request.environ.get('HTTP_USER_AGENT', ''),
            resource_type='security_scan',
            resource_id=scan_id,
            action='manual_scan_trigger',
            details={
                'scan_type': scan_type_name,
                'target': target,
                'trigger_type': 'manual'
            },
            severity='info',
            outcome='success'
        )
        
        return {
            'success': True,
            'data': {
                'scan_id': scan_id,
                'message': f'{scan_type_name} scan triggered successfully'
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to trigger security scan: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/scans/<scan_id>', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_security_scan(scan_id):
    """Get details of a specific security scan."""
    try:
        db = get_db()
        
        # Get scan
        scan = db(db.security_scans.scan_id == scan_id).select().first()
        
        if not scan:
            return {
                'success': False,
                'error': 'Scan not found'
            }
        
        # Get findings for this scan
        findings = db(db.security_findings.scan_id == scan_id).select(
            orderby=db.security_findings.severity
        )
        
        # Format findings
        formatted_findings = []
        for finding in findings:
            formatted_findings.append({
                'finding_id': finding.finding_id,
                'finding_type': finding.finding_type,
                'severity': finding.severity,
                'title': finding.title,
                'description': finding.description,
                'affected_component': finding.affected_component,
                'recommendation': finding.recommendation,
                'cve_ids': json.loads(finding.cve_ids) if finding.cve_ids else [],
                'cvss_score': finding.cvss_score,
                'confidence': finding.confidence,
                'status': finding.status,
                'first_seen': finding.first_seen.isoformat() if finding.first_seen else None,
                'last_seen': finding.last_seen.isoformat() if finding.last_seen else None,
                'metadata': json.loads(finding.metadata) if finding.metadata else {}
            })
        
        # Format scan
        formatted_scan = {
            'scan_id': scan.scan_id,
            'scan_type': scan.scan_type,
            'target': scan.target,
            'status': scan.status,
            'findings_count': scan.findings_count,
            'critical_findings': scan.critical_findings,
            'high_findings': scan.high_findings,
            'medium_findings': scan.medium_findings,
            'low_findings': scan.low_findings,
            'scan_duration': scan.scan_duration,
            'error_message': scan.error_message,
            'started_at': scan.started_at.isoformat() if scan.started_at else None,
            'completed_at': scan.completed_at.isoformat() if scan.completed_at else None,
            'triggered_by': scan.triggered_by,
            'tools_used': json.loads(scan.tools_used) if scan.tools_used else [],
            'metadata': json.loads(scan.metadata) if scan.metadata else {},
            'findings': formatted_findings
        }
        
        return {
            'success': True,
            'data': formatted_scan
        }
    
    except Exception as e:
        logger.error(f"Failed to get security scan: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/findings', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_security_findings():
    """Get security findings with filtering and pagination."""
    try:
        db = get_db()
        
        # Parse query parameters
        page = int(request.query.get('page', 1))
        limit = min(int(request.query.get('limit', 50)), 100)
        offset = (page - 1) * limit
        
        severity = request.query.get('severity')
        finding_type = request.query.get('finding_type')
        status = request.query.get('status', 'open')
        days_back = int(request.query.get('days_back', 30))
        
        # Build query
        since = datetime.utcnow() - timedelta(days=days_back)
        query = db.security_findings.first_seen >= since
        
        if severity:
            query &= (db.security_findings.severity == severity)
        if finding_type:
            query &= (db.security_findings.finding_type == finding_type)
        if status:
            query &= (db.security_findings.status == status)
        
        # Get findings
        findings = db(query).select(
            orderby=[~db.security_findings.severity, ~db.security_findings.first_seen],
            limitby=(offset, offset + limit)
        )
        
        # Get total count
        total_count = db(query).count()
        total_pages = (total_count + limit - 1) // limit
        
        # Format findings
        formatted_findings = []
        for finding in findings:
            formatted_findings.append({
                'finding_id': finding.finding_id,
                'scan_id': finding.scan_id,
                'finding_type': finding.finding_type,
                'severity': finding.severity,
                'title': finding.title,
                'description': finding.description,
                'affected_component': finding.affected_component,
                'recommendation': finding.recommendation,
                'cve_ids': json.loads(finding.cve_ids) if finding.cve_ids else [],
                'cvss_score': finding.cvss_score,
                'confidence': finding.confidence,
                'status': finding.status,
                'first_seen': finding.first_seen.isoformat() if finding.first_seen else None,
                'last_seen': finding.last_seen.isoformat() if finding.last_seen else None,
                'metadata': json.loads(finding.metadata) if finding.metadata else {}
            })
        
        return {
            'success': True,
            'data': {
                'findings': formatted_findings,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': total_pages
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get security findings: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/findings/<finding_id>/status', method=['PUT'])
@action.uses(security_fixture, cors())
@require_admin_role
def update_finding_status(finding_id):
    """Update the status of a security finding."""
    try:
        data = request.json or {}
        new_status = data.get('status')
        
        if not new_status:
            return {
                'success': False,
                'error': 'status parameter is required'
            }
        
        if new_status not in ['open', 'resolved', 'false_positive', 'accepted_risk']:
            return {
                'success': False,
                'error': 'Invalid status value'
            }
        
        db = get_db()
        
        # Update finding
        updated = db(db.security_findings.finding_id == finding_id).update(
            status=new_status,
            remediated_at=datetime.utcnow() if new_status != 'open' else None,
            false_positive=(new_status == 'false_positive')
        )
        
        if not updated:
            return {
                'success': False,
                'error': 'Finding not found'
            }
        
        db.commit()
        
        # Get user info
        user = request.environ.get('user', {})
        
        # Log audit event
        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_ACTION,
            user_id=user.get('id'),
            user_email=user.get('email'),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown'),
            user_agent=request.environ.get('HTTP_USER_AGENT', ''),
            resource_type='security_finding',
            resource_id=finding_id,
            action='update_finding_status',
            details={
                'new_status': new_status,
                'previous_status': data.get('previous_status', 'unknown')
            },
            severity='info',
            outcome='success'
        )
        
        return {
            'success': True,
            'message': f'Finding status updated to {new_status}'
        }
    
    except Exception as e:
        logger.error(f"Failed to update finding status: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/dashboard', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_security_dashboard():
    """Get security dashboard summary."""
    try:
        db = get_db()
        
        # Get summary statistics
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)
        
        # Active threat indicators
        active_indicators = db(db.threat_indicators.active == True).count()
        
        # Recent threat detections
        recent_detections = db(db.threat_detections.detected_at >= last_24h).count()
        
        # Open security findings by severity
        open_findings = db(db.security_findings.status == 'open').select(
            db.security_findings.severity,
            db.security_findings.id.count(),
            groupby=db.security_findings.severity
        )
        
        findings_by_severity = {}
        for row in open_findings:
            findings_by_severity[row.security_findings.severity] = row._extra[db.security_findings.id.count()]
        
        # Recent scans
        recent_scans = db(db.security_scans.started_at >= last_7d).select(
            db.security_scans.status,
            db.security_scans.id.count(),
            groupby=db.security_scans.status
        )
        
        scans_by_status = {}
        for row in recent_scans:
            scans_by_status[row.security_scans.status] = row._extra[db.security_scans.id.count()]
        
        # Top threat sources
        threat_sources = db(db.threat_detections.detected_at >= last_7d).select(
            db.threat_detections.source,
            db.threat_detections.id.count(),
            groupby=db.threat_detections.source,
            orderby=~db.threat_detections.id.count(),
            limitby=(0, 5)
        )
        
        top_sources = []
        for row in threat_sources:
            if row.threat_detections.source:
                top_sources.append({
                    'source': row.threat_detections.source,
                    'count': row._extra[db.threat_detections.id.count()]
                })
        
        return {
            'success': True,
            'data': {
                'active_indicators': active_indicators,
                'recent_detections_24h': recent_detections,
                'open_findings_by_severity': findings_by_severity,
                'recent_scans_by_status': scans_by_status,
                'top_threat_sources_7d': top_sources,
                'summary': {
                    'critical_findings': findings_by_severity.get('critical', 0),
                    'high_findings': findings_by_severity.get('high', 0),
                    'total_open_findings': sum(findings_by_severity.values()),
                    'total_scans_7d': sum(scans_by_status.values())
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get security dashboard: {e}")
        return {
            'success': False,
            'error': str(e)
        }