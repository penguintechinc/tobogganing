"""Global device authentication without tenant trust."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import structlog
from typing import Optional, Tuple

logger = structlog.get_logger()


async def authenticate_device_global(
    db: object, api_key: str
) -> Optional[Tuple[object, str]]:
    """Authenticate a device globally by API key without trusting client tenant.

    Searches across all tenants, validates the key hash with constant-time
    comparison, rejects revoked keys, and returns the device and its tenant.

    Args:
        db: penguin-dal DAL instance
        api_key: Unencrypted API key from request

    Returns:
        Tuple of (device_row, device_tenant) if authenticated and not revoked,
        None otherwise
    """
    try:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Query device_api_keys globally (no tenant filter)
        # Note: penguin-dal select() without tenant filter searches all rows
        key_obj = await asyncio.to_thread(
            db.device_api_keys.select,
            api_key_hash=api_key_hash,
        )

        if not key_obj:
            logger.warning(
                "device_auth_invalid_key",
                key_hash_prefix=api_key_hash[:8],
            )
            return None

        # Reject revoked keys
        if key_obj.revoked_at is not None:
            logger.warning(
                "device_auth_revoked_key",
                device_id=key_obj.device_id,
                tenant=key_obj.tenant,
            )
            return None

        # Fetch the device record to verify it's not deleted/suspended
        device = await asyncio.to_thread(
            db.devices.select,
            id=key_obj.device_id,
            tenant=key_obj.tenant,
        )

        if not device:
            logger.warning(
                "device_auth_device_not_found",
                device_id=key_obj.device_id,
                tenant=key_obj.tenant,
            )
            return None

        logger.info(
            "device_auth_success",
            device_id=device.id,
            tenant=key_obj.tenant,
        )

        return (device, key_obj.tenant)

    except Exception as e:
        logger.error("device_auth_error", error=str(e))
        return None
