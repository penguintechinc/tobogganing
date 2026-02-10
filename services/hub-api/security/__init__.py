"""Security middleware and rate limiting for SASEWaddle Manager."""

import os
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict, deque
from dataclasses import dataclass
import ipaddress

import redis
from database import get_db

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration."""
    name: str
    max_requests: int
    window_seconds: int
    block_duration: int = 300  # 5 minutes default
    endpoints: List[str] = None  # None means all endpoints
    exempt_ips: List[str] = None
    priority: int = 10  # Lower number = higher priority


@dataclass
class SecurityEvent:
    """Security event for logging and analysis."""
    event_type: str
    ip_address: str
    endpoint: str
    user_agent: str
    timestamp: datetime
    severity: str  # 'low', 'medium', 'high', 'critical'
    details: Dict[str, Any]


class RateLimiter:
    """Advanced rate limiter with Redis backend and multiple strategies."""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client or redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 1)),
            decode_responses=True
        )
        self.db = get_db()
        self.blocked_ips = set()
        self.blocked_until = {}
        
        # Default rate limiting rules
        self.rules = [
            # API endpoints - strict limits
            RateLimitRule(
                name="api_strict",
                max_requests=60,
                window_seconds=60,
                block_duration=300,
                endpoints=["/api/"],
                priority=1
            ),
            # Authentication endpoints - very strict
            RateLimitRule(
                name="auth_strict", 
                max_requests=5,
                window_seconds=60,
                block_duration=900,  # 15 minutes
                endpoints=["/api/auth/", "/login", "/api/v1/auth"],
                priority=1
            ),
            # Configuration pulls - moderate limits
            RateLimitRule(
                name="config_moderate",
                max_requests=10,
                window_seconds=300,  # 5 minutes
                block_duration=600,  # 10 minutes
                endpoints=["/api/v1/clients/", "/api/analytics/record/"],
                priority=2
            ),
            # Backup operations - strict limits
            RateLimitRule(
                name="backup_strict",
                max_requests=3,
                window_seconds=300,
                block_duration=1200,  # 20 minutes
                endpoints=["/api/backup/"],
                priority=1
            ),
            # Analytics - moderate limits
            RateLimitRule(
                name="analytics_moderate",
                max_requests=100,
                window_seconds=60,
                block_duration=300,
                endpoints=["/api/analytics/"],
                priority=3
            ),
            # General web interface - lenient
            RateLimitRule(
                name="web_lenient",
                max_requests=200,
                window_seconds=60,
                block_duration=60,
                priority=10
            )
        ]
        
        # Load custom rules from database
        self._load_custom_rules()
        
        # Sort rules by priority
        self.rules.sort(key=lambda r: r.priority)
    
    def _load_custom_rules(self):
        """Load custom rate limiting rules from database."""
        try:
            # Check if rate_limit_rules table exists
            if 'rate_limit_rules' in self.db.tables:
                rules = self.db(self.db.rate_limit_rules.enabled == True).select()
                for rule in rules:
                    custom_rule = RateLimitRule(
                        name=rule.name,
                        max_requests=rule.max_requests,
                        window_seconds=rule.window_seconds,
                        block_duration=rule.block_duration,
                        endpoints=json.loads(rule.endpoints) if rule.endpoints else None,
                        exempt_ips=json.loads(rule.exempt_ips) if rule.exempt_ips else None,
                        priority=rule.priority
                    )
                    self.rules.append(custom_rule)
                    logger.info(f"Loaded custom rate limit rule: {rule.name}")
        except Exception as e:
            logger.warning(f"Failed to load custom rate limit rules: {e}")
    
    def is_allowed(self, ip_address: str, endpoint: str, user_agent: str = "") -> Tuple[bool, Optional[RateLimitRule], int]:
        """
        Check if request is allowed based on rate limiting rules.
        
        Returns:
            (allowed, violated_rule, retry_after_seconds)
        """
        # Check if IP is currently blocked
        if self._is_ip_blocked(ip_address):
            return False, None, self.blocked_until.get(ip_address, 0)
        
        # Check against each rule
        for rule in self.rules:
            if self._rule_applies(rule, endpoint, ip_address):
                allowed, retry_after = self._check_rule(rule, ip_address, endpoint)
                if not allowed:
                    # Block the IP
                    self._block_ip(ip_address, rule.block_duration)
                    
                    # Log security event
                    self._log_security_event(
                        "rate_limit_violation",
                        ip_address,
                        endpoint,
                        user_agent,
                        "medium",
                        {"rule": rule.name, "max_requests": rule.max_requests, "window": rule.window_seconds}
                    )
                    
                    return False, rule, retry_after
        
        return True, None, 0
    
    def _is_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP address is currently blocked."""
        if ip_address in self.blocked_until:
            if time.time() < self.blocked_until[ip_address]:
                return True
            else:
                # Block has expired
                del self.blocked_until[ip_address]
                self.blocked_ips.discard(ip_address)
        return False
    
    def _block_ip(self, ip_address: str, duration: int):
        """Block IP address for specified duration."""
        until = time.time() + duration
        self.blocked_ips.add(ip_address)
        self.blocked_until[ip_address] = until
        
        # Store in Redis for persistence across restarts
        try:
            self.redis_client.setex(f"blocked_ip:{ip_address}", duration, int(until))
            logger.warning(f"Blocked IP {ip_address} for {duration} seconds due to rate limiting")
        except Exception as e:
            logger.error(f"Failed to store IP block in Redis: {e}")
    
    def _rule_applies(self, rule: RateLimitRule, endpoint: str, ip_address: str) -> bool:
        """Check if a rule applies to the current request."""
        # Check if IP is exempt
        if rule.exempt_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_address)
                for exempt in rule.exempt_ips:
                    if '/' in exempt:  # CIDR notation
                        if ip_obj in ipaddress.ip_network(exempt):
                            return False
                    else:  # Single IP
                        if ip_address == exempt:
                            return False
            except Exception as e:
                logger.warning(f"Invalid IP format in rule check: {e}")
        
        # Check if endpoint matches
        if rule.endpoints is None:
            return True  # Rule applies to all endpoints
        
        for pattern in rule.endpoints:
            if endpoint.startswith(pattern):
                return True
        
        return False
    
    def _check_rule(self, rule: RateLimitRule, ip_address: str, endpoint: str) -> Tuple[bool, int]:
        """Check if request violates the rate limit rule."""
        key = f"rl:{rule.name}:{ip_address}"
        
        try:
            # Use Redis sliding window counter
            now = int(time.time())
            window_start = now - rule.window_seconds
            
            # Clean old entries and count current requests
            pipeline = self.redis_client.pipeline()
            pipeline.zremrangebyscore(key, 0, window_start)
            pipeline.zcard(key)
            pipeline.expire(key, rule.window_seconds)
            results = pipeline.execute()
            
            current_count = results[1]
            
            if current_count >= rule.max_requests:
                # Get the oldest entry to calculate retry-after
                oldest_entry = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_entry:
                    oldest_time = int(oldest_entry[0][1])
                    retry_after = rule.window_seconds - (now - oldest_time)
                    return False, max(retry_after, 1)
                return False, rule.window_seconds
            
            # Add current request
            self.redis_client.zadd(key, {str(now): now})
            
            return True, 0
            
        except Exception as e:
            logger.error(f"Redis rate limiting error: {e}")
            # Fall back to in-memory rate limiting
            return self._fallback_rate_limit(rule, ip_address, endpoint)
    
    def _fallback_rate_limit(self, rule: RateLimitRule, ip_address: str, endpoint: str) -> Tuple[bool, int]:
        """Fallback in-memory rate limiting when Redis is unavailable."""
        key = f"{rule.name}:{ip_address}"
        now = time.time()
        
        if not hasattr(self, '_fallback_counters'):
            self._fallback_counters = defaultdict(deque)
        
        # Clean old entries
        counter = self._fallback_counters[key]
        while counter and counter[0] < now - rule.window_seconds:
            counter.popleft()
        
        if len(counter) >= rule.max_requests:
            # Calculate retry-after
            if counter:
                retry_after = rule.window_seconds - (now - counter[0])
                return False, max(int(retry_after), 1)
            return False, rule.window_seconds
        
        # Add current request
        counter.append(now)
        return True, 0
    
    def _log_security_event(self, event_type: str, ip_address: str, endpoint: str, 
                           user_agent: str, severity: str, details: Dict[str, Any]):
        """Log security event to database and monitoring systems."""
        event = SecurityEvent(
            event_type=event_type,
            ip_address=ip_address,
            endpoint=endpoint,
            user_agent=user_agent,
            timestamp=datetime.utcnow(),
            severity=severity,
            details=details
        )
        
        try:
            # Log to database if security_events table exists
            if 'security_events' in self.db.tables:
                self.db.security_events.insert(
                    event_type=event.event_type,
                    ip_address=event.ip_address,
                    endpoint=event.endpoint,
                    user_agent=event.user_agent,
                    timestamp=event.timestamp,
                    severity=event.severity,
                    details=json.dumps(event.details)
                )
                self.db.commit()
            
            # Log to application logs
            logger.warning(f"Security event: {event_type} from {ip_address} on {endpoint}")
            
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
    
    def get_blocked_ips(self) -> List[Dict[str, Any]]:
        """Get list of currently blocked IPs."""
        blocked = []
        current_time = time.time()
        
        for ip, until in self.blocked_until.items():
            if until > current_time:
                blocked.append({
                    'ip_address': ip,
                    'blocked_until': datetime.fromtimestamp(until),
                    'remaining_seconds': int(until - current_time)
                })
        
        return blocked
    
    def unblock_ip(self, ip_address: str) -> bool:
        """Manually unblock an IP address."""
        if ip_address in self.blocked_until:
            del self.blocked_until[ip_address]
            self.blocked_ips.discard(ip_address)
            
            # Remove from Redis
            try:
                self.redis_client.delete(f"blocked_ip:{ip_address}")
                logger.info(f"Manually unblocked IP: {ip_address}")
                return True
            except Exception as e:
                logger.error(f"Failed to remove IP block from Redis: {e}")
        
        return False


class DDoSProtection:
    """DDoS protection with advanced detection and mitigation."""
    
    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter
        self.redis_client = rate_limiter.redis_client
        self.db = rate_limiter.db
        
        # DDoS detection thresholds
        self.connection_threshold = int(os.getenv('DDOS_CONNECTION_THRESHOLD', '100'))
        self.request_threshold = int(os.getenv('DDOS_REQUEST_THRESHOLD', '1000'))
        self.time_window = int(os.getenv('DDOS_TIME_WINDOW', '60'))  # seconds
        
        # Pattern detection
        self.suspicious_patterns = [
            r'\.php$',  # PHP file requests (not used in our app)
            r'wp-admin',  # WordPress admin attempts
            r'\.asp$',  # ASP file requests
            r'sql',  # SQL injection attempts
            r'<script',  # XSS attempts
            r'union.*select',  # SQL injection
            r'etc/passwd',  # Directory traversal
        ]
        
        # Geolocation-based rules (countries to block/monitor)
        self.blocked_countries = os.getenv('DDOS_BLOCKED_COUNTRIES', '').split(',')
        self.monitored_countries = os.getenv('DDOS_MONITORED_COUNTRIES', '').split(',')
    
    def detect_ddos_attack(self, ip_address: str, endpoint: str, user_agent: str) -> Tuple[bool, str, str]:
        """
        Detect potential DDoS attack patterns.
        
        Returns:
            (is_attack, attack_type, severity)
        """
        attack_indicators = []
        
        # Volume-based detection
        if self._check_volume_attack(ip_address):
            attack_indicators.append(("volume", "high"))
        
        # Pattern-based detection
        if self._check_suspicious_patterns(endpoint, user_agent):
            attack_indicators.append(("pattern", "medium"))
        
        # Behavioral analysis
        if self._check_behavioral_anomaly(ip_address, endpoint):
            attack_indicators.append(("behavioral", "medium"))
        
        # Distributed attack detection
        if self._check_distributed_attack():
            attack_indicators.append(("distributed", "critical"))
        
        if attack_indicators:
            # Determine overall severity
            severities = [indicator[1] for indicator in attack_indicators]
            if "critical" in severities:
                severity = "critical"
            elif "high" in severities:
                severity = "high"
            else:
                severity = "medium"
            
            attack_types = [indicator[0] for indicator in attack_indicators]
            return True, ",".join(attack_types), severity
        
        return False, "", ""
    
    def _check_volume_attack(self, ip_address: str) -> bool:
        """Check for volume-based attacks from a single IP."""
        try:
            key = f"ddos_volume:{ip_address}"
            now = int(time.time())
            window_start = now - self.time_window
            
            # Count requests in the time window
            self.redis_client.zremrangebyscore(key, 0, window_start)
            count = self.redis_client.zcard(key)
            
            # Add current request
            self.redis_client.zadd(key, {str(now): now})
            self.redis_client.expire(key, self.time_window)
            
            return count > self.request_threshold
            
        except Exception as e:
            logger.error(f"Volume attack detection error: {e}")
            return False
    
    def _check_suspicious_patterns(self, endpoint: str, user_agent: str) -> bool:
        """Check for suspicious request patterns."""
        import re
        
        # Check endpoint against suspicious patterns
        for pattern in self.suspicious_patterns:
            if re.search(pattern, endpoint, re.IGNORECASE):
                return True
        
        # Check user agent patterns
        suspicious_ua_patterns = [
            r'bot',
            r'crawler',
            r'spider',
            r'scanner',
            r'sqlmap',
            r'nikto',
            r'masscan'
        ]
        
        for pattern in suspicious_ua_patterns:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return True
        
        return False
    
    def _check_behavioral_anomaly(self, ip_address: str, endpoint: str) -> bool:
        """Check for behavioral anomalies."""
        try:
            key = f"ddos_behavior:{ip_address}"
            
            # Track unique endpoints accessed
            self.redis_client.sadd(key, endpoint)
            self.redis_client.expire(key, 300)  # 5 minutes
            
            # Check if accessing too many different endpoints
            unique_endpoints = self.redis_client.scard(key)
            if unique_endpoints > 20:  # More than 20 unique endpoints in 5 minutes
                return True
            
            # Check request timing patterns
            timing_key = f"ddos_timing:{ip_address}"
            now = time.time()
            
            # Get last few request times
            last_requests = self.redis_client.lrange(timing_key, 0, 9)
            
            # Add current request
            self.redis_client.lpush(timing_key, now)
            self.redis_client.ltrim(timing_key, 0, 9)  # Keep only last 10
            self.redis_client.expire(timing_key, 60)
            
            # Check for suspiciously regular timing (bot behavior)
            if len(last_requests) >= 5:
                intervals = []
                prev_time = now
                for req_time in last_requests:
                    interval = prev_time - float(req_time)
                    intervals.append(interval)
                    prev_time = float(req_time)
                
                # Calculate variance in intervals
                if len(intervals) > 1:
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
                    
                    # Low variance indicates bot-like behavior
                    if variance < 0.1 and avg_interval < 2:  # Very regular, fast requests
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Behavioral anomaly detection error: {e}")
            return False
    
    def _check_distributed_attack(self) -> bool:
        """Check for distributed DDoS attacks."""
        try:
            key = "ddos_distributed"
            now = int(time.time())
            window_start = now - 60  # 1 minute window
            
            # Count unique IPs making requests
            unique_ips_key = f"{key}:ips"
            
            # This would be called for each request, adding the IP
            # For now, just check if we have too many unique IPs in recent requests
            self.redis_client.zremrangebyscore(unique_ips_key, 0, window_start)
            unique_ip_count = self.redis_client.zcard(unique_ips_key)
            
            # If more than 50 unique IPs in 1 minute, consider it distributed
            return unique_ip_count > 50
            
        except Exception as e:
            logger.error(f"Distributed attack detection error: {e}")
            return False
    
    def mitigate_attack(self, ip_address: str, attack_type: str, severity: str):
        """Implement DDoS mitigation measures."""
        # Block duration based on severity
        duration_map = {
            "low": 300,      # 5 minutes
            "medium": 900,   # 15 minutes
            "high": 3600,    # 1 hour
            "critical": 7200 # 2 hours
        }
        
        block_duration = duration_map.get(severity, 300)
        
        # Block the IP
        self.rate_limiter._block_ip(ip_address, block_duration)
        
        # Log the attack
        self.rate_limiter._log_security_event(
            "ddos_attack",
            ip_address,
            "/",  # Generic endpoint for DDoS
            "",
            severity,
            {
                "attack_type": attack_type,
                "mitigation": "ip_block",
                "block_duration": block_duration
            }
        )
        
        # Additional mitigations based on severity
        if severity in ["high", "critical"]:
            self._enable_emergency_mode()
        
        # Notify administrators
        self._notify_attack(ip_address, attack_type, severity)
    
    def _enable_emergency_mode(self):
        """Enable emergency mode with stricter rate limits."""
        try:
            self.redis_client.setex("emergency_mode", 3600, "1")  # 1 hour
            logger.critical("DDoS emergency mode enabled - stricter rate limits active")
        except Exception as e:
            logger.error(f"Failed to enable emergency mode: {e}")
    
    def _notify_attack(self, ip_address: str, attack_type: str, severity: str):
        """Send notifications about DDoS attacks."""
        # This would integrate with notification systems (email, Slack, etc.)
        logger.critical(f"DDoS attack detected from {ip_address}: type={attack_type}, severity={severity}")


class SecurityMiddleware:
    """Main security middleware integrating all protection mechanisms."""
    
    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.ddos_protection = DDoSProtection(self.rate_limiter)
        
        # Initialize database tables
        self._ensure_security_tables()
    
    def _ensure_security_tables(self):
        """Create security-related database tables."""
        db = self.rate_limiter.db
        
        # Security events table
        if 'security_events' not in db.tables:
            db.define_table('security_events',
                db.Field('event_type', 'string', length=64, required=True),
                db.Field('ip_address', 'string', length=45, required=True),
                db.Field('endpoint', 'string', length=255),
                db.Field('user_agent', 'text'),
                db.Field('timestamp', 'datetime', required=True),
                db.Field('severity', 'string', length=16),
                db.Field('details', 'json'),
                db.Field('created_at', 'datetime', default=datetime.utcnow)
            )
            
            # Create indexes
            db.executesql('CREATE INDEX idx_security_events_ip ON security_events(ip_address)')
            db.executesql('CREATE INDEX idx_security_events_timestamp ON security_events(timestamp)')
            db.executesql('CREATE INDEX idx_security_events_type ON security_events(event_type)')
        
        # Rate limit rules table
        if 'rate_limit_rules' not in db.tables:
            db.define_table('rate_limit_rules',
                db.Field('name', 'string', length=64, required=True, unique=True),
                db.Field('max_requests', 'integer', required=True),
                db.Field('window_seconds', 'integer', required=True),
                db.Field('block_duration', 'integer', default=300),
                db.Field('endpoints', 'json'),  # JSON array of endpoint patterns
                db.Field('exempt_ips', 'json'),  # JSON array of exempt IPs/CIDRs
                db.Field('priority', 'integer', default=10),
                db.Field('enabled', 'boolean', default=True),
                db.Field('created_at', 'datetime', default=datetime.utcnow),
                db.Field('updated_at', 'datetime', default=datetime.utcnow, update=datetime.utcnow)
            )
        
        db.commit()
        logger.info("Security tables ensured")
    
    def process_request(self, request_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Process incoming request through security layers.
        
        Args:
            request_info: Dict containing ip_address, endpoint, user_agent, etc.
            
        Returns:
            (allowed, response_headers)
        """
        ip_address = request_info.get('ip_address', '')
        endpoint = request_info.get('endpoint', '')
        user_agent = request_info.get('user_agent', '')
        
        # Check rate limits
        allowed, violated_rule, retry_after = self.rate_limiter.is_allowed(ip_address, endpoint, user_agent)
        
        if not allowed:
            headers = {
                'X-RateLimit-Limit': str(violated_rule.max_requests) if violated_rule else '0',
                'X-RateLimit-Remaining': '0',
                'X-RateLimit-Reset': str(int(time.time()) + retry_after),
                'Retry-After': str(retry_after)
            }
            return False, headers
        
        # Check for DDoS patterns
        is_attack, attack_type, severity = self.ddos_protection.detect_ddos_attack(ip_address, endpoint, user_agent)
        
        if is_attack:
            self.ddos_protection.mitigate_attack(ip_address, attack_type, severity)
            headers = {
                'X-Security-Block': 'DDoS-Protection',
                'X-Block-Reason': attack_type
            }
            return False, headers
        
        # Request allowed
        headers = {
            'X-RateLimit-Remaining': str(violated_rule.max_requests - 1) if violated_rule else '999'
        }
        return True, headers


# Global security middleware instance
security_middleware = SecurityMiddleware()