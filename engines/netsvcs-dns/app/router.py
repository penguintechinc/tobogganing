"""Selective DNS routing with split-horizon zone access control.

THE AUTHORITATIVE implementation — consolidates three divergent copies from squawk:
- selective_router.py::check_zone_permission
- utils/resilience.py::_check_zone_permission
- main.py::_find_zone_name

All split-horizon logic now lives here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class TokenClaims:
    """DNS client token claims."""

    teams: list[str]
    role: str | None = None


class SelectiveRouter:
    """Selective DNS routing based on visibility + token team/role membership.

    Visibility levels (public → private in restriction order):
    - public: accessible to anyone
    - internal: accessible to authenticated users sharing a team (or no team restriction)
    - restricted: accessible only to users in specific allowed_teams
    - private: accessible only to admin-role users

    No matching zone falls through to public recursion (implicitly allowed).
    """

    def __init__(self) -> None:
        """Initialize router."""
        self.zones: dict[str, dict] = {}

    def load_zones(self, zones: list[dict]) -> None:
        """Load DNS zones from Manager config.

        Each zone dict must contain:
        - name: zone name (e.g., "internal.example.com")
        - visibility: "public", "internal", "restricted", or "private"
        - allowed_teams: list of team IDs (used for internal/restricted)
        - records: list of DNS records {name, type, ttl, value}

        Args:
            zones: List of zone configurations from Manager.
        """
        self.zones.clear()

        for zone in zones:
            zone_name = zone.get("name")
            if not zone_name:
                logger.warning("Zone missing name, skipping")
                continue

            self.zones[zone_name] = {
                "name": zone_name,
                "visibility": zone.get("visibility", "public"),
                "allowed_teams": zone.get("allowed_teams", []),
                "records": zone.get("records", []),
            }

        logger.info(f"Loaded {len(self.zones)} DNS zones")

    def find_zone_for_domain(self, domain: str) -> dict | None:
        """Find zone matching domain via exact match then parent-label walk.

        The authoritative zone-finding logic (consolidates main.py::_find_zone_name).

        Args:
            domain: Domain being queried.

        Returns:
            Zone dict or None if no match.
        """
        # Exact match first
        if domain in self.zones:
            return self.zones[domain]

        # Walk parent labels (e.g., www.internal.example.com → internal.example.com → example.com)
        parts = domain.split(".")
        for i in range(len(parts)):
            parent = ".".join(parts[i:])
            if parent in self.zones:
                return self.zones[parent]

        return None

    def check_zone_permission(
        self, domain: str, token_claims: TokenClaims | None = None
    ) -> bool:
        """Check if token has permission to access zone for domain.

        THE AUTHORITATIVE permission-check logic (consolidates
        selective_router.py::check_zone_permission and
        resilience.py::_check_zone_permission).

        No matching zone → allow (falls through to public recursion).
        Public zones → always allow.
        Non-public without token → deny.
        Internal: allow if no team restrictions OR token shares a team.
        Restricted: allow only if token shares a team.
        Private: allow only if role == "admin".
        Unknown visibility → deny.

        Args:
            domain: Domain being queried.
            token_claims: Parsed JWT token claims {teams, role} or None.

        Returns:
            True if allowed, False otherwise.
        """
        zone = self.find_zone_for_domain(domain)

        if not zone:
            # No custom zone, allow (falls through to public recursion)
            return True

        visibility = zone.get("visibility", "public")

        # Public zones always accessible
        if visibility == "public":
            return True

        # Any non-public zone requires a token
        if not token_claims:
            logger.debug(
                f"Access denied to {visibility} zone {zone['name']}: no token provided"
            )
            return False

        allowed_teams = zone.get("allowed_teams", [])

        if visibility == "internal":
            # Internal: allow if no team restrictions OR token shares a team
            if not allowed_teams or any(team in allowed_teams for team in token_claims.teams):
                return True
            else:
                logger.debug(
                    f"Access denied to internal zone {zone['name']}: "
                    f"user teams {token_claims.teams} not in {allowed_teams}"
                )
                return False

        elif visibility == "restricted":
            # Restricted: allow only if token shares a team
            if any(team in allowed_teams for team in token_claims.teams):
                return True
            else:
                logger.debug(
                    f"Access denied to restricted zone {zone['name']}: "
                    f"user teams {token_claims.teams} not in {allowed_teams}"
                )
                return False

        elif visibility == "private":
            # Private: allow only if role == "admin"
            if token_claims.role == "admin":
                return True
            else:
                logger.debug(
                    f"Access denied to private zone {zone['name']}: "
                    f"user role {token_claims.role} is not admin"
                )
                return False

        else:
            # Unknown visibility, deny
            logger.warning(f"Unknown visibility '{visibility}' for zone {zone['name']}")
            return False

    def get_zone_records(self, domain: str) -> list[dict] | None:
        """Get DNS records for domain from custom zones.

        Args:
            domain: Domain to look up.

        Returns:
            List of records or None if not in custom zones.
        """
        zone = self.find_zone_for_domain(domain)

        if zone:
            return zone.get("records", [])

        return None

    def should_serve_zone(
        self, domain: str, token_claims: TokenClaims | None, mode: str
    ) -> bool:
        """Determine if zone should be served based on mode + permissions.

        Mode affects which zones are eligible:
        - normal/cached: full permission check
        - degraded: public zones only

        Args:
            domain: Domain being queried.
            token_claims: Token claims or None.
            mode: Operational mode (normal, cached, degraded).

        Returns:
            True if should serve, False otherwise.
        """
        zone = self.find_zone_for_domain(domain)

        if not zone:
            # Not a custom zone, always serve
            return True

        if mode in ("normal", "cached"):
            # Full functionality, check permissions
            return self.check_zone_permission(domain, token_claims)

        elif mode == "degraded":
            # Public-only mode
            visibility = zone.get("visibility", "public")
            return visibility == "public"

        return False

    def get_stats(self) -> dict[str, int]:
        """Get routing statistics.

        Returns:
            Dict with total_zones and visibility_breakdown.
        """
        visibility_counts: dict[str, int] = {}

        for zone in self.zones.values():
            visibility = zone.get("visibility", "public")
            visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1

        return {
            "total_zones": len(self.zones),
            "visibility_breakdown": visibility_counts,
        }
