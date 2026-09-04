"""Device management using penguin-dal."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

logger = structlog.get_logger()


@dataclass(slots=True)
class Device:
    """Device data structure."""

    id: str
    tenant: str
    org_unit_id: str | None
    name: str
    serial: str
    hostname: str | None
    os: str | None
    status: str
    last_heartbeat: datetime | None
    device_metadata: dict | None
    created_at: datetime
    updated_at: datetime


class DeviceManager:
    """Manages device registration and authentication using penguin-dal."""

    def __init__(self, db: object, tenant_id: str) -> None:
        """Initialize DeviceManager.

        Args:
            db: penguin-dal DAL instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id

    async def initialize(self) -> None:
        """Initialize the DeviceManager."""
        try:
            logger.info("DeviceManager initialized", tenant=self.tenant_id)
        except Exception as e:
            logger.error("Failed to initialize DeviceManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the DeviceManager."""
        logger.info("DeviceManager shutdown complete")

    async def register_device(self, device_info: dict) -> tuple[Device, str]:
        """Register a new device and return (device, api_key).

        Args:
            device_info: Device data dictionary with keys name, serial, hostname, os,
                org_unit_id, device_metadata

        Returns:
            Tuple of (Device object, unencrypted api_key)
        """
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        device_id = str(uuid4())
        now = datetime.now(timezone.utc)

        await self.db.devices.async_insert(
            id=device_id,
            tenant=self.tenant_id,
            org_unit_id=device_info.get("org_unit_id"),
            name=device_info.get("name"),
            serial=device_info.get("serial"),
            hostname=device_info.get("hostname"),
            os=device_info.get("os"),
            status="online",
            metadata=device_info.get("device_metadata"),
            created_at=now,
            updated_at=now,
        )

        # Create API key record
        key_id = str(uuid4())
        await self.db.device_api_keys.async_insert(
            id=key_id,
            tenant=self.tenant_id,
            device_id=device_id,
            api_key_hash=api_key_hash,
            created_at=now,
        )

        logger.info(
            "device_registered",
            device_id=device_id,
            serial=device_info.get("serial"),
            tenant=self.tenant_id,
        )

        return (
            Device(
                id=device_id,
                tenant=self.tenant_id,
                org_unit_id=device_info.get("org_unit_id"),
                name=device_info.get("name"),
                serial=device_info.get("serial"),
                hostname=device_info.get("hostname"),
                os=device_info.get("os"),
                status="online",
                last_heartbeat=None,
                device_metadata=device_info.get("device_metadata"),
                created_at=now,
                updated_at=now,
            ),
            api_key,
        )

    async def authenticate_device(self, api_key: str) -> Device | None:
        """Authenticate a device by API key.

        Args:
            api_key: Unencrypted API key

        Returns:
            Device if authenticated and not revoked, None otherwise
        """
        if not api_key or not api_key.strip():
            logger.warning(
                "authentication_rejected_empty_key",
                tenant=self.tenant_id,
            )
            return None

        try:
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

            # Query device_api_keys for this hash
            key_rowset = await self.db(
                (
                    (self.db.device_api_keys.api_key_hash == api_key_hash)
                    & (self.db.device_api_keys.tenant == self.tenant_id)
                )
            ).select()
            key_obj = key_rowset.first()

            if not key_obj:
                return None

            # Reject revoked keys
            if key_obj.revoked_at is not None:
                logger.warning(
                    "authentication_rejected_revoked_key",
                    device_id=key_obj.device_id,
                    tenant=self.tenant_id,
                )
                return None

            # Constant-time comparison
            if not hmac.compare_digest(key_obj.api_key_hash, api_key_hash):
                logger.warning(
                    "authentication_rejected_hash_mismatch",
                    device_id=key_obj.device_id,
                    tenant=self.tenant_id,
                )
                return None

            # Get device record
            device_rowset = await self.db(
                (
                    (self.db.devices.id == key_obj.device_id)
                    & (self.db.devices.tenant == self.tenant_id)
                )
            ).select()
            device_obj = device_rowset.first()

            if not device_obj:
                return None

            return Device(
                id=device_obj.id,
                tenant=device_obj.tenant,
                org_unit_id=device_obj.org_unit_id,
                name=device_obj.name,
                serial=device_obj.serial,
                hostname=device_obj.hostname,
                os=device_obj.os,
                status=device_obj.status,
                last_heartbeat=device_obj.last_heartbeat,
                device_metadata=device_obj.metadata,
                created_at=device_obj.created_at,
                updated_at=device_obj.updated_at,
            )
        except Exception as e:
            logger.error(
                "authentication_error_fail_closed",
                error=str(e),
                tenant=self.tenant_id,
            )
            return None

    async def get_device(self, device_id: str) -> Device | None:
        """Get a device by ID.

        Args:
            device_id: Device identifier

        Returns:
            Device or None if not found
        """
        device_rowset = await self.db(
            (self.db.devices.id == device_id) & (self.db.devices.tenant == self.tenant_id)
        ).select()
        device_obj = device_rowset.first()

        if not device_obj:
            return None

        return Device(
            id=device_obj.id,
            tenant=device_obj.tenant,
            org_unit_id=device_obj.org_unit_id,
            name=device_obj.name,
            serial=device_obj.serial,
            hostname=device_obj.hostname,
            os=device_obj.os,
            status=device_obj.status,
            last_heartbeat=device_obj.last_heartbeat,
            device_metadata=device_obj.metadata,
            created_at=device_obj.created_at,
            updated_at=device_obj.updated_at,
        )

    async def list_devices(
        self, org_unit_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Device]:
        """List devices for the tenant.

        Args:
            org_unit_id: Optional OU ID for filtering
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of Device objects
        """
        if org_unit_id is not None:
            devices_rowset = await self.db(
                (
                    (self.db.devices.tenant == self.tenant_id)
                    & (self.db.devices.org_unit_id == org_unit_id)
                )
            ).select(limitby=(offset, offset + limit))
        else:
            devices_rowset = await self.db(
                self.db.devices.tenant == self.tenant_id
            ).select(limitby=(offset, offset + limit))

        return [
            Device(
                id=d.id,
                tenant=d.tenant,
                org_unit_id=d.org_unit_id,
                name=d.name,
                serial=d.serial,
                hostname=d.hostname,
                os=d.os,
                status=d.status,
                last_heartbeat=d.last_heartbeat,
                device_metadata=d.metadata,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in devices_rowset
        ]

    async def update_status(self, device_id: str, status: str) -> Device | None:
        """Update device status.

        Args:
            device_id: Device identifier
            status: New status

        Returns:
            Updated Device or None if not found
        """
        existing = await self.get_device(device_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc)
        await self.db(
            (self.db.devices.id == device_id) & (self.db.devices.tenant == self.tenant_id)
        ).update(status=status, updated_at=now)

        logger.info(
            "device_status_updated",
            device_id=device_id,
            status=status,
            tenant=self.tenant_id,
        )

        return await self.get_device(device_id)

    async def heartbeat(self, device_id: str) -> Device | None:
        """Record device heartbeat.

        Args:
            device_id: Device identifier

        Returns:
            Updated Device or None if not found
        """
        existing = await self.get_device(device_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc)
        await self.db(
            (self.db.devices.id == device_id) & (self.db.devices.tenant == self.tenant_id)
        ).update(last_heartbeat=now, status="online", updated_at=now)

        logger.info(
            "device_heartbeat",
            device_id=device_id,
            tenant=self.tenant_id,
        )

        return await self.get_device(device_id)

    async def remove_device(self, device_id: str) -> bool:
        """Remove a device.

        Args:
            device_id: Device identifier

        Returns:
            True if successful, False if not found
        """
        existing = await self.get_device(device_id)
        if not existing:
            return False

        # Delete API keys first
        await self.db(
            (
                (self.db.device_api_keys.device_id == device_id)
                & (self.db.device_api_keys.tenant == self.tenant_id)
            )
        ).delete()

        # Delete device
        await self.db(
            (self.db.devices.id == device_id) & (self.db.devices.tenant == self.tenant_id)
        ).delete()

        logger.info(
            "device_removed",
            device_id=device_id,
            tenant=self.tenant_id,
        )

        return True

    async def count_active_devices(self) -> int:
        """Count active devices for the tenant.

        Returns:
            Number of active devices
        """
        count = await self.db(
            (self.db.devices.tenant == self.tenant_id)
            & (self.db.devices.status == "online")
        ).count()
        return count
