"""
PenguinTech License Server Python Client

This module provides a Python client for integrating with the PenguinTech License Server
to validate licenses and check feature entitlements.
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from functools import wraps

import requests


logger = logging.getLogger(__name__)


class FeatureNotAvailableError(Exception):
    """Raised when a required feature is not available in the current license."""

    def __init__(self, feature: str):
        self.feature = feature
        super().__init__(f"Feature '{feature}' requires license upgrade")


class LicenseValidationError(Exception):
    """Raised when license validation fails."""
    pass


class PenguinTechLicenseClient:
    """Client for PenguinTech License Server integration."""

    def __init__(
        self,
        license_key: str,
        product: str,
        base_url: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize the license client.

        Args:
            license_key: The license key (format: PENG-XXXX-XXXX-XXXX-XXXX-ABCD)
            product: The product identifier
            base_url: License server URL (default: https://license.penguintech.io)
            timeout: Request timeout in seconds
        """
        self.license_key = license_key
        self.product = product
        self.base_url = base_url or "https://license.penguintech.io"
        self.server_id = None
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {license_key}",
            "Content-Type": "application/json"
        })
        self.session.timeout = timeout

        # Feature cache
        self._feature_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes

    @classmethod
    def from_env(cls, timeout: int = 30) -> Optional['PenguinTechLicenseClient']:
        """
        Create client from environment variables.

        Requires LICENSE_KEY and PRODUCT_NAME environment variables.
        Optional LICENSE_SERVER_URL for custom server.

        Args:
            timeout: Request timeout in seconds

        Returns:
            PenguinTechLicenseClient instance or None if env vars missing
        """
        license_key = os.getenv("LICENSE_KEY")
        product = os.getenv("PRODUCT_NAME")
        base_url = os.getenv("LICENSE_SERVER_URL")

        if not license_key or not product:
            logger.warning("LICENSE_KEY and PRODUCT_NAME environment variables required")
            return None

        return cls(license_key, product, base_url, timeout)

    def validate(self) -> Dict[str, Any]:
        """
        Validate license and get server ID for keepalives.

        Returns:
            Dict containing validation response

        Raises:
            LicenseValidationError: If validation fails
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/v2/validate",
                json={"product": self.product}
            )
            response.raise_for_status()

            data = response.json()

            if not data.get("valid"):
                raise LicenseValidationError(f"License validation failed: {data.get('message')}")

            # Store server ID for keepalives
            if "metadata" in data and "server_id" in data["metadata"]:
                self.server_id = data["metadata"]["server_id"]

            # Update feature cache
            self._update_feature_cache(data.get("features", []))

            return data

        except requests.RequestException as e:
            raise LicenseValidationError(f"License validation request failed: {e}")

    def check_feature(self, feature: str, use_cache: bool = True) -> bool:
        """
        Check if a specific feature is enabled.

        Args:
            feature: Feature name to check
            use_cache: Whether to use cached results

        Returns:
            True if feature is enabled, False otherwise
        """
        # Check cache first if enabled and valid
        if use_cache and self._is_cache_valid():
            cached_result = self._feature_cache.get(feature)
            if cached_result is not None:
                return cached_result

        try:
            response = self.session.post(
                f"{self.base_url}/api/v2/features",
                json={"product": self.product, "feature": feature}
            )
            response.raise_for_status()

            data = response.json()
            features = data.get("features", [])

            if features:
                entitled = features[0].get("entitled", False)
                # Cache the result
                self._feature_cache[feature] = entitled
                self._cache_timestamp = time.time()
                return entitled

            return False

        except requests.RequestException as e:
            logger.error(f"Feature check failed for {feature}: {e}")
            return False

    def keepalive(self, usage_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send keepalive with optional usage statistics.

        Args:
            usage_data: Optional usage statistics to send

        Returns:
            Dict containing keepalive response

        Raises:
            LicenseValidationError: If keepalive fails
        """
        if not self.server_id:
            # Validate first to get server ID
            validation = self.validate()
            if not validation.get("valid"):
                raise LicenseValidationError("Failed to validate license for keepalive")

        payload = {
            "product": self.product,
            "server_id": self.server_id
        }

        if usage_data:
            payload.update(usage_data)

        try:
            response = self.session.post(
                f"{self.base_url}/api/v2/keepalive",
                json=payload
            )
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            raise LicenseValidationError(f"Keepalive request failed: {e}")

    def get_all_features(self) -> Dict[str, bool]:
        """
        Get all available features from cache or validation.

        Returns:
            Dict mapping feature names to enabled status
        """
        if not self._is_cache_valid():
            try:
                self.validate()
            except LicenseValidationError:
                logger.error("Failed to refresh feature cache")

        return self._feature_cache.copy()

    def _update_feature_cache(self, features: List[Dict[str, Any]]) -> None:
        """Update the feature cache with new feature data."""
        self._feature_cache = {}
        for feature in features:
            name = feature.get("name")
            entitled = feature.get("entitled", False)
            if name:
                self._feature_cache[name] = entitled

        self._cache_timestamp = time.time()

    def _is_cache_valid(self) -> bool:
        """Check if the feature cache is still valid."""
        if self._cache_timestamp is None:
            return False

        return (time.time() - self._cache_timestamp) < self._cache_ttl

    @staticmethod
    def is_valid_license_key(key: str) -> bool:
        """
        Validate license key format.

        Args:
            key: License key to validate

        Returns:
            True if format is valid
        """
        if not key or len(key) != 29:
            return False

        if not key.startswith("PENG-"):
            return False

        # Count dashes - should be 5 total
        return key.count("-") == 5


# Global client instance for convenience
_global_client: Optional[PenguinTechLicenseClient] = None


def get_client() -> Optional[PenguinTechLicenseClient]:
    """Get the global license client instance."""
    global _global_client
    if _global_client is None:
        _global_client = PenguinTechLicenseClient.from_env()
    return _global_client


def requires_feature(feature_name: str, client: Optional[PenguinTechLicenseClient] = None):
    """
    Decorator to gate functionality behind license features.

    Args:
        feature_name: Name of the required feature
        client: License client instance (uses global if None)

    Raises:
        FeatureNotAvailableError: If feature is not available
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            license_client = client or get_client()

            if not license_client:
                raise FeatureNotAvailableError(feature_name)

            if not license_client.check_feature(feature_name):
                raise FeatureNotAvailableError(feature_name)

            return func(*args, **kwargs)

        return wrapper
    return decorator


def initialize_licensing(license_key: str = None, product: str = None) -> Dict[str, Any]:
    """
    Initialize licensing system and validate license.

    Args:
        license_key: License key (uses env var if None)
        product: Product name (uses env var if None)

    Returns:
        Validation response dict

    Raises:
        LicenseValidationError: If initialization fails
    """
    global _global_client

    # Use provided values or environment variables
    license_key = license_key or os.getenv("LICENSE_KEY")
    product = product or os.getenv("PRODUCT_NAME")

    if not license_key or not product:
        raise LicenseValidationError("LICENSE_KEY and PRODUCT_NAME are required")

    _global_client = PenguinTechLicenseClient(license_key, product)
    validation = _global_client.validate()

    logger.info(f"License valid for {validation['customer']} ({validation['tier']} tier)")

    # Log available features
    for feature in validation.get("features", []):
        if feature.get("entitled"):
            logger.info(f"Feature enabled: {feature['name']}")

    return validation


# Convenience functions for common operations
def check_feature(feature: str) -> bool:
    """Check if a feature is available using the global client."""
    client = get_client()
    if not client:
        return False
    return client.check_feature(feature)


def send_keepalive(usage_data: Dict[str, Any] = None) -> bool:
    """Send keepalive using the global client."""
    client = get_client()
    if not client:
        return False

    try:
        client.keepalive(usage_data)
        return True
    except LicenseValidationError:
        logger.error("Failed to send keepalive")
        return False