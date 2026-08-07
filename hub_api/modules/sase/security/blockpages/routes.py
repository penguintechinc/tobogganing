"""Manager for SASE block routes with governance metadata and source type resolution."""
from __future__ import annotations

from datetime import datetime
from typing import Any
import structlog

from hub_api.modules.sase.security.blockpages.models import BlockRoute, RouteDest

logger = structlog.get_logger()


class BlockRouteManager:
    """Manages block routes with routing configuration and governance metadata."""

    def __init__(self, db: Any) -> None:
        """Initialize BlockRouteManager with a DAL instance.

        Args:
            db: penguin-dal DAL instance for database operations.
        """
        self.db = db

    async def set_route(
        self,
        tenant: str,
        source_type: str,
        destination_kind: RouteDest,
        page_id: str | None = None,
        external_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BlockRoute:
        """Set or update a block route for a source type.

        Args:
            tenant: Tenant ID (from authenticated claims).
            source_type: Source type identifier (e.g., 'web-category:gambling').
            destination_kind: Destination type (page or external).
            page_id: ID of the block page (if destination_kind=='page').
            external_url: External URL (if destination_kind=='external').
            metadata: Governance metadata dict (created_by, ticket, notes, expiry, etc.).

        Returns:
            Created or updated BlockRoute.

        Raises:
            Exception: If insert/update fails.
        """
        import uuid

        # Check if route already exists
        rowset = await self.db(
            (self.db.block_routes.tenant == tenant) & (self.db.block_routes.source_type == source_type)
        ).select()

        route_id = None
        if rowset:
            route_id = rowset[0].id
        else:
            route_id = str(uuid.uuid4())

        now = datetime.utcnow()
        meta = metadata or {}

        if route_id and rowset:
            # Update existing route
            await self.db(
                (self.db.block_routes.id == route_id) & (self.db.block_routes.tenant == tenant)
            ).update(
                destination_kind=destination_kind.value,
                page_id=page_id,
                external_url=external_url,
                created_by=meta.get("created_by"),
                updated_by=meta.get("updated_by"),
                ticket=meta.get("ticket"),
                notes=meta.get("notes"),
                expiry=meta.get("expiry"),
                review_date=meta.get("review_date"),
                scope=meta.get("scope"),
                risk=meta.get("risk"),
            )

            logger.info("block_route_updated", route_id=route_id, tenant=tenant, source_type=source_type)
        else:
            # Create new route
            await self.db.block_routes.async_insert(
                id=route_id,
                tenant=tenant,
                source_type=source_type,
                destination_kind=destination_kind.value,
                page_id=page_id,
                external_url=external_url,
                created_at=now,
                created_by=meta.get("created_by"),
                updated_by=meta.get("updated_by"),
                ticket=meta.get("ticket"),
                notes=meta.get("notes"),
                expiry=meta.get("expiry"),
                review_date=meta.get("review_date"),
                scope=meta.get("scope"),
                risk=meta.get("risk"),
            )

            logger.info("block_route_created", route_id=route_id, tenant=tenant, source_type=source_type)

        return BlockRoute(
            id=route_id,
            tenant=tenant,
            source_type=source_type,
            destination_kind=destination_kind,
            page_id=page_id,
            external_url=external_url,
            created_at=now,
            created_by=meta.get("created_by"),
            updated_by=meta.get("updated_by"),
            ticket=meta.get("ticket"),
            notes=meta.get("notes"),
            expiry=meta.get("expiry"),
            review_date=meta.get("review_date"),
            scope=meta.get("scope"),
            risk=meta.get("risk"),
        )

    async def get_routes(self, tenant: str) -> list[BlockRoute]:
        """Get all routes for a tenant.

        Args:
            tenant: Tenant ID (from authenticated claims).

        Returns:
            List of BlockRoute objects.
        """
        try:
            rowset = await self.db(self.db.block_routes.tenant == tenant).select()

            routes: list[BlockRoute] = []
            for row in rowset:
                route = BlockRoute(
                    id=row.id,
                    tenant=row.tenant,
                    source_type=row.source_type,
                    destination_kind=RouteDest(row.destination_kind),
                    page_id=row.page_id,
                    external_url=row.external_url,
                    created_at=row.created_at,
                    created_by=row.created_by,
                    updated_by=row.updated_by,
                    ticket=row.ticket,
                    notes=row.notes,
                    expiry=row.expiry,
                    review_date=row.review_date,
                    scope=row.scope,
                    risk=row.risk,
                )
                routes.append(route)

            return routes

        except Exception as e:
            logger.error("failed_to_get_routes", tenant=tenant, error=str(e))
            return []

    async def resolve(self, tenant: str, source_type: str) -> BlockRoute | None:
        """Resolve a block route for a given source type.

        Returns exact match for source_type, or global default if configured,
        or None if no match found.

        Args:
            tenant: Tenant ID (from authenticated claims).
            source_type: Source type to resolve.

        Returns:
            BlockRoute or None if not found.
        """
        try:
            # Try exact source type match
            rowset = await self.db(
                (self.db.block_routes.tenant == tenant) & (self.db.block_routes.source_type == source_type)
            ).select()

            if rowset:
                row = rowset[0]
                return BlockRoute(
                    id=row.id,
                    tenant=row.tenant,
                    source_type=row.source_type,
                    destination_kind=RouteDest(row.destination_kind),
                    page_id=row.page_id,
                    external_url=row.external_url,
                    created_at=row.created_at,
                    created_by=row.created_by,
                    updated_by=row.updated_by,
                    ticket=row.ticket,
                    notes=row.notes,
                    expiry=row.expiry,
                    review_date=row.review_date,
                    scope=row.scope,
                    risk=row.risk,
                )

            # Try global default
            rowset = await self.db(
                (self.db.block_routes.tenant == tenant) & (self.db.block_routes.source_type == "default")
            ).select()

            if rowset:
                row = rowset[0]
                return BlockRoute(
                    id=row.id,
                    tenant=row.tenant,
                    source_type=row.source_type,
                    destination_kind=RouteDest(row.destination_kind),
                    page_id=row.page_id,
                    external_url=row.external_url,
                    created_at=row.created_at,
                    created_by=row.created_by,
                    updated_by=row.updated_by,
                    ticket=row.ticket,
                    notes=row.notes,
                    expiry=row.expiry,
                    review_date=row.review_date,
                    scope=row.scope,
                    risk=row.risk,
                )

            return None

        except Exception as e:
            logger.error("failed_to_resolve_route", tenant=tenant, source_type=source_type, error=str(e))
            return None
