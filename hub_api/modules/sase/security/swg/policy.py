"""Category policy management for SWG enforcement actions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from hub_api.modules.sase.security.enforcement import (
    EnforcementAction,
    DEFAULT_UNCATEGORIZED,
    most_restrictive,
)

logger = structlog.get_logger()

__all__ = ["CategoryPolicyManager"]


class CategoryPolicyManager:
    """Manages category-to-action policies scoped to tenant/group/user.

    Resolves which enforcement action applies to a domain's categories
    based on policy precedence (user > group > tenant) and most-restrictive
    action selection.
    """

    def __init__(self, db: Any) -> None:
        """Initialize the policy manager.

        Args:
            db: penguin-dal DAL instance.
        """
        self.db = db

    async def set_policy(
        self,
        tenant: str,
        scope: str,
        scope_id: str | None,
        category: str,
        action: str,
    ) -> None:
        """Set or update a category policy.

        Args:
            tenant: Tenant ID.
            scope: Scope level ("tenant", "group", "user").
            scope_id: Scope identifier (group_id or user_id; None for tenant scope).
            category: Category name.
            action: Enforcement action string (allow, log_only, soft_block, block, drop).
        """
        # Validate scope
        if scope not in ("tenant", "group", "user"):
            logger.warning("invalid_scope", scope=scope, tenant=tenant)
            return

        # Validate action
        try:
            action_enum = EnforcementAction(action)
        except ValueError:
            logger.warning("invalid_action", action=action, tenant=tenant)
            return

        now = datetime.now(timezone.utc)

        try:
            # Check if policy exists
            existing = await self._get_policy(tenant, scope, scope_id, category)

            if existing:
                # Update
                existing.action = action
                await self.db.category_policies.update(existing)
            else:
                # Insert
                new_id = str(uuid.uuid4())
                await self.db.category_policies.insert({
                    "id": new_id,
                    "tenant": tenant,
                    "scope": scope,
                    "scope_id": scope_id,
                    "category": category,
                    "action": action,
                    "created_at": now,
                })

            logger.info(
                "policy_set",
                tenant=tenant,
                scope=scope,
                category=category,
                action=action,
            )
        except Exception as e:
            logger.error("set_policy_failed", tenant=tenant, error=str(e))

    async def get_policies(self, tenant: str) -> list[Any]:
        """Get all policies for a tenant.

        Args:
            tenant: Tenant ID.

        Returns:
            List of CategoryPolicy objects.
        """
        try:
            rows = await self.db.category_policies.select(tenant=tenant)
            return list(rows) if rows else []
        except Exception as e:
            logger.error("get_policies_failed", tenant=tenant, error=str(e))
            return []

    async def resolve(
        self,
        tenant: str,
        categories: tuple[str, ...] | None,
        *,
        user_id: str | None = None,
        group_ids: tuple[str, ...] | None = None,
    ) -> tuple[EnforcementAction, str]:
        """Resolve the enforcement action for a domain's categories.

        Uses scope precedence (user > group > tenant) and picks the most-restrictive
        action among matching categories. If no policy matches or categories are None,
        returns the tenant default (allow).

        Args:
            tenant: Tenant ID.
            categories: Tuple of category names (None for uncategorized).
            user_id: User ID (optional).
            group_ids: Tuple of group IDs (optional).

        Returns:
            (EnforcementAction, matched_scope) tuple.
        """
        if not categories:
            # Uncategorized: use default
            return (DEFAULT_UNCATEGORIZED, "default")

        try:
            policies = await self.get_policies(tenant)
            if not policies:
                # No policies: default to allow
                return (DEFAULT_UNCATEGORIZED, "default")

            # Filter policies for this domain's categories
            matching_policies = [p for p in policies if p.category in categories]
            if not matching_policies:
                # No matching policies: default to allow
                return (DEFAULT_UNCATEGORIZED, "default")

            # Apply scope precedence: user > group > tenant
            user_policies = [p for p in matching_policies if p.scope == "user" and p.scope_id == user_id] if user_id else []
            group_policies = [p for p in matching_policies if p.scope == "group" and p.scope_id in (group_ids or ())] if group_ids else []
            tenant_policies = [p for p in matching_policies if p.scope == "tenant"]

            # Pick most-specific scope
            if user_policies:
                actions = [EnforcementAction(p.action) for p in user_policies]
                return (most_restrictive(actions), "user")
            elif group_policies:
                actions = [EnforcementAction(p.action) for p in group_policies]
                return (most_restrictive(actions), "group")
            elif tenant_policies:
                actions = [EnforcementAction(p.action) for p in tenant_policies]
                return (most_restrictive(actions), "tenant")
            else:
                # No matching policies
                return (DEFAULT_UNCATEGORIZED, "default")

        except Exception as e:
            logger.error("resolve_failed", tenant=tenant, error=str(e))
            # Fail open: default to allow
            return (DEFAULT_UNCATEGORIZED, "default")

    # Private methods

    async def _get_policy(
        self, tenant: str, scope: str, scope_id: str | None, category: str
    ) -> Any:
        """Fetch an existing policy.

        Args:
            tenant: Tenant ID.
            scope: Scope level.
            scope_id: Scope identifier.
            category: Category name.

        Returns:
            Existing policy, or None.
        """
        try:
            rows = await self.db.category_policies.select(
                tenant=tenant, scope=scope, scope_id=scope_id, category=category
            )
            return rows[0] if rows else None
        except Exception:
            return None
