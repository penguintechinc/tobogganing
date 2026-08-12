"""Selective DNS routing with split-horizon zone access control.

THE AUTHORITATIVE implementation — consolidates three divergent copies from squawk:
- selective_router.py::check_zone_permission
- utils/resilience.py::_check_zone_permission
- main.py::_find_zone_name

All split-horizon logic now lives here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class TokenClaims:
    """DNS client token claims.

    allowed_zone_ids: List of zone IDs this token is permitted to resolve.
                       Set by the control plane's ValidateToken response.
                       Default empty (no zone-scoped restrictions); filled by control plane.
    """

    teams: list[str]
    allowed_zone_ids: list[str] = field(default_factory=list)
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
        - id: zone ID (e.g., "z1") for control-plane tenant scoping
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
                "id": zone.get("id"),  # Zone ID for control-plane tenant scoping
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

        COMBINED RULE (public OR allowed_zone_ids):
        - A zone is served if visibility=="public" (SelectiveRouter allows visibility), OR
        - the zone's id is in the token's allowed_zone_ids (control-plane tenant+token scoping).

        No matching zone → allow (falls through to public recursion).
        Public zones → always allow.
        Non-public zones:
        - Check if zone.id is in token.allowed_zone_ids (tenant-scoped from control plane).
        - If zone NOT in allowed_zone_ids, deny.
        - If in allowed_zone_ids, apply classic visibility logic (teams, role).

        Args:
            domain: Domain being queried.
            token_claims: Parsed JWT token claims {teams, allowed_zone_ids, role} or None.

        Returns:
            True if allowed, False otherwise.
        """
        zone = self.find_zone_for_domain(domain)

        if not zone:
            # No custom zone, allow (falls through to public recursion)
            return True

        visibility = zone.get("visibility", "public")
        zone_id = zone.get("id")

        # Public zones always accessible
        if visibility == "public":
            return True

        # Non-public zone requires token
        if not token_claims:
            logger.debug(
                f"Access denied to {visibility} zone {zone['name']}: no token provided"
            )
            return False

        # Tenant+token scoping: zone must be in allowed_zone_ids
        if zone_id and zone_id not in token_claims.allowed_zone_ids:
            logger.debug(
                f"Access denied to zone {zone['name']}: zone id {zone_id} not in "
                f"allowed_zone_ids {token_claims.allowed_zone_ids}"
            )
            return False

        # Zone is in allowed_zone_ids; now check visibility rules
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
