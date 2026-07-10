"""Device management using penguin-dal."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

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
        self._lock = asyncio.Lock()

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
            device_info: Device data dictionary (name, serial, hostname, os, org_unit_id, device_metadata)

        Returns:
            Tuple of (Device object, unencrypted api_key)
        """
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        async with self._lock:
            device_obj = await asyncio.to_thread(
                self.db.devices.create,
                tenant=self.tenant_id,
                org_unit_id=device_info.get("org_unit_id"),
                name=device_info.get("name"),
                serial=device_info.get("serial"),
                hostname=device_info.get("hostname"),
                os=device_info.get("os"),
                status="online",
                device_metadata=device_info.get("device_metadata", {}),
            )

            # Create API key record
            await asyncio.to_thread(
                self.db.device_api_keys.create,
                tenant=self.tenant_id,
                device_id=device_obj.id,
                api_key_hash=api_key_hash,
            )

            logger.info(
                "device_registered",
                device_id=device_obj.id,
                serial=device_obj.serial,
                tenant=self.tenant_id,
            )

            return (
                Device(
                    id=device_obj.id,
                    tenant=device_obj.tenant,
                    org_unit_id=device_obj.org_unit_id,
                    name=device_obj.name,
                    serial=device_obj.serial,
                    hostname=device_obj.hostname,
                    os=device_obj.os,
                    status=device_obj.status,
                    last_heartbeat=device_obj.last_heartbeat,
                    device_metadata=device_obj.device_metadata,
                    created_at=device_obj.created_at,
                    updated_at=device_obj.updated_at,
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
        try:
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

            # Query device_api_keys for this hash
            key_obj = await asyncio.to_thread(
                self.db.device_api_keys.select,
                tenant=self.tenant_id,
                api_key_hash=api_key_hash,
            )

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
            device_obj = await asyncio.to_thread(
                self.db.devices.select,
                id=key_obj.device_id,
                tenant=self.tenant_id,
            )

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
                device_metadata=device_obj.device_metadata,
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
        device_obj = await asyncio.to_thread(
            self.db.devices.select,
            id=device_id,
            tenant=self.tenant_id,
        )
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
            device_metadata=device_obj.device_metadata,
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
            devices = await asyncio.to_thread(
                self.db.devices.select_list,
                tenant=self.tenant_id,
                org_unit_id=org_unit_id,
                limitby=(offset, offset + limit),
            )
        else:
            devices = await asyncio.to_thread(
                self.db.devices.select_list,
                tenant=self.tenant_id,
                limitby=(offset, offset + limit),
            )

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
                device_metadata=d.device_metadata,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in devices
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

        async with self._lock:
            await asyncio.to_thread(
                self.db.devices.update,
                id=device_id,
                tenant=self.tenant_id,
                status=status,
                updated_at=datetime.now(timezone.utc),
            )

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

        async with self._lock:
            now = datetime.now(timezone.utc)
            await asyncio.to_thread(
                self.db.devices.update,
                id=device_id,
                tenant=self.tenant_id,
                last_heartbeat=now,
                status="online",
                updated_at=now,
            )

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

        async with self._lock:
            # Delete API keys first
            await asyncio.to_thread(
                self.db.device_api_keys.delete,
                device_id=device_id,
                tenant=self.tenant_id,
            )

            # Delete device
            await asyncio.to_thread(
                self.db.devices.delete,
                id=device_id,
                tenant=self.tenant_id,
            )

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
        devices = await asyncio.to_thread(
            self.db.devices.select_list,
            tenant=self.tenant_id,
            status="online",
        )
        return len(devices) if devices else 0
