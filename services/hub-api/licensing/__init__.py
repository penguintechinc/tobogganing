"""
SASEWaddle License Management
Handles license validation and feature gating
"""

import os
import requests
import json
from functools import wraps
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import structlog

logger = structlog.get_logger()

# License server configuration
LICENSE_SERVER_URL = os.getenv('LICENSE_SERVER_URL', 'https://license.penguintech.io')
LICENSE_KEY = os.getenv('SASEWADDLE_LICENSE_KEY', '')

# Cache for license validation
_license_cache = {
    'valid': False,
    'features': [],
    'tier': 'basic',
    'expires_at': None,
    'last_check': None,
    'max_clients': 10,
    'max_headends': 1
}

def validate_license(force_check: bool = False) -> Dict[str, Any]:
    """
    Validate SASEWaddle license with the license server
    Results are cached for 1 hour to reduce API calls
    """
    global _license_cache
    
    # Check cache validity (1 hour)
    if not force_check and _license_cache['last_check']:
        time_since_check = datetime.now() - _license_cache['last_check']
        if time_since_check < timedelta(hours=1) and _license_cache['valid']:
            return _license_cache
    
    # No license key configured - community open source features
    if not LICENSE_KEY:
        logger.info("No license key configured, running in Community Open Source mode")
        _license_cache = {
            'valid': True,
            'features': ['wireguard_vpn', 'basic_firewall', 'certificate_management', 'web_portal', 'basic_auth', 'split_tunnel', 'unlimited_clients', 'unlimited_headends'],
            'tier': 'community',
            'expires_at': None,
            'last_check': datetime.now(),
            'max_clients': None,  # No limits in community
            'max_headends': None  # No limits in community
        }
        return _license_cache
    
    try:
        # Validate with license server using new multi-product API
        response = requests.post(
            f"{LICENSE_SERVER_URL}/api/validate",
            json={
                'license_key': LICENSE_KEY,
                'product': 'sasewaddle'
            },
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('valid'):
                _license_cache = {
                    'valid': True,
                    'features': data.get('features', []),
                    'tier': data.get('tier', 'community'),
                    'expires_at': data.get('expires_at'),
                    'last_check': datetime.now(),
                    'max_clients': None,  # No limits with new model
                    'max_headends': None,  # No limits with new model
                    'organization': data.get('organization', ''),
                    'product': data.get('product', 'sasewaddle'),
                    'all_products': data.get('all_products', {})
                }
                logger.info(f"License validated: {_license_cache['tier']} tier")
                return _license_cache
        
        logger.error(f"License validation failed: {response.status_code}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to contact license server: {e}")
        # If we have a previously valid cache, continue using it
        if _license_cache['valid']:
            logger.warning("Using cached license data")
            return _license_cache
    
    # Default to community features on error
    _license_cache = {
        'valid': False,
        'features': ['wireguard_vpn', 'basic_firewall', 'certificate_management', 'web_portal', 'basic_auth', 'split_tunnel', 'unlimited_clients', 'unlimited_headends'],
        'tier': 'community',
        'expires_at': None,
        'last_check': datetime.now(),
        'max_clients': None,  # No limits in community
        'max_headends': None  # No limits in community
    }
    return _license_cache

def check_feature(feature: str) -> bool:
    """
    Check if a specific feature is enabled in the current license
    """
    license_info = validate_license()
    return feature in license_info.get('features', [])

def require_feature(feature: str):
    """
    Decorator to require a specific license feature for an endpoint
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not check_feature(feature):
                from py4web import response
                response.status = 402  # Payment Required
                return {
                    'error': 'License required',
                    'message': f"Feature '{feature}' requires a professional or enterprise license",
                    'required_feature': feature,
                    'current_tier': _license_cache.get('tier', 'basic')
                }
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def get_license_info() -> Dict[str, Any]:
    """
    Get current license information
    """
    return validate_license()

def is_enterprise() -> bool:
    """
    Check if running with enterprise license
    """
    license_info = validate_license()
    return license_info.get('tier') == 'enterprise'

def is_professional() -> bool:
    """
    Check if running with professional license or higher
    """
    license_info = validate_license()
    return license_info.get('tier') in ['professional', 'enterprise']

def check_client_limit(current_count: int) -> bool:
    """
    Check if adding another client would exceed license limit
    Community edition has no limits, other tiers may have custom limits
    """
    license_info = validate_license()
    max_clients = license_info.get('max_clients')
    # None means unlimited (community edition)
    if max_clients is None:
        return True
    return current_count < max_clients

def check_headend_limit(current_count: int) -> bool:
    """
    Check if adding another headend would exceed license limit
    Community edition has no limits, other tiers may have custom limits
    """
    license_info = validate_license()
    max_headends = license_info.get('max_headends')
    # None means unlimited (community edition)
    if max_headends is None:
        return True
    return current_count < max_headends

# Initialize license on module load
validate_license()