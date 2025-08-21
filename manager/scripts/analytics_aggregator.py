#!/usr/bin/env python3
"""
Analytics data aggregation script for SASEWaddle Manager.
This script should be run periodically (e.g., via cron) to aggregate analytics data.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List

# Add the parent directory to the path so we can import from manager modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db
from analytics import analytics_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnalyticsAggregator:
    """Aggregates analytics data into time-based summaries."""
    
    def __init__(self):
        self.db = get_db()
        self.retention_days = int(os.getenv('ANALYTICS_RETENTION_DAYS', '90'))
    
    def aggregate_hourly_stats(self, target_hour: datetime = None):
        """Aggregate analytics data for a specific hour."""
        if not target_hour:
            # Default to the previous hour
            target_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        
        hour_start = target_hour
        hour_end = target_hour + timedelta(hours=1)
        
        logger.info(f"Aggregating hourly stats for {hour_start} to {hour_end}")
        
        try:
            # Get all active clients during this hour
            client_query = self.db(
                (self.db.client_analytics.last_seen >= hour_start) &
                (self.db.client_analytics.last_seen < hour_end)
            )
            
            # Get all headends that were active during this hour
            headend_query = self.db(
                (self.db.headend_analytics.last_heartbeat >= hour_start) &
                (self.db.headend_analytics.last_heartbeat < hour_end)
            )
            
            # Aggregate by headend
            headend_stats = {}
            
            # Process headend data
            for headend in headend_query.select():
                headend_id = headend.headend_id
                if headend_id not in headend_stats:
                    headend_stats[headend_id] = {
                        'client_count': 0,
                        'total_bytes': 0,
                        'total_packets': 0,
                        'unique_users': set(),
                        'peak_connections': headend.active_connections or 0,
                        'total_connection_duration': 0
                    }
                
                # Update peak connections
                if (headend.active_connections or 0) > headend_stats[headend_id]['peak_connections']:
                    headend_stats[headend_id]['peak_connections'] = headend.active_connections or 0
            
            # Process client data
            for client in client_query.select():
                headend_id = client.connected_headend
                if not headend_id:
                    continue
                
                if headend_id not in headend_stats:
                    headend_stats[headend_id] = {
                        'client_count': 0,
                        'total_bytes': 0,
                        'total_packets': 0,
                        'unique_users': set(),
                        'peak_connections': 0,
                        'total_connection_duration': 0
                    }
                
                stats = headend_stats[headend_id]
                stats['client_count'] += 1
                stats['total_bytes'] += (client.bytes_sent or 0) + (client.bytes_received or 0)
                stats['total_packets'] += (client.packets_sent or 0) + (client.packets_received or 0)
                stats['unique_users'].add(client.client_id)
                stats['total_connection_duration'] += client.connection_duration or 0
            
            # Save aggregated data
            for headend_id, stats in headend_stats.items():
                # Check if record already exists
                existing = self.db(
                    (self.db.traffic_stats.stat_type == 'hourly') &
                    (self.db.traffic_stats.timestamp == hour_start) &
                    (self.db.traffic_stats.headend_id == headend_id)
                ).select().first()
                
                avg_duration = (
                    stats['total_connection_duration'] // max(stats['client_count'], 1)
                    if stats['client_count'] > 0 else 0
                )
                
                if existing:
                    # Update existing record
                    self.db(self.db.traffic_stats.id == existing.id).update(
                        client_count=stats['client_count'],
                        total_bytes=stats['total_bytes'],
                        total_packets=stats['total_packets'],
                        unique_users=len(stats['unique_users']),
                        avg_connection_duration=avg_duration,
                        peak_concurrent_connections=stats['peak_connections']
                    )
                else:
                    # Insert new record
                    self.db.traffic_stats.insert(
                        stat_type='hourly',
                        timestamp=hour_start,
                        headend_id=headend_id,
                        client_count=stats['client_count'],
                        total_bytes=stats['total_bytes'],
                        total_packets=stats['total_packets'],
                        unique_users=len(stats['unique_users']),
                        avg_connection_duration=avg_duration,
                        peak_concurrent_connections=stats['peak_connections']
                    )
            
            self.db.commit()
            logger.info(f"Successfully aggregated hourly stats for {len(headend_stats)} headends")
            return True
            
        except Exception as e:
            logger.error(f"Failed to aggregate hourly stats: {e}")
            self.db.rollback()
            return False
    
    def aggregate_daily_stats(self, target_date: datetime = None):
        """Aggregate hourly stats into daily summaries."""
        if not target_date:
            # Default to yesterday
            target_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        
        day_start = target_date
        day_end = target_date + timedelta(days=1)
        
        logger.info(f"Aggregating daily stats for {day_start.date()}")
        
        try:
            # Get all hourly stats for this day
            hourly_query = self.db(
                (self.db.traffic_stats.stat_type == 'hourly') &
                (self.db.traffic_stats.timestamp >= day_start) &
                (self.db.traffic_stats.timestamp < day_end)
            )
            
            # Aggregate by headend
            daily_stats = {}
            
            for hourly in hourly_query.select():
                headend_id = hourly.headend_id
                if headend_id not in daily_stats:
                    daily_stats[headend_id] = {
                        'client_count': 0,
                        'total_bytes': 0,
                        'total_packets': 0,
                        'unique_users': 0,
                        'avg_connection_duration': 0,
                        'peak_connections': 0,
                        'hour_count': 0,
                        'duration_sum': 0
                    }
                
                stats = daily_stats[headend_id]
                stats['client_count'] += hourly.client_count or 0
                stats['total_bytes'] += hourly.total_bytes or 0
                stats['total_packets'] += hourly.total_packets or 0
                stats['unique_users'] = max(stats['unique_users'], hourly.unique_users or 0)
                stats['peak_connections'] = max(stats['peak_connections'], hourly.peak_concurrent_connections or 0)
                stats['duration_sum'] += (hourly.avg_connection_duration or 0) * (hourly.client_count or 1)
                stats['hour_count'] += 1
            
            # Save daily aggregates
            for headend_id, stats in daily_stats.items():
                # Calculate average connection duration across the day
                avg_duration = (
                    stats['duration_sum'] // max(stats['client_count'], 1)
                    if stats['client_count'] > 0 else 0
                )
                
                # Check if record already exists
                existing = self.db(
                    (self.db.traffic_stats.stat_type == 'daily') &
                    (self.db.traffic_stats.timestamp == day_start) &
                    (self.db.traffic_stats.headend_id == headend_id)
                ).select().first()
                
                if existing:
                    # Update existing record
                    self.db(self.db.traffic_stats.id == existing.id).update(
                        client_count=stats['client_count'],
                        total_bytes=stats['total_bytes'],
                        total_packets=stats['total_packets'],
                        unique_users=stats['unique_users'],
                        avg_connection_duration=avg_duration,
                        peak_concurrent_connections=stats['peak_connections']
                    )
                else:
                    # Insert new record
                    self.db.traffic_stats.insert(
                        stat_type='daily',
                        timestamp=day_start,
                        headend_id=headend_id,
                        client_count=stats['client_count'],
                        total_bytes=stats['total_bytes'],
                        total_packets=stats['total_packets'],
                        unique_users=stats['unique_users'],
                        avg_connection_duration=avg_duration,
                        peak_concurrent_connections=stats['peak_connections']
                    )
            
            self.db.commit()
            logger.info(f"Successfully aggregated daily stats for {len(daily_stats)} headends")
            return True
            
        except Exception as e:
            logger.error(f"Failed to aggregate daily stats: {e}")
            self.db.rollback()
            return False
    
    def cleanup_old_data(self):
        """Clean up old analytics data beyond retention period."""
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        
        logger.info(f"Cleaning up analytics data older than {cutoff_date}")
        
        try:
            # Clean up old client analytics
            client_deleted = self.db(self.db.client_analytics.created_at < cutoff_date).delete()
            
            # Clean up old headend analytics (keep recent heartbeats)
            headend_deleted = self.db(self.db.headend_analytics.created_at < cutoff_date).delete()
            
            # Clean up old hourly traffic stats (keep daily/monthly)
            hourly_cutoff = datetime.utcnow() - timedelta(days=30)  # Keep 30 days of hourly data
            hourly_deleted = self.db(
                (self.db.traffic_stats.stat_type == 'hourly') &
                (self.db.traffic_stats.timestamp < hourly_cutoff)
            ).delete()
            
            self.db.commit()
            
            logger.info(f"Cleaned up {client_deleted} client records, {headend_deleted} headend records, "
                       f"and {hourly_deleted} hourly stats")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            self.db.rollback()
            return False
    
    def generate_system_summary(self):
        """Generate a system-wide analytics summary."""
        try:
            # Get counts
            total_clients = self.db(self.db.client_analytics).count()
            total_headends = self.db(self.db.headend_analytics).count()
            
            # Get active counts (last 24 hours)
            last_24h = datetime.utcnow() - timedelta(hours=24)
            active_clients = self.db(self.db.client_analytics.last_seen >= last_24h).count()
            active_headends = self.db(self.db.headend_analytics.last_heartbeat >= last_24h).count()
            
            # Get traffic totals
            traffic_query = """
                SELECT SUM(bytes_proxied) as total_bytes, SUM(packets_proxied) as total_packets
                FROM headend_analytics
            """
            traffic_result = self.db.executesql(traffic_query)
            total_bytes = traffic_result[0][0] if traffic_result and traffic_result[0][0] else 0
            total_packets = traffic_result[0][1] if traffic_result and traffic_result[0][1] else 0
            
            summary = {
                'timestamp': datetime.utcnow().isoformat(),
                'total_clients': total_clients,
                'total_headends': total_headends,
                'active_clients_24h': active_clients,
                'active_headends_24h': active_headends,
                'total_bytes_proxied': total_bytes,
                'total_packets_proxied': total_packets
            }
            
            logger.info(f"System summary: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate system summary: {e}")
            return {}


def main():
    """Main aggregation routine."""
    logger.info("Starting analytics aggregation")
    
    aggregator = AnalyticsAggregator()
    
    # Run aggregations
    success_count = 0
    
    # Aggregate hourly stats for the last few hours (catch up)
    current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    for i in range(1, 4):  # Last 3 hours
        hour = current_hour - timedelta(hours=i)
        if aggregator.aggregate_hourly_stats(hour):
            success_count += 1
    
    # Aggregate daily stats for yesterday
    yesterday = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    if aggregator.aggregate_daily_stats(yesterday):
        success_count += 1
    
    # Clean up old data
    if aggregator.cleanup_old_data():
        success_count += 1
    
    # Generate system summary
    summary = aggregator.generate_system_summary()
    if summary:
        success_count += 1
    
    logger.info(f"Analytics aggregation completed: {success_count} operations successful")
    
    return success_count > 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)