"""Cluster-to-cluster endpoint management using penguin-dal."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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

    def __init__(self, db: Any, tenant: str) -> None:
        """Initialize EndpointManager.

        Args:
            db: penguin-dal AsyncDB instance
            tenant: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant = tenant

    async def list_endpoints(self, enabled_only: bool = False) -> list[dict[str, object]]:
        """List all endpoints for this tenant.

        Args:
            enabled_only: If True, only return enabled endpoints

        Returns:
            List of endpoint dicts, newest first
        """
        if enabled_only:
            rowset = await self.db(
                (self.db.c2c_endpoints.tenant == self.tenant)
                & (self.db.c2c_endpoints.enabled == True)  # noqa: E712
            ).select()
        else:
            rowset = await self.db(self.db.c2c_endpoints.tenant == self.tenant).select()

        if not rowset:
            return []

        return [self._endpoint_to_dict(e) for e in rowset]

    async def get_endpoint(self, endpoint_id: str) -> dict[str, object] | None:
        """Get an endpoint by ID.

        Args:
            endpoint_id: Endpoint ID

        Returns:
            Endpoint dict or None if not found or belongs to different tenant
        """
        rowset = await self.db(
            (self.db.c2c_endpoints.id == endpoint_id)
            & (self.db.c2c_endpoints.tenant == self.tenant)
        ).select()

        endpoint = rowset.first()
        if not endpoint:
            return None

        return self._endpoint_to_dict(endpoint)

    async def create_endpoint(
        self,
        region: str,
        name: str,
        engine_url: str,
        target: str,
        api_key: str | None = None,
        visibility: str = "private",
        provider: str | None = None,
    ) -> tuple[dict[str, object], str | None]:
        """Create a new endpoint.

        Args:
            region: Region name
            name: Endpoint name
            engine_url: Base URL of the test engine
            target: Target host that other nodes test against
            api_key: Optional API key; if None, one is generated
            visibility: Endpoint visibility ('private' or 'public'), default 'private'
            provider: Optional cloud provider name

        Returns:
            Tuple of (endpoint_dict, raw_api_key). If api_key provided,
            raw_api_key is None. If generated, raw_api_key is returned once.

        Raises:
            ValueError: If endpoint with same (tenant, region, name) already exists,
            or if api_key is provided but blank, or if visibility is invalid
        """
        # Validate visibility
        if visibility not in ("private", "public"):
            raise ValueError(f"visibility must be 'private' or 'public', got {visibility}")

        # Reject empty/blank api_key (finding #4)
        if api_key is not None and not api_key.strip():
            raise ValueError("api_key cannot be empty or blank")

        # Check for duplicate
        rowset = await self.db(
            (self.db.c2c_endpoints.tenant == self.tenant)
            & (self.db.c2c_endpoints.region == region)
            & (self.db.c2c_endpoints.name == name)
        ).select()

        if rowset.first():
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
        endpoint_id = await self.db.c2c_endpoints.async_insert(
            id=secrets.token_urlsafe(16),
            tenant=self.tenant,
            region=region,
            name=name,
            engine_url=engine_url,
            target=target,
            api_key_hash=api_key_hash,
            enabled=True,
            visibility=visibility,
            provider=provider,
            health_status="unknown",
            last_health_check=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Re-fetch to get all fields
        rowset = await self.db(
            self.db.c2c_endpoints.id == endpoint_id,
        ).select()
        endpoint = rowset.first()

        logger.info(
            "endpoint_created",
            endpoint_id=endpoint_id,
            region=region,
            name=name,
            tenant=self.tenant,
        )

        endpoint_dict = self._endpoint_to_dict(endpoint)
        return (endpoint_dict, return_key)

    def _endpoint_to_dict(self, endpoint: Any) -> dict[str, object]:
        """Convert endpoint row to dict with all fields.

        Args:
            endpoint: Endpoint row from database

        Returns:
            Dictionary representation of endpoint
        """
        return {
            "id": endpoint.id,
            "tenant": endpoint.tenant,
            "region": endpoint.region,
            "name": endpoint.name,
            "engine_url": endpoint.engine_url,
            "target": endpoint.target,
            "api_key_hash": endpoint.api_key_hash,
            "enabled": endpoint.enabled,
            "visibility": endpoint.visibility,
            "provider": endpoint.provider,
            "health_status": endpoint.health_status,
            "last_health_check": (
                endpoint.last_health_check.isoformat()
                if endpoint.last_health_check
                else None
            ),
            "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
            "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
        }

    async def update_endpoint(self, endpoint_id: str, **fields: object) -> dict[str, object] | None:
        """Update an endpoint.

        Args:
            endpoint_id: Endpoint ID
            **fields: Fields to update (name, engine_url, target, region, enabled, visibility)

        Returns:
            Updated endpoint dict or None if not found
        """
        # Verify ownership by tenant
        rowset = await self.db(
            (self.db.c2c_endpoints.id == endpoint_id)
            & (self.db.c2c_endpoints.tenant == self.tenant)
        ).select()

        if not rowset.first():
            return None

        # Filter to allowed fields
        allowed = {"name", "engine_url", "target", "region", "enabled", "visibility", "provider"}
        update_data = {k: v for k, v in fields.items() if k in allowed}

        # Validate visibility if provided
        if "visibility" in update_data and update_data["visibility"] not in ("private", "public"):
            raise ValueError(
                f"visibility must be 'private' or 'public', got {update_data['visibility']}"
            )

        if not update_data:
            return await self.get_endpoint(endpoint_id)

        # Update with current timestamp
        update_data["updated_at"] = datetime.now(timezone.utc)
        await self.db(
            (self.db.c2c_endpoints.id == endpoint_id)
            & (self.db.c2c_endpoints.tenant == self.tenant)
        ).update(**update_data)

        logger.info(
            "endpoint_updated",
            endpoint_id=endpoint_id,
            tenant=self.tenant,
        )

        return await self.get_endpoint(endpoint_id)

    async def list_regions(self, tenant: str) -> list[dict[str, object]]:
        """Aggregate regions over tenant's endpoints and all public endpoints.

        Returns aggregate data including node count, healthy count, and providers
        for each region. Includes own tenant's all endpoints and ALL tenants'
        public endpoints.

        Args:
            tenant: Tenant identifier

        Returns:
            List of region aggregates: {region, node_count, healthy_count, providers}
        """
        # Get own tenant's all endpoints
        own_rowset = await self.db(self.db.c2c_endpoints.tenant == tenant).select()

        # Get all public endpoints from any tenant
        public_rowset = await self.db(
            self.db.c2c_endpoints.visibility == "public"
        ).select()

        # Combine and aggregate by region
        endpoints = list(own_rowset) if own_rowset else []
        endpoints += list(public_rowset) if public_rowset else []

        region_data: dict[str, dict[str, Any]] = {}
        for ep in endpoints:
            region = ep.region
            if region not in region_data:
                region_data[region] = {
                    "region": region,
                    "node_count": 0,
                    "healthy_count": 0,
                    "providers": set(),
                }

            region_data[region]["node_count"] += 1
            if ep.health_status == "healthy":
                region_data[region]["healthy_count"] += 1
            if ep.provider:
                region_data[region]["providers"].add(ep.provider)

        # Convert to list with providers as list
        result = [
            {
                "region": data["region"],
                "node_count": data["node_count"],
                "healthy_count": data["healthy_count"],
                "providers": sorted(list(data["providers"])),
            }
            for data in region_data.values()
        ]

        return sorted(result, key=lambda r: r["region"])

    async def visible_endpoints(
        self, tenant: str, region: str | None = None
    ) -> list[dict[str, object]]:
        """List endpoints visible to a tenant (own + foreign public, optionally filtered by region).

        Returns own tenant's all endpoints + all public endpoints from other tenants.
        Foreign public endpoints are returned WITHOUT engine_url, target, or api_key_hash.

        Args:
            tenant: Tenant identifier
            region: Optional region filter

        Returns:
            List of visible endpoint dicts (foreign public endpoints redacted)
        """
        # Get own tenant's all endpoints
        if region:
            own_rowset = await self.db(
                (self.db.c2c_endpoints.tenant == tenant) & (self.db.c2c_endpoints.region == region)
            ).select()
        else:
            own_rowset = await self.db(self.db.c2c_endpoints.tenant == tenant).select()

        # Get all public endpoints from any tenant
        if region:
            public_rowset = await self.db(
                (self.db.c2c_endpoints.visibility == "public")
                & (self.db.c2c_endpoints.region == region)
            ).select()
        else:
            public_rowset = await self.db(
                self.db.c2c_endpoints.visibility == "public"
            ).select()

        result = []

        # Add own endpoints (full data)
        if own_rowset:
            for ep in own_rowset:
                result.append(self._endpoint_to_dict(ep))

        # Add foreign public endpoints (redacted)
        if public_rowset:
            for ep in public_rowset:
                if ep.tenant != tenant:  # Foreign
                    # Redact sensitive fields
                    redacted = self._endpoint_to_dict(ep)
                    del redacted["engine_url"]
                    del redacted["target"]
                    del redacted["api_key_hash"]
                    result.append(redacted)

        return result

    async def delete_endpoint(self, endpoint_id: str) -> bool:
        """Delete an endpoint.

        Args:
            endpoint_id: Endpoint ID

        Returns:
            True if deleted, False if not found
        """
        rowset = await self.db(
            (self.db.c2c_endpoints.id == endpoint_id)
            & (self.db.c2c_endpoints.tenant == self.tenant)
        ).select()

        if not rowset.first():
            return False

        await self.db(
            (self.db.c2c_endpoints.id == endpoint_id)
            & (self.db.c2c_endpoints.tenant == self.tenant)
        ).delete()

        logger.info(
            "endpoint_deleted",
            endpoint_id=endpoint_id,
            tenant=self.tenant,
        )

        return True


async def authenticate_node_global(
    db: Any, api_key: str
) -> tuple[dict[str, object], str] | None:
    """Authenticate a node globally by API key without trusting tenant.

    Searches across all tenants, validates the key hash with constant-time
    comparison, and returns the endpoint and its tenant.

    Args:
        db: penguin-dal AsyncDB instance
        api_key: Unencrypted API key from request

    Returns:
        Tuple of (endpoint_dict, tenant) if authenticated, None otherwise
    """
    try:
        # Reject empty/blank api_key (finding #4)
        if not api_key or not api_key.strip():
            logger.warning("endpoint_auth_empty_key")
            return None

        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Query c2c_endpoints globally (no tenant filter)
        rowset = await db(
            db.c2c_endpoints.api_key_hash == api_key_hash,
        ).select()

        endpoint = rowset.first()
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

        # Build endpoint dict with all fields
        endpoint_dict: dict[str, object] = {
            "id": endpoint.id,
            "tenant": endpoint.tenant,
            "region": endpoint.region,
            "name": endpoint.name,
            "engine_url": endpoint.engine_url,
            "target": endpoint.target,
            "api_key_hash": endpoint.api_key_hash,
            "enabled": endpoint.enabled,
            "visibility": endpoint.visibility,
            "provider": endpoint.provider,
            "health_status": endpoint.health_status,
            "last_health_check": (
                endpoint.last_health_check.isoformat()
                if endpoint.last_health_check
                else None
            ),
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
