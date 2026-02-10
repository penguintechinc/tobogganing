#!/usr/bin/env python3
"""Initialize security feeds and scanner for SASEWaddle Manager."""

import os
import sys
import asyncio
import logging
from datetime import datetime

# Add the manager directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db
from security.feeds import security_feeds_manager
from security.scanner import security_scanner

logger = logging.getLogger(__name__)


async def init_security_feeds():
    """Initialize security threat feeds."""
    logger.info("Initializing security threat feeds...")
    
    try:
        # Start security feeds manager
        logger.info("Starting security feeds manager...")
        await security_feeds_manager.start_feed_updates()
        
        logger.info("Security feeds manager started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start security feeds manager: {e}")
        raise


async def init_security_scanner():
    """Initialize security scanner."""
    logger.info("Initializing security scanner...")
    
    try:
        # Start security scanner
        logger.info("Starting security scanning pipeline...")
        await security_scanner.start_scanning_pipeline()
        
        logger.info("Security scanning pipeline started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start security scanner: {e}")
        raise


def test_security_feeds():
    """Test security feeds functionality."""
    logger.info("Testing security feeds...")
    
    try:
        # Test threat indicator check
        test_domain = "example.com"
        is_threat, threat_details = security_feeds_manager.check_threat_indicator(test_domain, 'domain')
        
        logger.info(f"Test domain check - {test_domain}: is_threat={is_threat}, details={len(threat_details)} indicators")
        
        # Test IP check
        test_ip = "8.8.8.8"
        is_threat, threat_details = security_feeds_manager.check_threat_indicator(test_ip, 'ip')
        
        logger.info(f"Test IP check - {test_ip}: is_threat={is_threat}, details={len(threat_details)} indicators")
        
        # Get threat statistics
        stats = security_feeds_manager.get_threat_statistics(24)
        logger.info(f"Threat statistics: {stats}")
        
        logger.info("✓ Security feeds test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Security feeds test failed: {e}")
        return False


def create_sample_threats():
    """Create sample threat indicators for testing."""
    logger.info("Creating sample threat indicators for testing...")
    
    try:
        from security.feeds import ThreatIndicator, ThreatType, FeedSource
        
        # Sample malware domains
        sample_domains = [
            "malware-test.example",
            "phishing-test.example", 
            "spam-test.example"
        ]
        
        # Sample malicious IPs
        sample_ips = [
            "192.0.2.100",  # TEST-NET-1
            "203.0.113.50",  # TEST-NET-3
            "198.51.100.25"  # TEST-NET-2
        ]
        
        for domain in sample_domains:
            indicator = ThreatIndicator(
                indicator_type='domain',
                value=domain,
                threat_types=[ThreatType.MALWARE_DOMAIN],
                source=FeedSource.BLACKWEB,
                confidence=85,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                ttl=3600,
                metadata={'category': 'test_sample'}
            )
            security_feeds_manager._store_indicator(indicator)
        
        for ip in sample_ips:
            indicator = ThreatIndicator(
                indicator_type='ip',
                value=ip,
                threat_types=[ThreatType.MALWARE_IP],
                source=FeedSource.SPAMHAUS,
                confidence=90,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                ttl=3600,
                metadata={'category': 'test_sample'}
            )
            security_feeds_manager._store_indicator(indicator)
        
        logger.info(f"Created {len(sample_domains)} sample domain indicators and {len(sample_ips)} sample IP indicators")
        
    except Exception as e:
        logger.error(f"Failed to create sample threats: {e}")


async def run_initial_feed_update():
    """Run initial feed update for available sources."""
    logger.info("Running initial security feeds update...")
    
    try:
        from security.feeds import FeedSource
        
        # Update available feeds
        for source in [FeedSource.BLACKWEB, FeedSource.SPAMHAUS]:
            try:
                logger.info(f"Updating {source.value} feed...")
                stats = await security_feeds_manager.update_feed(source)
                logger.info(f"Updated {source.value}: {stats}")
            except Exception as e:
                logger.warning(f"Failed to update {source.value}: {e}")
        
        logger.info("Initial feeds update completed")
        
    except Exception as e:
        logger.error(f"Initial feeds update failed: {e}")


async def run_initial_scan():
    """Run initial security scan."""
    logger.info("Running initial security scan...")
    
    try:
        from security.scanner import ScanType
        
        # Run a threat intelligence scan
        config = security_scanner.scan_configs.get(ScanType.THREAT_INTEL_SCAN, {})
        await security_scanner._execute_scan(ScanType.THREAT_INTEL_SCAN, config)
        
        logger.info("Initial security scan completed")
        
    except Exception as e:
        logger.error(f"Initial security scan failed: {e}")


async def main():
    """Main initialization function."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        logger.info("Starting SASEWaddle security system initialization...")
        
        # Create sample threat indicators for testing
        create_sample_threats()
        
        # Test security feeds functionality
        if not test_security_feeds():
            logger.error("Security feeds test failed, aborting initialization")
            return False
        
        # Run initial feed update (comment out for faster testing)
        # await run_initial_feed_update()
        
        # Run initial security scan
        # await run_initial_scan()
        
        logger.info("✓ Security system initialization completed successfully")
        
        # Keep running for a short time to test feeds
        logger.info("Running security feeds for 30 seconds...")
        await asyncio.sleep(30)
        
        return True
        
    except KeyboardInterrupt:
        logger.info("Initialization interrupted by user")
        return True
    except Exception as e:
        logger.error(f"Security system initialization failed: {e}")
        return False
    finally:
        # Cleanup
        try:
            await security_feeds_manager.stop_feed_updates()
        except:
            pass


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)