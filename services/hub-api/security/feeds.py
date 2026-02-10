"""Security threat feeds integration for SASEWaddle Manager."""

import os
import json
import logging
import hashlib
import requests
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Set, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import ipaddress
import dns.resolver
import xml.etree.ElementTree as ET
from pathlib import Path

from database import get_db
from ..audit import audit_logger, AuditEventType

logger = logging.getLogger(__name__)


class ThreatType(Enum):
    """Types of threats from security feeds."""
    MALWARE_DOMAIN = "malware_domain"
    PHISHING_DOMAIN = "phishing_domain"
    SPAM_DOMAIN = "spam_domain"
    BOTNET_IP = "botnet_ip"
    MALWARE_IP = "malware_ip"
    SCANNING_IP = "scanning_ip"
    REPUTATION_IP = "reputation_ip"
    BLACKLISTED_DOMAIN = "blacklisted_domain"
    BLACKLISTED_IP = "blacklisted_ip"


class FeedSource(Enum):
    """Security feed sources."""
    BLACKWEB = "blackweb"
    SPAMHAUS = "spamhaus"
    IPVOID = "ipvoid"
    DNSBL = "dnsbl"
    STIX_TAXII = "stix_taxii"


@dataclass
class ThreatIndicator:
    """Security threat indicator."""
    indicator_type: str  # 'domain' or 'ip'
    value: str
    threat_types: List[ThreatType]
    source: FeedSource
    confidence: int  # 1-100
    first_seen: datetime
    last_seen: datetime
    ttl: int  # Time to live in seconds
    metadata: Dict[str, Any]


class SecurityFeedsManager:
    """Manage security threat intelligence feeds."""
    
    def __init__(self):
        self.db = get_db()
        self.session = None
        self._ensure_feeds_tables()
        
        # Feed configurations
        self.feed_configs = {
            FeedSource.BLACKWEB: {
                'domains_url': 'https://raw.githubusercontent.com/maravento/blackweb/master/blackweb.txt',
                'ips_url': 'https://raw.githubusercontent.com/maravento/blackweb/master/blackip.txt',
                'update_interval': 3600,  # 1 hour
                'confidence': 85
            },
            FeedSource.SPAMHAUS: {
                'drop_url': 'https://www.spamhaus.org/drop/drop.txt',
                'edrop_url': 'https://www.spamhaus.org/drop/edrop.txt',
                'pbl_url': 'https://www.spamhaus.org/pbl/pbl.txt',
                'update_interval': 1800,  # 30 minutes
                'confidence': 95
            },
            FeedSource.IPVOID: {
                'api_url': 'https://endpoint.apivoid.com/iprep/v1/pay-as-you-go/',
                'api_key': os.getenv('IPVOID_API_KEY'),
                'update_interval': 3600,  # 1 hour
                'confidence': 90
            },
            FeedSource.DNSBL: {
                'providers': [
                    'zen.spamhaus.org',
                    'bl.spamcop.net',
                    'dnsbl.sorbs.net',
                    'cbl.abuseat.org'
                ],
                'update_interval': 1800,  # 30 minutes
                'confidence': 80
            }
        }
        
        # Cache for recent lookups
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def _ensure_feeds_tables(self):
        """Create security feeds database tables."""
        
        # Threat indicators table
        if 'threat_indicators' not in self.db.tables:
            self.db.define_table('threat_indicators',
                self.db.Field('indicator_type', 'string', length=16, required=True),  # domain/ip
                self.db.Field('value', 'string', length=255, required=True),
                self.db.Field('threat_types', 'json', required=True),
                self.db.Field('source', 'string', length=32, required=True),
                self.db.Field('confidence', 'integer', required=True),
                self.db.Field('first_seen', 'datetime', required=True),
                self.db.Field('last_seen', 'datetime', required=True),
                self.db.Field('ttl', 'integer', default=3600),
                self.db.Field('metadata', 'json'),
                self.db.Field('active', 'boolean', default=True),
                self.db.Field('created_at', 'datetime', default=datetime.utcnow),
                self.db.Field('updated_at', 'datetime', default=datetime.utcnow, update=datetime.utcnow)
            )
            
            # Create indexes
            try:
                self.db.executesql('CREATE INDEX idx_threat_indicators_value ON threat_indicators(value)')
                self.db.executesql('CREATE INDEX idx_threat_indicators_type ON threat_indicators(indicator_type)')
                self.db.executesql('CREATE INDEX idx_threat_indicators_source ON threat_indicators(source)')
                self.db.executesql('CREATE INDEX idx_threat_indicators_active ON threat_indicators(active)')
                self.db.executesql('CREATE UNIQUE INDEX idx_threat_indicators_unique ON threat_indicators(value, source)')
                logger.info("Created indexes for threat_indicators table")
            except Exception as e:
                logger.warning(f"Could not create threat indicators indexes: {e}")
        
        # Feed update history table
        if 'feed_updates' not in self.db.tables:
            self.db.define_table('feed_updates',
                self.db.Field('source', 'string', length=32, required=True),
                self.db.Field('update_type', 'string', length=32, required=True),
                self.db.Field('status', 'string', length=16, required=True),
                self.db.Field('indicators_added', 'integer', default=0),
                self.db.Field('indicators_updated', 'integer', default=0),
                self.db.Field('indicators_removed', 'integer', default=0),
                self.db.Field('error_message', 'text'),
                self.db.Field('duration_seconds', 'integer'),
                self.db.Field('started_at', 'datetime', required=True),
                self.db.Field('completed_at', 'datetime')
            )
        
        # Threat detection log
        if 'threat_detections' not in self.db.tables:
            self.db.define_table('threat_detections',
                self.db.Field('client_ip', 'string', length=45, required=True),
                self.db.Field('requested_domain', 'string', length=255),
                self.db.Field('requested_ip', 'string', length=45),
                self.db.Field('threat_indicator_id', 'reference threat_indicators'),
                self.db.Field('action_taken', 'string', length=32, required=True),  # blocked/logged/allowed
                self.db.Field('threat_types', 'json'),
                self.db.Field('confidence', 'integer'),
                self.db.Field('source', 'string', length=32),
                self.db.Field('metadata', 'json'),
                self.db.Field('detected_at', 'datetime', default=datetime.utcnow)
            )
            
            # Create indexes
            try:
                self.db.executesql('CREATE INDEX idx_threat_detections_client_ip ON threat_detections(client_ip)')
                self.db.executesql('CREATE INDEX idx_threat_detections_domain ON threat_detections(requested_domain)')
                self.db.executesql('CREATE INDEX idx_threat_detections_detected_at ON threat_detections(detected_at)')
                logger.info("Created indexes for threat_detections table")
            except Exception as e:
                logger.warning(f"Could not create threat detections indexes: {e}")
        
        self.db.commit()
        logger.info("Security feeds tables ensured")
    
    async def start_feed_updates(self):
        """Start automated feed updates."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        logger.info("Starting security feeds update process")
        
        # Schedule updates for each feed
        tasks = []
        for source in FeedSource:
            if source == FeedSource.STIX_TAXII:
                continue  # STIX/TAXII requires separate implementation
            
            tasks.append(self._schedule_feed_updates(source))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_feed_updates(self):
        """Stop feed updates and cleanup."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def _schedule_feed_updates(self, source: FeedSource):
        """Schedule periodic updates for a feed source."""
        config = self.feed_configs.get(source)
        if not config:
            return
        
        interval = config.get('update_interval', 3600)
        
        while True:
            try:
                await self.update_feed(source)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating feed {source.value}: {e}")
                # Wait before retrying
                await asyncio.sleep(300)  # 5 minutes
    
    async def update_feed(self, source: FeedSource) -> Dict[str, int]:
        """Update a specific threat feed."""
        start_time = datetime.utcnow()
        stats = {
            'added': 0,
            'updated': 0,
            'removed': 0,
            'errors': 0
        }
        
        try:
            logger.info(f"Updating threat feed: {source.value}")
            
            # Record feed update start
            update_id = self.db.feed_updates.insert(
                source=source.value,
                update_type='automatic',
                status='running',
                started_at=start_time
            )
            self.db.commit()
            
            # Update based on source type
            if source == FeedSource.BLACKWEB:
                stats = await self._update_blackweb_feed()
            elif source == FeedSource.SPAMHAUS:
                stats = await self._update_spamhaus_feed()
            elif source == FeedSource.IPVOID:
                stats = await self._update_ipvoid_feed()
            elif source == FeedSource.DNSBL:
                stats = await self._update_dnsbl_feed()
            
            # Record successful completion
            duration = int((datetime.utcnow() - start_time).total_seconds())
            self.db(self.db.feed_updates.id == update_id).update(
                status='completed',
                indicators_added=stats['added'],
                indicators_updated=stats['updated'],
                indicators_removed=stats['removed'],
                duration_seconds=duration,
                completed_at=datetime.utcnow()
            )
            self.db.commit()
            
            # Log audit event
            audit_logger.log_event(
                event_type=AuditEventType.ADMIN_ACTION,
                action=f'update_threat_feed_{source.value}',
                details={
                    'source': source.value,
                    'indicators_added': stats['added'],
                    'indicators_updated': stats['updated'],
                    'indicators_removed': stats['removed'],
                    'duration_seconds': duration
                },
                severity='info',
                outcome='success'
            )
            
            logger.info(f"Successfully updated {source.value} feed: {stats}")
            
        except Exception as e:
            # Record failed update
            duration = int((datetime.utcnow() - start_time).total_seconds())
            self.db(self.db.feed_updates.id == update_id).update(
                status='failed',
                error_message=str(e),
                duration_seconds=duration,
                completed_at=datetime.utcnow()
            )
            self.db.commit()
            
            # Log audit event
            audit_logger.log_event(
                event_type=AuditEventType.ADMIN_ACTION,
                action=f'update_threat_feed_{source.value}',
                details={
                    'source': source.value,
                    'error': str(e),
                    'duration_seconds': duration
                },
                severity='error',
                outcome='failure'
            )
            
            logger.error(f"Failed to update {source.value} feed: {e}")
            stats['errors'] = 1
        
        return stats
    
    async def _update_blackweb_feed(self) -> Dict[str, int]:
        """Update Blackweb threat feed."""
        stats = {'added': 0, 'updated': 0, 'removed': 0, 'errors': 0}
        config = self.feed_configs[FeedSource.BLACKWEB]
        
        # Update domains
        try:
            async with self.session.get(config['domains_url']) as response:
                if response.status == 200:
                    content = await response.text()
                    domains = self._parse_blackweb_domains(content)
                    
                    for domain in domains:
                        indicator = ThreatIndicator(
                            indicator_type='domain',
                            value=domain,
                            threat_types=[ThreatType.BLACKLISTED_DOMAIN],
                            source=FeedSource.BLACKWEB,
                            confidence=config['confidence'],
                            first_seen=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                            ttl=config['update_interval'],
                            metadata={'category': 'blacklisted'}
                        )
                        
                        if self._store_indicator(indicator):
                            stats['added'] += 1
        except Exception as e:
            logger.error(f"Failed to update Blackweb domains: {e}")
            stats['errors'] += 1
        
        # Update IPs
        try:
            async with self.session.get(config['ips_url']) as response:
                if response.status == 200:
                    content = await response.text()
                    ips = self._parse_blackweb_ips(content)
                    
                    for ip in ips:
                        indicator = ThreatIndicator(
                            indicator_type='ip',
                            value=ip,
                            threat_types=[ThreatType.BLACKLISTED_IP],
                            source=FeedSource.BLACKWEB,
                            confidence=config['confidence'],
                            first_seen=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                            ttl=config['update_interval'],
                            metadata={'category': 'blacklisted'}
                        )
                        
                        if self._store_indicator(indicator):
                            stats['added'] += 1
        except Exception as e:
            logger.error(f"Failed to update Blackweb IPs: {e}")
            stats['errors'] += 1
        
        return stats
    
    async def _update_spamhaus_feed(self) -> Dict[str, int]:
        """Update Spamhaus threat feed."""
        stats = {'added': 0, 'updated': 0, 'removed': 0, 'errors': 0}
        config = self.feed_configs[FeedSource.SPAMHAUS]
        
        # Update DROP list
        try:
            async with self.session.get(config['drop_url']) as response:
                if response.status == 200:
                    content = await response.text()
                    networks = self._parse_spamhaus_drop(content)
                    
                    for network in networks:
                        indicator = ThreatIndicator(
                            indicator_type='ip',
                            value=network,
                            threat_types=[ThreatType.SPAM_DOMAIN, ThreatType.REPUTATION_IP],
                            source=FeedSource.SPAMHAUS,
                            confidence=config['confidence'],
                            first_seen=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                            ttl=config['update_interval'],
                            metadata={'list': 'DROP'}
                        )
                        
                        if self._store_indicator(indicator):
                            stats['added'] += 1
        except Exception as e:
            logger.error(f"Failed to update Spamhaus DROP: {e}")
            stats['errors'] += 1
        
        # Update EDROP list
        try:
            async with self.session.get(config['edrop_url']) as response:
                if response.status == 200:
                    content = await response.text()
                    networks = self._parse_spamhaus_drop(content)
                    
                    for network in networks:
                        indicator = ThreatIndicator(
                            indicator_type='ip',
                            value=network,
                            threat_types=[ThreatType.SPAM_DOMAIN, ThreatType.REPUTATION_IP],
                            source=FeedSource.SPAMHAUS,
                            confidence=config['confidence'],
                            first_seen=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                            ttl=config['update_interval'],
                            metadata={'list': 'EDROP'}
                        )
                        
                        if self._store_indicator(indicator):
                            stats['added'] += 1
        except Exception as e:
            logger.error(f"Failed to update Spamhaus EDROP: {e}")
            stats['errors'] += 1
        
        return stats
    
    async def _update_ipvoid_feed(self) -> Dict[str, int]:
        """Update IPVoid reputation feed."""
        stats = {'added': 0, 'updated': 0, 'removed': 0, 'errors': 0}
        config = self.feed_configs[FeedSource.IPVOID]
        
        if not config.get('api_key'):
            logger.warning("IPVoid API key not configured, skipping update")
            return stats
        
        # IPVoid requires individual IP lookups rather than bulk download
        # This would typically be used for on-demand reputation checks
        # For now, we'll skip bulk updates and implement real-time lookups
        logger.info("IPVoid feed configured for real-time lookups only")
        
        return stats
    
    async def _update_dnsbl_feed(self) -> Dict[str, int]:
        """Update DNSBL reputation feed."""
        stats = {'added': 0, 'updated': 0, 'removed': 0, 'errors': 0}
        
        # DNSBL also works with real-time lookups rather than bulk downloads
        # We'll implement the lookup mechanism for real-time checking
        logger.info("DNSBL feed configured for real-time lookups only")
        
        return stats
    
    def _parse_blackweb_domains(self, content: str) -> List[str]:
        """Parse Blackweb domains file."""
        domains = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('!'):
                # Clean domain format
                domain = line.replace('||', '').replace('^', '').replace('*', '')
                if '.' in domain and len(domain) > 3:
                    domains.append(domain)
        return domains
    
    def _parse_blackweb_ips(self, content: str) -> List[str]:
        """Parse Blackweb IPs file."""
        ips = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    # Validate IP address or CIDR
                    ipaddress.ip_network(line, strict=False)
                    ips.append(line)
                except ValueError:
                    continue
        return ips
    
    def _parse_spamhaus_drop(self, content: str) -> List[str]:
        """Parse Spamhaus DROP/EDROP file."""
        networks = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith(';'):
                # Extract CIDR from line (format: "1.2.3.0/24 ; SBL123")
                parts = line.split(';')[0].strip()
                try:
                    ipaddress.ip_network(parts, strict=False)
                    networks.append(parts)
                except ValueError:
                    continue
        return networks
    
    def _store_indicator(self, indicator: ThreatIndicator) -> bool:
        """Store threat indicator in database."""
        try:
            # Check if indicator already exists
            existing = self.db(
                (self.db.threat_indicators.value == indicator.value) &
                (self.db.threat_indicators.source == indicator.source.value)
            ).select().first()
            
            if existing:
                # Update existing indicator
                self.db(self.db.threat_indicators.id == existing.id).update(
                    threat_types=json.dumps([t.value for t in indicator.threat_types]),
                    confidence=indicator.confidence,
                    last_seen=indicator.last_seen,
                    ttl=indicator.ttl,
                    metadata=json.dumps(indicator.metadata),
                    updated_at=datetime.utcnow()
                )
                return False  # Updated, not added
            else:
                # Insert new indicator
                self.db.threat_indicators.insert(
                    indicator_type=indicator.indicator_type,
                    value=indicator.value,
                    threat_types=json.dumps([t.value for t in indicator.threat_types]),
                    source=indicator.source.value,
                    confidence=indicator.confidence,
                    first_seen=indicator.first_seen,
                    last_seen=indicator.last_seen,
                    ttl=indicator.ttl,
                    metadata=json.dumps(indicator.metadata)
                )
                return True  # Added new
                
        except Exception as e:
            logger.error(f"Failed to store indicator {indicator.value}: {e}")
            return False
    
    def check_threat_indicator(self, value: str, indicator_type: str = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Check if a value (domain/IP) is a known threat indicator.
        
        Returns:
            (is_threat, threat_details)
        """
        # Check cache first
        cache_key = f"{indicator_type}:{value}"
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if datetime.utcnow().timestamp() - timestamp < self.cache_ttl:
                return cached_result
        
        threats = []
        
        # Auto-detect type if not provided
        if not indicator_type:
            try:
                ipaddress.ip_address(value)
                indicator_type = 'ip'
            except ValueError:
                indicator_type = 'domain'
        
        # Check database for exact matches
        query = (self.db.threat_indicators.value == value) & \
                (self.db.threat_indicators.active == True)
        
        if indicator_type:
            query &= (self.db.threat_indicators.indicator_type == indicator_type)
        
        indicators = self.db(query).select()
        
        for indicator in indicators:
            threats.append({
                'value': indicator.value,
                'threat_types': json.loads(indicator.threat_types) if indicator.threat_types else [],
                'source': indicator.source,
                'confidence': indicator.confidence,
                'first_seen': indicator.first_seen.isoformat() if indicator.first_seen else None,
                'last_seen': indicator.last_seen.isoformat() if indicator.last_seen else None,
                'metadata': json.loads(indicator.metadata) if indicator.metadata else {}
            })
        
        # For domains, also check parent domains
        if indicator_type == 'domain' and '.' in value:
            domain_parts = value.split('.')
            for i in range(1, len(domain_parts)):
                parent_domain = '.'.join(domain_parts[i:])
                parent_indicators = self.db(
                    (self.db.threat_indicators.value == parent_domain) &
                    (self.db.threat_indicators.indicator_type == 'domain') &
                    (self.db.threat_indicators.active == True)
                ).select()
                
                for indicator in parent_indicators:
                    threats.append({
                        'value': indicator.value,
                        'threat_types': json.loads(indicator.threat_types) if indicator.threat_types else [],
                        'source': indicator.source,
                        'confidence': max(0, indicator.confidence - 10),  # Reduce confidence for parent domain
                        'first_seen': indicator.first_seen.isoformat() if indicator.first_seen else None,
                        'last_seen': indicator.last_seen.isoformat() if indicator.last_seen else None,
                        'metadata': json.loads(indicator.metadata) if indicator.metadata else {},
                        'match_type': 'parent_domain'
                    })
        
        # For IPs, check if it falls within any blocked networks
        if indicator_type == 'ip':
            try:
                ip_obj = ipaddress.ip_address(value)
                network_indicators = self.db(
                    (self.db.threat_indicators.indicator_type == 'ip') &
                    (self.db.threat_indicators.active == True) &
                    (self.db.threat_indicators.value.contains('/'))  # CIDR networks
                ).select()
                
                for indicator in network_indicators:
                    try:
                        network = ipaddress.ip_network(indicator.value, strict=False)
                        if ip_obj in network:
                            threats.append({
                                'value': indicator.value,
                                'threat_types': json.loads(indicator.threat_types) if indicator.threat_types else [],
                                'source': indicator.source,
                                'confidence': indicator.confidence,
                                'first_seen': indicator.first_seen.isoformat() if indicator.first_seen else None,
                                'last_seen': indicator.last_seen.isoformat() if indicator.last_seen else None,
                                'metadata': json.loads(indicator.metadata) if indicator.metadata else {},
                                'match_type': 'network_range'
                            })
                    except ValueError:
                        continue
            except ValueError:
                pass
        
        is_threat = len(threats) > 0
        result = (is_threat, threats)
        
        # Cache result
        self.cache[cache_key] = (result, datetime.utcnow().timestamp())
        
        return result
    
    def log_threat_detection(self, client_ip: str, requested_domain: str = None,
                           requested_ip: str = None, action_taken: str = 'blocked',
                           threat_details: List[Dict[str, Any]] = None) -> str:
        """Log a threat detection event."""
        
        try:
            # Find the highest confidence threat
            highest_confidence = 0
            primary_threat = None
            all_threat_types = []
            sources = []
            
            if threat_details:
                for threat in threat_details:
                    if threat['confidence'] > highest_confidence:
                        highest_confidence = threat['confidence']
                        primary_threat = threat
                    
                    all_threat_types.extend(threat.get('threat_types', []))
                    if threat['source'] not in sources:
                        sources.append(threat['source'])
            
            # Insert detection record
            detection_id = self.db.threat_detections.insert(
                client_ip=client_ip,
                requested_domain=requested_domain,
                requested_ip=requested_ip,
                action_taken=action_taken,
                threat_types=json.dumps(list(set(all_threat_types))),
                confidence=highest_confidence,
                source=','.join(sources),
                metadata=json.dumps({
                    'threat_details': threat_details,
                    'detection_method': 'security_feeds'
                })
            )
            self.db.commit()
            
            # Log audit event
            audit_logger.log_event(
                event_type=AuditEventType.SECURITY_INCIDENT,
                ip_address=client_ip,
                action=f'threat_detected_{action_taken}',
                details={
                    'requested_domain': requested_domain,
                    'requested_ip': requested_ip,
                    'action_taken': action_taken,
                    'threat_types': all_threat_types,
                    'confidence': highest_confidence,
                    'sources': sources,
                    'threat_count': len(threat_details) if threat_details else 0
                },
                severity='high' if highest_confidence > 80 else 'medium',
                outcome='success'
            )
            
            logger.warning(f"Threat detected - Client: {client_ip}, Target: {requested_domain or requested_ip}, "
                         f"Action: {action_taken}, Confidence: {highest_confidence}")
            
            return str(detection_id)
            
        except Exception as e:
            logger.error(f"Failed to log threat detection: {e}")
            return ""
    
    def get_threat_statistics(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get threat detection statistics."""
        
        since = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Total detections
        total_detections = self.db(
            self.db.threat_detections.detected_at >= since
        ).count()
        
        # Detections by action
        actions = self.db(
            self.db.threat_detections.detected_at >= since
        ).select(
            self.db.threat_detections.action_taken,
            self.db.threat_detections.id.count(),
            groupby=self.db.threat_detections.action_taken
        )
        
        action_counts = {}
        for row in actions:
            action_counts[row.threat_detections.action_taken] = row._extra[self.db.threat_detections.id.count()]
        
        # Top threat sources
        sources = self.db(
            self.db.threat_detections.detected_at >= since
        ).select(
            self.db.threat_detections.source,
            self.db.threat_detections.id.count(),
            groupby=self.db.threat_detections.source,
            orderby=~self.db.threat_detections.id.count(),
            limitby=(0, 5)
        )
        
        top_sources = []
        for row in sources:
            if row.threat_detections.source:
                top_sources.append({
                    'source': row.threat_detections.source,
                    'count': row._extra[self.db.threat_detections.id.count()]
                })
        
        # Active indicators count
        active_indicators = self.db(
            self.db.threat_indicators.active == True
        ).count()
        
        # Indicators by source
        indicator_sources = self.db(
            self.db.threat_indicators.active == True
        ).select(
            self.db.threat_indicators.source,
            self.db.threat_indicators.id.count(),
            groupby=self.db.threat_indicators.source
        )
        
        source_counts = {}
        for row in indicator_sources:
            source_counts[row.threat_indicators.source] = row._extra[self.db.threat_indicators.id.count()]
        
        return {
            'period_hours': hours_back,
            'total_detections': total_detections,
            'action_counts': action_counts,
            'top_threat_sources': top_sources,
            'active_indicators': active_indicators,
            'indicators_by_source': source_counts
        }


# Global security feeds manager instance
security_feeds_manager = SecurityFeedsManager()