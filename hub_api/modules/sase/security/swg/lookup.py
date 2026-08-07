"""Domain lookup and enforcement action resolution for SWG."""
from __future__ import annotations

import json
from typing import Any

import structlog

from hub_api.cache import CacheClient
from hub_api.modules.sase.security.enforcement import (
    EnforcementAction,
    DEFAULT_UNCATEGORIZED,
)
from hub_api.modules.sase.security.swg.models import LookupResult
from hub_api.modules.sase.security.swg.radix import RadixTree
from hub_api.modules.sase.security.swg.policy import CategoryPolicyManager

logger = structlog.get_logger()

__all__ = ["SwgLookup", "build_radix"]


class SwgLookup:
    """Domain lookup with category matching and policy-based enforcement action.

    Combines radix tree lookup, policy resolution, and caching to determine
    the appropriate enforcement action for a domain access attempt.
    Fails open: miss or error → allow (never block on infrastructure failure).
    """

    def __init__(
        self, radix: RadixTree, policy_mgr: CategoryPolicyManager, cache: CacheClient
    ) -> None:
        """Initialize the lookup engine.

        Args:
            radix: RadixTree for domain→categories mapping.
            policy_mgr: CategoryPolicyManager for policy resolution.
            cache: CacheClient for catcache access.
        """
        self.radix = radix
        self.policy_mgr = policy_mgr
        self.cache = cache

    async def lookup(
        self,
        domain: str,
        *,
        tenant: str,
        user_id: str | None = None,
        group_ids: tuple[str, ...] | None = None,
    ) -> LookupResult:
        """Look up a domain and resolve its enforcement action.

        Returns categories from the radix tree (or cache), resolves the policy,
        and returns the enforcement action. Fails open: any error → allow.

        Args:
            domain: Domain to look up.
            tenant: Tenant ID.
            user_id: User ID (optional).
            group_ids: Tuple of group IDs (optional).

        Returns:
            LookupResult with domain, categories, action, matched_scope, uncategorized.
        """
        domain = domain.lower().strip()

        try:
            # Step 1: Try radix tree first
            categories = self.radix.lookup(domain)

            # Step 2: If not found, try cache
            if categories is None:
                categories = await self._lookup_cache(domain)

            # Step 3: Resolve policy
            if categories:
                action, matched_scope = await self.policy_mgr.resolve(
                    tenant, categories, user_id=user_id, group_ids=group_ids
                )
                return LookupResult(
                    domain=domain,
                    categories=categories,
                    action=action,
                    matched_scope=matched_scope,
                    uncategorized=False,
                )
            else:
                # Uncategorized domain
                await self._enqueue_uncategorized(domain, tenant)
                return LookupResult(
                    domain=domain,
                    categories=None,
                    action=DEFAULT_UNCATEGORIZED,
                    matched_scope="default",
                    uncategorized=True,
                )

        except Exception as e:
            # Fail open: any error during lookup → allow
            logger.error("lookup_failed", domain=domain, tenant=tenant, error=str(e))
            return LookupResult(
                domain=domain,
                categories=None,
                action=EnforcementAction.allow,
                matched_scope="error",
                uncategorized=True,
            )

    # Private methods

    async def _lookup_cache(self, domain: str) -> tuple[str, ...] | None:
        """Look up categories in Valkey cache.

        Args:
            domain: Domain to look up.

        Returns:
            Tuple of categories, or None.
        """
        try:
            cache_key = f"sase:catcache:{domain}"
            cached_value = await self.cache.get(cache_key)

            if cached_value:
                try:
                    categories = json.loads(cached_value)
                    return tuple(categories)
                except (json.JSONDecodeError, TypeError):
                    return None
            return None
        except Exception as e:
            logger.debug("cache_lookup_failed", domain=domain, error=str(e))
            return None

    async def _enqueue_uncategorized(self, domain: str, tenant: str) -> None:
        """Enqueue an uncategorized domain for Slice-E processing.

        This is a no-op stub in Slice B. Slice E will hook here to categorize
        unknown domains via AI and write results back to the radix.

        Args:
            domain: Domain to categorize.
            tenant: Tenant ID.
        """
        # Slice B: no-op stub
        logger.info(
            "uncategorized_enqueue_stub",
            domain=domain,
            tenant=tenant,
            message="would enqueue for Slice-E AI categorization",
        )


async def build_radix(db: Any) -> RadixTree:
    """Build a RadixTree from domain_categories database, custom-wins-on-conflict.

    Fetches all domain_categories from the database and builds a radix tree.
    When the same (domain, category) pair exists in both feed and custom sources,
    the custom version is used.

    Args:
        db: penguin-dal DAL instance.

    Returns:
        Built RadixTree ready for lookups.
    """
    tree = RadixTree()

    try:
        # Fetch all domain_categories
        rows = await db.domain_categories.select()
        if not rows:
            logger.info("build_radix_empty", message="no categories in database")
            return tree

        # Group by (domain, category) to track sources
        domain_categories_map: dict[tuple[str, str], str] = {}

        for row in rows:
            domain = row.domain.lower().strip()
            source = row.source.lower().strip()

            try:
                categories = json.loads(row.categories)
            except (json.JSONDecodeError, TypeError):
                continue

            for category in categories:
                category = category.lower().strip()
                if not domain or not category:
                    continue

                key = (domain, category)

                # Custom wins on conflict
                if key not in domain_categories_map:
                    domain_categories_map[key] = source
                elif source == "custom":
                    domain_categories_map[key] = source

        # Insert into radix tree (grouped by domain)
        domain_to_categories: dict[str, set[str]] = {}
        for (domain, category), source in domain_categories_map.items():
            if domain not in domain_to_categories:
                domain_to_categories[domain] = set()
            domain_to_categories[domain].add(category)

        for domain, categories in domain_to_categories.items():
            tree.insert(domain, tuple(sorted(categories)))

        logger.info(
            "build_radix_complete",
            domains=len(domain_to_categories),
            total_categories=len(domain_categories_map),
        )

    except Exception as e:
        logger.error("build_radix_failed", error=str(e))

    return tree
