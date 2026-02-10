"""Analytics and monitoring functionality for SASEWaddle Manager."""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
import logging

from database import get_db
from pydal import DAL

logger = logging.getLogger(__name__)


class AnalyticsManager:
    """Manages analytics data collection and reporting."""
    
    def __init__(self):
        self.db = get_db()
        self._ensure_analytics_tables()
    
    def _ensure_analytics_tables(self):
        """Create analytics tables if they don't exist."""
        db = self.db
        
        # Client analytics table
        if 'client_analytics' not in db.tables:
            db.define_table('client_analytics',
                db.Field('client_id', 'string', length=64, required=True),
                db.Field('hostname', 'string', length=255),
                db.Field('os_name', 'string', length=64),  # Windows, macOS, Linux, etc.
                db.Field('os_version', 'string', length=128),  # 10.0.19041, 12.6.1, 5.15.0-56
                db.Field('architecture', 'string', length=32),  # x64, arm64, x86
                db.Field('client_version', 'string', length=64),  # SASEWaddle client version
                db.Field('ip_address', 'string', length=45),  # IPv4/IPv6
                db.Field('connected_headend', 'string', length=128),
                db.Field('connection_duration', 'integer'),  # seconds
                db.Field('bytes_sent', 'bigint', default=0),
                db.Field('bytes_received', 'bigint', default=0),
                db.Field('packets_sent', 'bigint', default=0),
                db.Field('packets_received', 'bigint', default=0),
                db.Field('last_seen', 'datetime', required=True),
                db.Field('created_at', 'datetime', default=datetime.utcnow),
                db.Field('updated_at', 'datetime', default=datetime.utcnow, update=datetime.utcnow)
            )
            # Create indexes
            db.executesql('CREATE INDEX idx_client_analytics_client_id ON client_analytics(client_id)')
            db.executesql('CREATE INDEX idx_client_analytics_os_name ON client_analytics(os_name)')
            db.executesql('CREATE INDEX idx_client_analytics_last_seen ON client_analytics(last_seen)')
            db.executesql('CREATE INDEX idx_client_analytics_headend ON client_analytics(connected_headend)')
        
        # Headend analytics table
        if 'headend_analytics' not in db.tables:
            db.define_table('headend_analytics',
                db.Field('headend_id', 'string', length=128, required=True),
                db.Field('hostname', 'string', length=255),
                db.Field('region', 'string', length=64),
                db.Field('cluster_id', 'string', length=128),
                db.Field('version', 'string', length=64),
                db.Field('active_connections', 'integer', default=0),
                db.Field('total_connections', 'bigint', default=0),
                db.Field('bytes_proxied', 'bigint', default=0),
                db.Field('packets_proxied', 'bigint', default=0),
                db.Field('cpu_usage_percent', 'double'),  # 0-100
                db.Field('memory_usage_mb', 'integer'),
                db.Field('disk_usage_percent', 'double'),  # 0-100
                db.Field('network_errors', 'integer', default=0),
                db.Field('auth_successes', 'integer', default=0),
                db.Field('auth_failures', 'integer', default=0),
                db.Field('last_heartbeat', 'datetime', required=True),
                db.Field('created_at', 'datetime', default=datetime.utcnow),
                db.Field('updated_at', 'datetime', default=datetime.utcnow, update=datetime.utcnow)
            )
            # Create indexes
            db.executesql('CREATE INDEX idx_headend_analytics_headend_id ON headend_analytics(headend_id)')
            db.executesql('CREATE INDEX idx_headend_analytics_region ON headend_analytics(region)')
            db.executesql('CREATE INDEX idx_headend_analytics_last_heartbeat ON headend_analytics(last_heartbeat)')
        
        # Traffic statistics table (aggregated by time periods)
        if 'traffic_stats' not in db.tables:
            db.define_table('traffic_stats',
                db.Field('stat_type', 'string', length=32),  # 'hourly', 'daily', 'monthly'
                db.Field('timestamp', 'datetime', required=True),
                db.Field('headend_id', 'string', length=128),
                db.Field('client_count', 'integer', default=0),
                db.Field('total_bytes', 'bigint', default=0),
                db.Field('total_packets', 'bigint', default=0),
                db.Field('unique_users', 'integer', default=0),
                db.Field('avg_connection_duration', 'integer', default=0),  # seconds
                db.Field('peak_concurrent_connections', 'integer', default=0),
                db.Field('created_at', 'datetime', default=datetime.utcnow)
            )
            # Create indexes
            db.executesql('CREATE INDEX idx_traffic_stats_type_time ON traffic_stats(stat_type, timestamp)')
            db.executesql('CREATE INDEX idx_traffic_stats_headend ON traffic_stats(headend_id)')
        
        db.commit()
        logger.info("Analytics tables ensured")
    
    def record_client_activity(self, client_data: Dict[str, Any]) -> bool:
        """Record or update client activity data."""
        try:
            db = self.db
            
            # Check if client already exists
            existing = db(db.client_analytics.client_id == client_data['client_id']).select().first()
            
            if existing:
                # Update existing record
                db(db.client_analytics.client_id == client_data['client_id']).update(
                    hostname=client_data.get('hostname', existing.hostname),
                    os_name=client_data.get('os_name', existing.os_name),
                    os_version=client_data.get('os_version', existing.os_version),
                    architecture=client_data.get('architecture', existing.architecture),
                    client_version=client_data.get('client_version', existing.client_version),
                    ip_address=client_data.get('ip_address', existing.ip_address),
                    connected_headend=client_data.get('connected_headend', existing.connected_headend),
                    connection_duration=client_data.get('connection_duration', existing.connection_duration),
                    bytes_sent=client_data.get('bytes_sent', existing.bytes_sent),
                    bytes_received=client_data.get('bytes_received', existing.bytes_received),
                    packets_sent=client_data.get('packets_sent', existing.packets_sent),
                    packets_received=client_data.get('packets_received', existing.packets_received),
                    last_seen=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            else:
                # Insert new record
                db.client_analytics.insert(
                    client_id=client_data['client_id'],
                    hostname=client_data.get('hostname'),
                    os_name=client_data.get('os_name'),
                    os_version=client_data.get('os_version'),
                    architecture=client_data.get('architecture'),
                    client_version=client_data.get('client_version'),
                    ip_address=client_data.get('ip_address'),
                    connected_headend=client_data.get('connected_headend'),
                    connection_duration=client_data.get('connection_duration', 0),
                    bytes_sent=client_data.get('bytes_sent', 0),
                    bytes_received=client_data.get('bytes_received', 0),
                    packets_sent=client_data.get('packets_sent', 0),
                    packets_received=client_data.get('packets_received', 0),
                    last_seen=datetime.utcnow()
                )
            
            db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to record client activity: {e}")
            db.rollback()
            return False
    
    def record_headend_stats(self, headend_data: Dict[str, Any]) -> bool:
        """Record or update headend statistics."""
        try:
            db = self.db
            
            # Check if headend already exists
            existing = db(db.headend_analytics.headend_id == headend_data['headend_id']).select().first()
            
            if existing:
                # Update existing record
                db(db.headend_analytics.headend_id == headend_data['headend_id']).update(
                    hostname=headend_data.get('hostname', existing.hostname),
                    region=headend_data.get('region', existing.region),
                    cluster_id=headend_data.get('cluster_id', existing.cluster_id),
                    version=headend_data.get('version', existing.version),
                    active_connections=headend_data.get('active_connections', existing.active_connections),
                    total_connections=headend_data.get('total_connections', existing.total_connections),
                    bytes_proxied=headend_data.get('bytes_proxied', existing.bytes_proxied),
                    packets_proxied=headend_data.get('packets_proxied', existing.packets_proxied),
                    cpu_usage_percent=headend_data.get('cpu_usage_percent', existing.cpu_usage_percent),
                    memory_usage_mb=headend_data.get('memory_usage_mb', existing.memory_usage_mb),
                    disk_usage_percent=headend_data.get('disk_usage_percent', existing.disk_usage_percent),
                    network_errors=headend_data.get('network_errors', existing.network_errors),
                    auth_successes=headend_data.get('auth_successes', existing.auth_successes),
                    auth_failures=headend_data.get('auth_failures', existing.auth_failures),
                    last_heartbeat=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            else:
                # Insert new record
                db.headend_analytics.insert(
                    headend_id=headend_data['headend_id'],
                    hostname=headend_data.get('hostname'),
                    region=headend_data.get('region'),
                    cluster_id=headend_data.get('cluster_id'),
                    version=headend_data.get('version'),
                    active_connections=headend_data.get('active_connections', 0),
                    total_connections=headend_data.get('total_connections', 0),
                    bytes_proxied=headend_data.get('bytes_proxied', 0),
                    packets_proxied=headend_data.get('packets_proxied', 0),
                    cpu_usage_percent=headend_data.get('cpu_usage_percent'),
                    memory_usage_mb=headend_data.get('memory_usage_mb'),
                    disk_usage_percent=headend_data.get('disk_usage_percent'),
                    network_errors=headend_data.get('network_errors', 0),
                    auth_successes=headend_data.get('auth_successes', 0),
                    auth_failures=headend_data.get('auth_failures', 0),
                    last_heartbeat=datetime.utcnow()
                )
            
            db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to record headend stats: {e}")
            db.rollback()
            return False
    
    def get_os_statistics(self, days_back: int = 7) -> Dict[str, Any]:
        """Get operating system distribution statistics."""
        try:
            db = self.db
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            # Get OS distribution
            os_query = """
                SELECT os_name, os_version, architecture, COUNT(*) as count,
                       AVG(connection_duration) as avg_duration,
                       SUM(bytes_sent + bytes_received) as total_bytes
                FROM client_analytics 
                WHERE last_seen >= %s AND os_name IS NOT NULL
                GROUP BY os_name, os_version, architecture
                ORDER BY count DESC
            """
            
            os_results = db.executesql(os_query, [cutoff_date])
            
            # Process results
            os_stats = {
                'total_clients': 0,
                'by_os': defaultdict(lambda: {'count': 0, 'versions': defaultdict(int), 'architectures': defaultdict(int)}),
                'by_architecture': defaultdict(int),
                'active_last_24h': 0,
                'active_last_hour': 0
            }
            
            for row in os_results:
                os_name, os_version, arch, count, avg_duration, total_bytes = row
                os_stats['total_clients'] += count
                os_stats['by_os'][os_name]['count'] += count
                if os_version:
                    os_stats['by_os'][os_name]['versions'][os_version] += count
                if arch:
                    os_stats['by_os'][os_name]['architectures'][arch] += count
                    os_stats['by_architecture'][arch] += count
            
            # Get recent activity counts
            last_24h = datetime.utcnow() - timedelta(hours=24)
            last_hour = datetime.utcnow() - timedelta(hours=1)
            
            os_stats['active_last_24h'] = db(db.client_analytics.last_seen >= last_24h).count()
            os_stats['active_last_hour'] = db(db.client_analytics.last_seen >= last_hour).count()
            
            # Convert defaultdicts to regular dicts for JSON serialization
            os_stats['by_os'] = dict(os_stats['by_os'])
            for os_name in os_stats['by_os']:
                os_stats['by_os'][os_name]['versions'] = dict(os_stats['by_os'][os_name]['versions'])
                os_stats['by_os'][os_name]['architectures'] = dict(os_stats['by_os'][os_name]['architectures'])
            os_stats['by_architecture'] = dict(os_stats['by_architecture'])
            
            return os_stats
            
        except Exception as e:
            logger.error(f"Failed to get OS statistics: {e}")
            return {}
    
    def get_traffic_statistics(self, days_back: int = 7) -> Dict[str, Any]:
        """Get traffic statistics by headend."""
        try:
            db = self.db
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            # Get headend traffic stats
            headend_stats = db(db.headend_analytics.last_heartbeat >= cutoff_date).select()
            
            traffic_data = {
                'total_bytes_proxied': 0,
                'total_packets_proxied': 0,
                'total_connections': 0,
                'active_headends': 0,
                'by_headend': {},
                'by_region': defaultdict(lambda: {'bytes': 0, 'packets': 0, 'connections': 0}),
                'timeline': []
            }
            
            for headend in headend_stats:
                if headend.last_heartbeat >= (datetime.utcnow() - timedelta(hours=1)):
                    traffic_data['active_headends'] += 1
                
                traffic_data['total_bytes_proxied'] += headend.bytes_proxied or 0
                traffic_data['total_packets_proxied'] += headend.packets_proxied or 0
                traffic_data['total_connections'] += headend.total_connections or 0
                
                # By headend
                traffic_data['by_headend'][headend.headend_id] = {
                    'hostname': headend.hostname,
                    'region': headend.region,
                    'active_connections': headend.active_connections,
                    'total_connections': headend.total_connections,
                    'bytes_proxied': headend.bytes_proxied,
                    'packets_proxied': headend.packets_proxied,
                    'cpu_usage': headend.cpu_usage_percent,
                    'memory_usage': headend.memory_usage_mb,
                    'last_heartbeat': headend.last_heartbeat.isoformat() if headend.last_heartbeat else None,
                    'auth_success_rate': (
                        (headend.auth_successes / (headend.auth_successes + headend.auth_failures + 1)) * 100
                        if (headend.auth_successes or headend.auth_failures) else 0
                    )
                }
                
                # By region
                if headend.region:
                    traffic_data['by_region'][headend.region]['bytes'] += headend.bytes_proxied or 0
                    traffic_data['by_region'][headend.region]['packets'] += headend.packets_proxied or 0
                    traffic_data['by_region'][headend.region]['connections'] += headend.total_connections or 0
            
            # Convert defaultdict to regular dict
            traffic_data['by_region'] = dict(traffic_data['by_region'])
            
            # Get timeline data from traffic_stats table
            timeline_query = db(
                (db.traffic_stats.stat_type == 'hourly') & 
                (db.traffic_stats.timestamp >= cutoff_date)
            ).select(orderby=db.traffic_stats.timestamp)
            
            for stat in timeline_query:
                traffic_data['timeline'].append({
                    'timestamp': stat.timestamp.isoformat(),
                    'headend_id': stat.headend_id,
                    'bytes': stat.total_bytes,
                    'packets': stat.total_packets,
                    'clients': stat.client_count,
                    'peak_connections': stat.peak_concurrent_connections
                })
            
            return traffic_data
            
        except Exception as e:
            logger.error(f"Failed to get traffic statistics: {e}")
            return {}
    
    def search_agents_and_headends(
        self, 
        search_term: str = "",
        filter_type: str = "all",  # 'all', 'agents', 'headends'
        sort_by: str = "last_seen",  # 'last_seen', 'hostname', 'os_name'
        limit: int = 100
    ) -> Dict[str, Any]:
        """Search and filter agents and headends."""
        try:
            db = self.db
            results = {
                'agents': [],
                'headends': [],
                'total_agents': 0,
                'total_headends': 0
            }
            
            # Search agents
            if filter_type in ['all', 'agents']:
                agent_query = db.client_analytics
                
                if search_term:
                    # Search in hostname, OS name, IP address, or client ID
                    agent_query = agent_query(
                        (db.client_analytics.hostname.contains(search_term)) |
                        (db.client_analytics.os_name.contains(search_term)) |
                        (db.client_analytics.ip_address.contains(search_term)) |
                        (db.client_analytics.client_id.contains(search_term)) |
                        (db.client_analytics.os_version.contains(search_term))
                    )
                
                # Sort
                if sort_by == 'hostname':
                    orderby = db.client_analytics.hostname
                elif sort_by == 'os_name':
                    orderby = db.client_analytics.os_name
                else:
                    orderby = ~db.client_analytics.last_seen  # Newest first
                
                agents = agent_query.select(limitby=(0, limit), orderby=orderby)
                results['total_agents'] = agent_query.count()
                
                for agent in agents:
                    # Calculate status
                    last_seen_minutes = (datetime.utcnow() - agent.last_seen).total_seconds() / 60
                    if last_seen_minutes <= 5:
                        status = 'online'
                    elif last_seen_minutes <= 60:
                        status = 'recently_active'
                    elif last_seen_minutes <= 1440:  # 24 hours
                        status = 'offline'
                    else:
                        status = 'stale'
                    
                    results['agents'].append({
                        'client_id': agent.client_id,
                        'hostname': agent.hostname,
                        'os_name': agent.os_name,
                        'os_version': agent.os_version,
                        'architecture': agent.architecture,
                        'client_version': agent.client_version,
                        'ip_address': agent.ip_address,
                        'connected_headend': agent.connected_headend,
                        'connection_duration': agent.connection_duration,
                        'bytes_sent': agent.bytes_sent,
                        'bytes_received': agent.bytes_received,
                        'last_seen': agent.last_seen.isoformat() if agent.last_seen else None,
                        'status': status,
                        'total_bytes': (agent.bytes_sent or 0) + (agent.bytes_received or 0)
                    })
            
            # Search headends
            if filter_type in ['all', 'headends']:
                headend_query = db.headend_analytics
                
                if search_term:
                    # Search in hostname, headend ID, region, or cluster
                    headend_query = headend_query(
                        (db.headend_analytics.hostname.contains(search_term)) |
                        (db.headend_analytics.headend_id.contains(search_term)) |
                        (db.headend_analytics.region.contains(search_term)) |
                        (db.headend_analytics.cluster_id.contains(search_term))
                    )
                
                # Sort
                if sort_by == 'hostname':
                    orderby = db.headend_analytics.hostname
                else:
                    orderby = ~db.headend_analytics.last_heartbeat  # Newest first
                
                headends = headend_query.select(limitby=(0, limit), orderby=orderby)
                results['total_headends'] = headend_query.count()
                
                for headend in headends:
                    # Calculate status
                    last_heartbeat_minutes = (datetime.utcnow() - headend.last_heartbeat).total_seconds() / 60
                    if last_heartbeat_minutes <= 2:
                        status = 'healthy'
                    elif last_heartbeat_minutes <= 10:
                        status = 'warning'
                    else:
                        status = 'critical'
                    
                    results['headends'].append({
                        'headend_id': headend.headend_id,
                        'hostname': headend.hostname,
                        'region': headend.region,
                        'cluster_id': headend.cluster_id,
                        'version': headend.version,
                        'active_connections': headend.active_connections,
                        'total_connections': headend.total_connections,
                        'bytes_proxied': headend.bytes_proxied,
                        'packets_proxied': headend.packets_proxied,
                        'cpu_usage_percent': headend.cpu_usage_percent,
                        'memory_usage_mb': headend.memory_usage_mb,
                        'disk_usage_percent': headend.disk_usage_percent,
                        'auth_success_rate': (
                            (headend.auth_successes / (headend.auth_successes + headend.auth_failures + 1)) * 100
                            if (headend.auth_successes or headend.auth_failures) else 0
                        ),
                        'last_heartbeat': headend.last_heartbeat.isoformat() if headend.last_heartbeat else None,
                        'status': status
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search agents and headends: {e}")
            return {'agents': [], 'headends': [], 'total_agents': 0, 'total_headends': 0}


# Global analytics manager instance
analytics_manager = AnalyticsManager()