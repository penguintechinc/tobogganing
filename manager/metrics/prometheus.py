"""
Prometheus Metrics for SASEWaddle Manager Service
Provides comprehensive metrics for monitoring and alerting
"""

import time
import threading
from typing import Dict, Any
from datetime import datetime
from collections import defaultdict

import structlog
from prometheus_client import (
    Counter, Histogram, Gauge, Info, Enum,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)

logger = structlog.get_logger()

class ManagerMetrics:
    """Prometheus metrics collector for Manager service"""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        self._init_metrics()
        self._start_time = time.time()
        
        # Thread-safe counters for internal tracking
        self._lock = threading.Lock()
        self._api_calls = defaultdict(int)
        self._errors_by_endpoint = defaultdict(int)
        
    def _init_metrics(self):
        """Initialize all Prometheus metrics"""
        
        # Service Info
        self.service_info = Info(
            'sasewaddle_manager_info',
            'SASEWaddle Manager service information',
            registry=self.registry
        )
        
        # Service Status
        self.service_status = Enum(
            'sasewaddle_manager_status',
            'Current status of the manager service',
            states=['starting', 'healthy', 'degraded', 'unhealthy'],
            registry=self.registry
        )
        
        # Uptime
        self.uptime_seconds = Gauge(
            'sasewaddle_manager_uptime_seconds',
            'Time since manager service started',
            registry=self.registry
        )
        
        # HTTP Request Metrics
        self.http_requests_total = Counter(
            'sasewaddle_manager_http_requests_total',
            'Total HTTP requests processed',
            ['method', 'endpoint', 'status'],
            registry=self.registry
        )
        
        self.http_request_duration = Histogram(
            'sasewaddle_manager_http_request_duration_seconds',
            'Time spent processing HTTP requests',
            ['method', 'endpoint'],
            registry=self.registry
        )
        
        # API Authentication Metrics
        self.auth_attempts_total = Counter(
            'sasewaddle_manager_auth_attempts_total',
            'Total authentication attempts',
            ['type', 'result'],  # type: api_key, jwt, session; result: success, failure
            registry=self.registry
        )
        
        self.active_sessions = Gauge(
            'sasewaddle_manager_active_sessions',
            'Number of active user sessions',
            registry=self.registry
        )
        
        # Cluster Metrics
        self.clusters_total = Gauge(
            'sasewaddle_manager_clusters_total',
            'Total number of registered clusters',
            registry=self.registry
        )
        
        self.clusters_by_status = Gauge(
            'sasewaddle_manager_clusters_by_status',
            'Number of clusters by status',
            ['status'],  # active, inactive, unhealthy
            registry=self.registry
        )
        
        self.cluster_heartbeats_total = Counter(
            'sasewaddle_manager_cluster_heartbeats_total',
            'Total cluster heartbeat messages received',
            ['cluster_id', 'status'],
            registry=self.registry
        )
        
        # Client Metrics
        self.clients_total = Gauge(
            'sasewaddle_manager_clients_total',
            'Total number of registered clients',
            registry=self.registry
        )
        
        self.clients_by_type = Gauge(
            'sasewaddle_manager_clients_by_type',
            'Number of clients by type',
            ['type'],  # docker, native
            registry=self.registry
        )
        
        self.clients_by_status = Gauge(
            'sasewaddle_manager_clients_by_status',
            'Number of clients by status',
            ['status'],  # active, inactive, pending
            registry=self.registry
        )
        
        self.client_registrations_total = Counter(
            'sasewaddle_manager_client_registrations_total',
            'Total client registration attempts',
            ['type', 'result'],  # result: success, failure
            registry=self.registry
        )
        
        # Certificate Metrics
        self.certificates_issued_total = Counter(
            'sasewaddle_manager_certificates_issued_total',
            'Total certificates issued',
            ['type'],  # client, headend, ca
            registry=self.registry
        )
        
        self.certificates_active = Gauge(
            'sasewaddle_manager_certificates_active',
            'Number of active certificates',
            ['type'],
            registry=self.registry
        )
        
        self.certificates_expiring_soon = Gauge(
            'sasewaddle_manager_certificates_expiring_soon',
            'Number of certificates expiring within 30 days',
            ['type'],
            registry=self.registry
        )
        
        # JWT Token Metrics
        self.jwt_tokens_issued_total = Counter(
            'sasewaddle_manager_jwt_tokens_issued_total',
            'Total JWT tokens issued',
            ['node_type'],  # client, headend
            registry=self.registry
        )
        
        self.jwt_tokens_validated_total = Counter(
            'sasewaddle_manager_jwt_tokens_validated_total',
            'Total JWT token validation attempts',
            ['result'],  # success, failure, expired
            registry=self.registry
        )
        
        self.jwt_tokens_revoked_total = Counter(
            'sasewaddle_manager_jwt_tokens_revoked_total',
            'Total JWT tokens revoked',
            ['reason'],  # admin, client_request, expired, security
            registry=self.registry
        )
        
        # Database Metrics
        self.database_connections = Gauge(
            'sasewaddle_manager_database_connections',
            'Number of active database connections',
            registry=self.registry
        )
        
        self.database_queries_total = Counter(
            'sasewaddle_manager_database_queries_total',
            'Total database queries executed',
            ['operation'],  # select, insert, update, delete
            registry=self.registry
        )
        
        self.database_query_duration = Histogram(
            'sasewaddle_manager_database_query_duration_seconds',
            'Time spent executing database queries',
            ['operation'],
            registry=self.registry
        )
        
        # Redis Metrics
        self.redis_connections = Gauge(
            'sasewaddle_manager_redis_connections',
            'Number of active Redis connections',
            registry=self.registry
        )
        
        self.redis_operations_total = Counter(
            'sasewaddle_manager_redis_operations_total',
            'Total Redis operations',
            ['operation'],  # get, set, del, expire
            registry=self.registry
        )
        
        # System Resource Metrics
        self.memory_usage_bytes = Gauge(
            'sasewaddle_manager_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )
        
        self.cpu_usage_percent = Gauge(
            'sasewaddle_manager_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )
        
        # Business Logic Metrics
        self.user_logins_total = Counter(
            'sasewaddle_manager_user_logins_total',
            'Total user login attempts',
            ['role', 'result'],  # role: admin, reporter; result: success, failure
            registry=self.registry
        )
        
        self.api_rate_limit_hits = Counter(
            'sasewaddle_manager_api_rate_limit_hits_total',
            'Total API rate limit hits',
            ['endpoint', 'client_type'],
            registry=self.registry
        )
        
        # Error Metrics
        self.errors_total = Counter(
            'sasewaddle_manager_errors_total',
            'Total errors by component',
            ['component', 'error_type'],
            registry=self.registry
        )
        
        # Initialize service info
        with open('.version', 'r') as f:
            version = f.read().strip()
        
        self.service_info.info({
            'version': version,
            'service': 'sasewaddle-manager',
            'started_at': datetime.now().isoformat()
        })
        
        self.service_status.state('healthy')
        
    def record_http_request(self, method: str, endpoint: str, status: int, duration: float):
        """Record HTTP request metrics"""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=str(status)
        ).inc()
        
        self.http_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_auth_attempt(self, auth_type: str, success: bool):
        """Record authentication attempt"""
        result = 'success' if success else 'failure'
        self.auth_attempts_total.labels(
            type=auth_type,
            result=result
        ).inc()
    
    def record_user_login(self, role: str, success: bool):
        """Record user login attempt"""
        result = 'success' if success else 'failure'
        self.user_logins_total.labels(
            role=role,
            result=result
        ).inc()
    
    def record_client_registration(self, client_type: str, success: bool):
        """Record client registration"""
        result = 'success' if success else 'failure'
        self.client_registrations_total.labels(
            type=client_type,
            result=result
        ).inc()
    
    def record_certificate_issued(self, cert_type: str):
        """Record certificate issuance"""
        self.certificates_issued_total.labels(type=cert_type).inc()
    
    def record_jwt_token_issued(self, node_type: str):
        """Record JWT token issuance"""
        self.jwt_tokens_issued_total.labels(node_type=node_type).inc()
    
    def record_jwt_validation(self, result: str):
        """Record JWT token validation"""
        self.jwt_tokens_validated_total.labels(result=result).inc()
    
    def record_jwt_revocation(self, reason: str):
        """Record JWT token revocation"""
        self.jwt_tokens_revoked_total.labels(reason=reason).inc()
    
    def record_cluster_heartbeat(self, cluster_id: str, status: str):
        """Record cluster heartbeat"""
        self.cluster_heartbeats_total.labels(
            cluster_id=cluster_id,
            status=status
        ).inc()
    
    def record_database_query(self, operation: str, duration: float):
        """Record database query"""
        self.database_queries_total.labels(operation=operation).inc()
        self.database_query_duration.labels(operation=operation).observe(duration)
    
    def record_redis_operation(self, operation: str):
        """Record Redis operation"""
        self.redis_operations_total.labels(operation=operation).inc()
    
    def record_error(self, component: str, error_type: str):
        """Record error occurrence"""
        self.errors_total.labels(
            component=component,
            error_type=error_type
        ).inc()
    
    def update_cluster_stats(self, total: int, by_status: Dict[str, int]):
        """Update cluster statistics"""
        self.clusters_total.set(total)
        for status, count in by_status.items():
            self.clusters_by_status.labels(status=status).set(count)
    
    def update_client_stats(self, total: int, by_type: Dict[str, int], by_status: Dict[str, int]):
        """Update client statistics"""
        self.clients_total.set(total)
        for client_type, count in by_type.items():
            self.clients_by_type.labels(type=client_type).set(count)
        for status, count in by_status.items():
            self.clients_by_status.labels(status=status).set(count)
    
    def update_certificate_stats(self, active: Dict[str, int], expiring: Dict[str, int]):
        """Update certificate statistics"""
        for cert_type, count in active.items():
            self.certificates_active.labels(type=cert_type).set(count)
        for cert_type, count in expiring.items():
            self.certificates_expiring_soon.labels(type=cert_type).set(count)
    
    def update_system_resources(self, memory_bytes: int, cpu_percent: float):
        """Update system resource metrics"""
        self.memory_usage_bytes.set(memory_bytes)
        self.cpu_usage_percent.set(cpu_percent)
    
    def update_active_sessions(self, count: int):
        """Update active session count"""
        self.active_sessions.set(count)
    
    def update_connection_pools(self, db_connections: int, redis_connections: int):
        """Update connection pool metrics"""
        self.database_connections.set(db_connections)
        self.redis_connections.set(redis_connections)
    
    def update_uptime(self):
        """Update service uptime"""
        uptime = time.time() - self._start_time
        self.uptime_seconds.set(uptime)
    
    def set_service_status(self, status: str):
        """Set service status"""
        self.service_status.state(status)
    
    def get_metrics(self) -> bytes:
        """Get Prometheus metrics in text format"""
        self.update_uptime()
        return generate_latest(self.registry)
    
    def get_content_type(self) -> str:
        """Get content type for metrics endpoint"""
        return CONTENT_TYPE_LATEST

# Global metrics instance
manager_metrics = ManagerMetrics()

def get_metrics_instance() -> ManagerMetrics:
    """Get the global metrics instance"""
    return manager_metrics