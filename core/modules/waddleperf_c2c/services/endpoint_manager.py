"""Cluster-to-cluster endpoint management using penguin-dal."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = structlog.get_logger()


@dataclass(slots=True)
class EndpointRecord:
    """C2C endpoint data structure."""

    id: str
    tenant: str
    region: str
    name: str
    engine_url: str
    target: str
    api_key_hash: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class EndpointManager:
    """Manages cluster-to-cluster test endpoints using penguin-dal."""

    def __init__(self, db: object, tenant: str) -> None:
        """Initialize EndpointManager.

        Args:
            db: penguin-dal DAL instance
            tenant: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant = tenant

    def list_endpoints(self, enabled_only: bool = False) -> list[dict[str, object]]:
        """List all endpoints for this tenant.

        Args:
            enabled_only: If True, only return enabled endpoints

        Returns:
            List of endpoint dicts, newest first
        """
        if enabled_only:
            endpoints = self.db.c2c_endpoints.select(
                tenant=self.tenant, enabled=True
            )
        else:
            endpoints = self.db.c2c_endpoints.select(tenant=self.tenant)

        if not endpoints:
            return []

        # Convert to list if single result
        endpoint_list = endpoints if isinstance(endpoints, list) else [endpoints]

        return [
            {
                "id": e.id,
                "tenant": e.tenant,
                "region": e.region,
                "name": e.name,
                "engine_url": e.engine_url,
                "target": e.target,
                "api_key_hash": e.api_key_hash,
                "enabled": e.enabled,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in endpoint_list
        ]

    def get_endpoint(self, endpoint_id: str) -> dict[str, object] | None:
        """Get an endpoint by ID.

        Args:
            endpoint_id: Endpoint ID

        Returns:
            Endpoint dict or None if not found or belongs to different tenant
        """
        endpoint = self.db.c2c_endpoints.select(
            id=endpoint_id, tenant=self.tenant
        )

        if not endpoint:
            return None

        return {
            "id": endpoint.id,
            "tenant": endpoint.tenant,
            "region": endpoint.region,
            "name": endpoint.name,
            "engine_url": endpoint.engine_url,
            "target": endpoint.target,
            "api_key_hash": endpoint.api_key_hash,
            "enabled": endpoint.enabled,
            "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
            "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
        }

    def create_endpoint(
        self,
        region: str,
        name: str,
        engine_url: str,
        target: str,
        api_key: str | None = None,
    ) -> tuple[dict[str, object], str | None]:
        """Create a new endpoint.

        Args:
            region: Region name
            name: Endpoint name
            engine_url: Base URL of the test engine
            target: Target host that other nodes test against
            api_key: Optional API key; if None, one is generated

        Returns:
            Tuple of (endpoint_dict, raw_api_key). If api_key provided,
            raw_api_key is None. If generated, raw_api_key is returned once.

        Raises:
            ValueError: If endpoint with same (tenant, region, name) already exists
        """
        # Check for duplicate
        existing = self.db.c2c_endpoints.select(
            tenant=self.tenant, region=region, name=name
        )
        if existing:
            raise ValueError(
                f"Endpoint with tenant={self.tenant}, region={region}, name={name} already exists"
            )

        # Generate or hash API key
        if api_key is None:
            api_key = secrets.token_urlsafe(32)
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            return_key = api_key
        else:
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            return_key = None

        # Create endpoint
        endpoint = self.db.c2c_endpoints.create(
            tenant=self.tenant,
            region=region,
            name=name,
            engine_url=engine_url,
            target=target,
            api_key_hash=api_key_hash,
            enabled=True,
        )

        logger.info(
            "endpoint_created",
            endpoint_id=endpoint.id,
            region=region,
            name=name,
            tenant=self.tenant,
        )

        endpoint_dict = {
            "id": endpoint.id,
            "tenant": endpoint.tenant,
            "region": endpoint.region,
            "name": endpoint.name,
            "engine_url": endpoint.engine_url,
            "target": endpoint.target,
            "api_key_hash": endpoint.api_key_hash,
            "enabled": endpoint.enabled,
            "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
            "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
        }

        return (endpoint_dict, return_key)

    def update_endpoint(self, endpoint_id: str, **fields: object) -> dict[str, object] | None:
        """Update an endpoint.

        Args:
            endpoint_id: Endpoint ID
            **fields: Fields to update (name, engine_url, target, region, enabled)

        Returns:
            Updated endpoint dict or None if not found
        """
        # Verify ownership by tenant
        existing = self.db.c2c_endpoints.select(
            id=endpoint_id, tenant=self.tenant
        )
        if not existing:
            return None

        # Filter to allowed fields
        allowed = {"name", "engine_url", "target", "region", "enabled"}
        update_data = {k: v for k, v in fields.items() if k in allowed}

        if not update_data:
            return self.get_endpoint(endpoint_id)

        # Update with current timestamp
        self.db.c2c_endpoints.update(
            id=endpoint_id,
            tenant=self.tenant,
            **update_data,
        )

        logger.info(
            "endpoint_updated",
            endpoint_id=endpoint_id,
            tenant=self.tenant,
        )

        return self.get_endpoint(endpoint_id)

    def delete_endpoint(self, endpoint_id: str) -> bool:
        """Delete an endpoint.

        Args:
            endpoint_id: Endpoint ID

        Returns:
            True if deleted, False if not found
        """
        existing = self.db.c2c_endpoints.select(
            id=endpoint_id, tenant=self.tenant
        )
        if not existing:
            return False

        self.db.c2c_endpoints.delete(id=endpoint_id, tenant=self.tenant)

        logger.info(
            "endpoint_deleted",
            endpoint_id=endpoint_id,
            tenant=self.tenant,
        )

        return True


def authenticate_node_global(
    db: object, api_key: str
) -> tuple[dict[str, object], str] | None:
    """Authenticate a node globally by API key without trusting tenant.

    Searches across all tenants, validates the key hash with constant-time
    comparison, and returns the endpoint and its tenant.

    Args:
        db: penguin-dal DAL instance
        api_key: Unencrypted API key from request

    Returns:
        Tuple of (endpoint_dict, tenant) if authenticated, None otherwise
    """
    try:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Query c2c_endpoints globally (no tenant filter)
        endpoint = db.c2c_endpoints.select(api_key_hash=api_key_hash)

        if not endpoint:
            logger.warning(
                "endpoint_auth_invalid_key",
                key_hash_prefix=api_key_hash[:8],
            )
            return None

        # Constant-time comparison
        if not hmac.compare_digest(endpoint.api_key_hash, api_key_hash):
            logger.warning(
                "endpoint_auth_digest_mismatch",
                endpoint_id=endpoint.id,
                tenant=endpoint.tenant,
            )
            return None

        # Verify endpoint is enabled
        if not endpoint.enabled:
            logger.warning(
                "endpoint_auth_disabled",
                endpoint_id=endpoint.id,
                tenant=endpoint.tenant,
            )
            return None

        endpoint_dict = {
            "id": endpoint.id,
            "tenant": endpoint.tenant,
            "region": endpoint.region,
            "name": endpoint.name,
            "engine_url": endpoint.engine_url,
            "target": endpoint.target,
            "api_key_hash": endpoint.api_key_hash,
            "enabled": endpoint.enabled,
            "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
            "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
        }

        logger.info(
            "endpoint_auth_success",
            endpoint_id=endpoint.id,
            tenant=endpoint.tenant,
        )

        return (endpoint_dict, endpoint.tenant)

    except Exception as e:
        logger.error("endpoint_auth_error", error=str(e))
        return None
