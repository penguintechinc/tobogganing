"""Enrollment secret management using penguin-dal."""
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
class EnrollmentSecret:
    """Enrollment secret data structure."""

    id: str
    tenant: str
    org_unit_id: str | None
    secret_hash: str
    expires_at: datetime | None
    created_at: datetime
    created_by: str | None


class EnrollmentManager:
    """Manages enrollment secrets for device onboarding using penguin-dal."""

    def __init__(self, db: object, tenant_id: str) -> None:
        """Initialize EnrollmentManager.

        Args:
            db: penguin-dal DAL instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the EnrollmentManager."""
        try:
            logger.info("EnrollmentManager initialized", tenant=self.tenant_id)
        except Exception as e:
            logger.error("Failed to initialize EnrollmentManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the EnrollmentManager."""
        logger.info("EnrollmentManager shutdown complete")

    async def create_secret(
        self, org_unit_id: str | None, expires_at: datetime | None, created_by: str | None
    ) -> tuple[EnrollmentSecret, str]:
        """Create an enrollment secret.

        Args:
            org_unit_id: Optional OU ID for this secret
            expires_at: Optional expiration datetime
            created_by: User ID who created the secret

        Returns:
            Tuple of (EnrollmentSecret object, unencrypted raw secret)
        """
        raw_secret = secrets.token_urlsafe(32)
        secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

        async with self._lock:
            secret_obj = await asyncio.to_thread(
                self.db.device_enrollment_secrets.create,
                tenant=self.tenant_id,
                org_unit_id=org_unit_id,
                secret_hash=secret_hash,
                expires_at=expires_at,
                created_by=created_by,
            )

            logger.info(
                "enrollment_secret_created",
                secret_id=secret_obj.id,
                org_unit_id=org_unit_id,
                tenant=self.tenant_id,
            )

            return (
                EnrollmentSecret(
                    id=secret_obj.id,
                    tenant=secret_obj.tenant,
                    org_unit_id=secret_obj.org_unit_id,
                    secret_hash=secret_obj.secret_hash,
                    expires_at=secret_obj.expires_at,
                    created_at=secret_obj.created_at,
                    created_by=secret_obj.created_by,
                ),
                raw_secret,
            )

    async def get_secret(self, secret_id: str) -> EnrollmentSecret | None:
        """Get an enrollment secret by ID.

        Args:
            secret_id: Secret identifier

        Returns:
            EnrollmentSecret or None if not found
        """
        secret_obj = await asyncio.to_thread(
            self.db.device_enrollment_secrets.select,
            id=secret_id,
            tenant=self.tenant_id,
        )
        if not secret_obj:
            return None

        return EnrollmentSecret(
            id=secret_obj.id,
            tenant=secret_obj.tenant,
            org_unit_id=secret_obj.org_unit_id,
            secret_hash=secret_obj.secret_hash,
            expires_at=secret_obj.expires_at,
            created_at=secret_obj.created_at,
            created_by=secret_obj.created_by,
        )

    async def list_secrets(self, limit: int = 100, offset: int = 0) -> list[EnrollmentSecret]:
        """List enrollment secrets for the tenant.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of EnrollmentSecret objects
        """
        secrets_list = await asyncio.to_thread(
            self.db.device_enrollment_secrets.select_list,
            tenant=self.tenant_id,
            limitby=(offset, offset + limit),
        )

        return [
            EnrollmentSecret(
                id=s.id,
                tenant=s.tenant,
                org_unit_id=s.org_unit_id,
                secret_hash=s.secret_hash,
                expires_at=s.expires_at,
                created_at=s.created_at,
                created_by=s.created_by,
            )
            for s in (secrets_list if secrets_list else [])
        ]

    async def delete_secret(self, secret_id: str) -> bool:
        """Delete an enrollment secret.

        Args:
            secret_id: Secret identifier

        Returns:
            True if successful, False if not found
        """
        existing = await self.get_secret(secret_id)
        if not existing:
            return False

        async with self._lock:
            await asyncio.to_thread(
                self.db.device_enrollment_secrets.delete,
                id=secret_id,
                tenant=self.tenant_id,
            )

            logger.info(
                "enrollment_secret_deleted",
                secret_id=secret_id,
                tenant=self.tenant_id,
            )

        return True

    async def verify_secret(self, raw_secret: str) -> str | None:
        """Verify an enrollment secret and return org_unit_id if valid.

        Args:
            raw_secret: Unencrypted enrollment secret

        Returns:
            org_unit_id if secret is valid and not expired, None otherwise
        """
        try:
            secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

            # Query for this secret
            secret_obj = await asyncio.to_thread(
                self.db.device_enrollment_secrets.select,
                tenant=self.tenant_id,
                secret_hash=secret_hash,
            )

            if not secret_obj:
                logger.warning(
                    "secret_verification_failed_not_found",
                    tenant=self.tenant_id,
                )
                return None

            # Constant-time comparison
            if not hmac.compare_digest(secret_obj.secret_hash, secret_hash):
                logger.warning(
                    "secret_verification_failed_hash_mismatch",
                    secret_id=secret_obj.id,
                    tenant=self.tenant_id,
                )
                return None

            # Check expiration
            if secret_obj.expires_at is not None:
                now = datetime.now(timezone.utc)
                if secret_obj.expires_at < now:
                    logger.warning(
                        "secret_verification_failed_expired",
                        secret_id=secret_obj.id,
                        expires_at=secret_obj.expires_at,
                        tenant=self.tenant_id,
                    )
                    return None

            logger.info(
                "secret_verified",
                secret_id=secret_obj.id,
                org_unit_id=secret_obj.org_unit_id,
                tenant=self.tenant_id,
            )

            return secret_obj.org_unit_id
        except Exception as e:
            logger.error(
                "secret_verification_error_fail_closed",
                error=str(e),
                tenant=self.tenant_id,
            )
            return None
