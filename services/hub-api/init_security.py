#!/usr/bin/env python3
"""Initialize security tables and default configuration for SASEWaddle Manager."""

import os
import sys
import logging
from datetime import datetime

# Add the manager directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db

logger = logging.getLogger(__name__)


def init_security_tables():
    """Initialize security-related database tables."""
    db = get_db()
    
    logger.info("Initializing security tables...")
    
    # Security events table
    if 'security_events' not in db.tables:
        logger.info("Creating security_events table...")
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
        
        # Create indexes for performance
        try:
            db.executesql('CREATE INDEX idx_security_events_ip ON security_events(ip_address)')
            db.executesql('CREATE INDEX idx_security_events_timestamp ON security_events(timestamp)')
            db.executesql('CREATE INDEX idx_security_events_type ON security_events(event_type)')
            logger.info("Created indexes for security_events table")
        except Exception as e:
            logger.warning(f"Could not create indexes (may already exist): {e}")
    
    # Rate limit rules table
    if 'rate_limit_rules' not in db.tables:
        logger.info("Creating rate_limit_rules table...")
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
        
        # Insert some default rate limit rules
        logger.info("Inserting default rate limit rules...")
        default_rules = [
            {
                'name': 'api_strict_custom',
                'max_requests': 30,
                'window_seconds': 60,
                'block_duration': 600,
                'endpoints': '[\"/api/backup/\", \"/api/admin/\"]',
                'priority': 1,
                'enabled': True
            },
            {
                'name': 'web_moderate_custom',
                'max_requests': 100,
                'window_seconds': 60,
                'block_duration': 120,
                'endpoints': '[\"/admin\", \"/security\"]',
                'priority': 5,
                'enabled': True
            }
        ]
        
        for rule in default_rules:
            try:
                db.rate_limit_rules.insert(**rule)
                logger.info(f"Inserted default rule: {rule['name']}")
            except Exception as e:
                logger.warning(f"Could not insert rule {rule['name']}: {e}")
    
    # Commit all changes
    db.commit()
    logger.info("Security tables initialization completed")


def test_security_system():
    """Test that the security system is working properly."""
    logger.info("Testing security system...")
    
    try:
        from security import security_middleware
        
        # Test rate limiter
        test_ip = "127.0.0.1"
        test_endpoint = "/api/test"
        
        allowed, rule, retry_after = security_middleware.rate_limiter.is_allowed(
            test_ip, test_endpoint, "test-user-agent"
        )
        
        if allowed:
            logger.info("✓ Rate limiter is working - test request allowed")
        else:
            logger.warning(f"Rate limiter blocked test request: rule={rule}, retry_after={retry_after}")
        
        # Test DDoS protection
        is_attack, attack_type, severity = security_middleware.ddos_protection.detect_ddos_attack(
            test_ip, test_endpoint, "test-user-agent"
        )
        
        if not is_attack:
            logger.info("✓ DDoS protection is working - no attack detected for test")
        else:
            logger.warning(f"DDoS protection flagged test: type={attack_type}, severity={severity}")
        
        logger.info("Security system test completed successfully")
        
    except Exception as e:
        logger.error(f"Security system test failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Initialize security tables
        init_security_tables()
        
        # Test security system
        if test_security_system():
            logger.info("✓ Security initialization completed successfully")
            sys.exit(0)
        else:
            logger.error("✗ Security initialization completed with errors")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Security initialization failed: {e}")
        sys.exit(1)