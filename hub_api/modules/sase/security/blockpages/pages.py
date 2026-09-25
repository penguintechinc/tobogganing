"""Manager for SASE block pages with versioning and tenant scoping."""
from __future__ import annotations

from datetime import datetime
from typing import Any
import structlog

from hub_api.modules.sase.security.blockpages.models import BlockPage, PageStatus

logger = structlog.get_logger()


class BlockPageManager:
    """Manages block pages with CRUD, versioning, and tenant-scoped queries."""

    def __init__(self, db: Any) -> None:
        """Initialize BlockPageManager with a DAL instance.

        Args:
            db: penguin-dal DAL instance for database operations.
        """
        self.db = db

    async def create(self, tenant: str, name: str, markdown: str, created_by: str) -> BlockPage:
        """Create a new draft block page.

        Args:
            tenant: Tenant ID (from authenticated claims).
            name: Display name of the page.
            markdown: Markdown content.
            created_by: User ID who created the page.

        Returns:
            Created BlockPage.

        Raises:
            Exception: If insert fails.
        """
        import uuid

        page_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self.db.block_pages.async_insert(
            id=page_id,
            tenant=tenant,
            name=name,
            markdown=markdown,
            status=PageStatus.draft.value,
            version=1,
            created_by=created_by,
            updated_by=None,
            created_at=now,
            updated_at=now,
        )

        logger.info("block_page_created", page_id=page_id, tenant=tenant, name=name)

        return BlockPage(
            id=page_id,
            tenant=tenant,
            name=name,
            markdown=markdown,
            status=PageStatus.draft,
            version=1,
            created_by=created_by,
            updated_by=None,
            created_at=now,
            updated_at=now,
        )

    async def update(self, tenant: str, page_id: str, markdown: str, updated_by: str) -> BlockPage | None:
        """Update a block page's markdown (draft or live).

        Args:
            tenant: Tenant ID (from authenticated claims).
            page_id: ID of the page to update.
            markdown: New markdown content.
            updated_by: User ID who updated the page.

        Returns:
            Updated BlockPage or None if not found.

        Raises:
            Exception: If update fails.
        """
        now = datetime.utcnow()

        # Verify ownership (tenant scoped)
        rowset = await self.db(
            (self.db.block_pages.id == page_id) & (self.db.block_pages.tenant == tenant)
        ).select()

        if not rowset:
            return None

        row = rowset[0]

        await self.db(
            (self.db.block_pages.id == page_id) & (self.db.block_pages.tenant == tenant)
        ).update(
            markdown=markdown,
            updated_by=updated_by,
            updated_at=now,
        )

        logger.info("block_page_updated", page_id=page_id, tenant=tenant, updated_by=updated_by)

        return BlockPage(
            id=row.id,
            tenant=row.tenant,
            name=row.name,
            markdown=markdown,
            status=PageStatus(row.status),
            version=row.version,
            created_by=row.created_by,
            updated_by=updated_by,
            created_at=row.created_at,
            updated_at=now,
        )

    async def publish(self, tenant: str, page_id: str) -> BlockPage | None:
        """Publish a draft page to live (bumps version).

        Args:
            tenant: Tenant ID (from authenticated claims).
            page_id: ID of the page to publish.

        Returns:
            Published BlockPage or None if not found.

        Raises:
            Exception: If update fails.
        """
        # Verify ownership (tenant scoped)
        rowset = await self.db(
            (self.db.block_pages.id == page_id) & (self.db.block_pages.tenant == tenant)
        ).select()

        if not rowset:
            return None

        row = rowset[0]
        now = datetime.utcnow()
        new_version = row.version + 1

        await self.db(
            (self.db.block_pages.id == page_id) & (self.db.block_pages.tenant == tenant)
        ).update(
            status=PageStatus.live.value,
            version=new_version,
            updated_at=now,
        )

        logger.info("block_page_published", page_id=page_id, tenant=tenant, version=new_version)

        return BlockPage(
            id=row.id,
            tenant=row.tenant,
            name=row.name,
            markdown=row.markdown,
            status=PageStatus.live,
            version=new_version,
            created_by=row.created_by,
            updated_by=row.updated_by,
            created_at=row.created_at,
            updated_at=now,
        )

    async def revert(self, tenant: str, page_id: str, version: int) -> BlockPage | None:
        """Revert to a previous version (currently just supports single live version).

        Args:
            tenant: Tenant ID (from authenticated claims).
            page_id: ID of the page to revert.
            version: Version number to revert to (not used in current simple implementation).

        Returns:
            Reverted BlockPage or None if not found.

        Raises:
            Exception: If update fails.
        """
        # Simple implementation: revert to draft status
        rowset = await self.db(
            (self.db.block_pages.id == page_id) & (self.db.block_pages.tenant == tenant)
        ).select()

        if not rowset:
            return None

        row = rowset[0]
        now = datetime.utcnow()

        await self.db(
            (self.db.block_pages.id == page_id) & (self.db.block_pages.tenant == tenant)
        ).update(
            status=PageStatus.draft.value,
            updated_at=now,
        )

        logger.info("block_page_reverted", page_id=page_id, tenant=tenant, version=version)

        return BlockPage(
            id=row.id,
            tenant=row.tenant,
            name=row.name,
            markdown=row.markdown,
            status=PageStatus.draft,
            version=row.version,
            created_by=row.created_by,
            updated_by=row.updated_by,
            created_at=row.created_at,
            updated_at=now,
        )

    async def get_live(self, tenant: str, name: str) -> BlockPage | None:
        """Get the live version of a page by name.

        Args:
            tenant: Tenant ID (from authenticated claims).
            name: Page name.

        Returns:
            BlockPage or None if not found or not live.
        """
        rowset = await self.db(
            (self.db.block_pages.tenant == tenant)
            & (self.db.block_pages.name == name)
            & (self.db.block_pages.status == PageStatus.live.value)
        ).select()

        if not rowset:
            return None

        row = rowset[0]

        return BlockPage(
            id=row.id,
            tenant=row.tenant,
            name=row.name,
            markdown=row.markdown,
            status=PageStatus.live,
            version=row.version,
            created_by=row.created_by,
            updated_by=row.updated_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def list_pages(self, tenant: str) -> list[BlockPage]:
        """List all pages for a tenant.

        Args:
            tenant: Tenant ID (from authenticated claims).

        Returns:
            List of BlockPage objects.
        """
        try:
            rowset = await self.db(
                self.db.block_pages.tenant == tenant,
            ).select(orderby=[self.db.block_pages.created_at])

            pages: list[BlockPage] = []
            for row in rowset:
                page = BlockPage(
                    id=row.id,
                    tenant=row.tenant,
                    name=row.name,
                    markdown=row.markdown,
                    status=PageStatus(row.status),
                    version=row.version,
                    created_by=row.created_by,
                    updated_by=row.updated_by,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                pages.append(page)

            return pages

        except Exception as e:
            logger.error("failed_to_list_pages", tenant=tenant, error=str(e))
            return []

    async def get_by_id(self, tenant: str, page_id: str) -> BlockPage | None:
        """Get a page by ID (tenant-scoped).

        Args:
            tenant: Tenant ID (from authenticated claims).
            page_id: ID of the page.

        Returns:
            BlockPage or None if not found.
        """
        rowset = await self.db(
            (self.db.block_pages.id == page_id) & (self.db.block_pages.tenant == tenant)
        ).select()

        if not rowset:
            return None

        row = rowset[0]

        return BlockPage(
            id=row.id,
            tenant=row.tenant,
            name=row.name,
            markdown=row.markdown,
            status=PageStatus(row.status),
            version=row.version,
            created_by=row.created_by,
            updated_by=row.updated_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
