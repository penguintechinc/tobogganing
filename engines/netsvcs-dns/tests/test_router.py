"""Tests for the split-horizon selective router.

Comprehensive visibility matrix tests verifying the authoritative permission logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.router import SelectiveRouter, TokenClaims


class TestSelectiveRouterZoneLoading:
    """Test zone loading."""

    @pytest.fixture
    def router(self) -> SelectiveRouter:
        """Create router instance."""
        return SelectiveRouter()

    def test_load_zones(self, router: SelectiveRouter) -> None:
        """Test loading zones from config."""
        zones = [
            {"name": "public.example.com", "visibility": "public", "records": []},
            {
                "name": "internal.example.com",
                "visibility": "internal",
                "allowed_teams": ["team-a"],
                "records": [],
            },
        ]

        router.load_zones(zones)

        assert len(router.zones) == 2
        assert router.zones["public.example.com"]["visibility"] == "public"
        assert router.zones["internal.example.com"]["visibility"] == "internal"

    def test_load_zones_clears_previous(self, router: SelectiveRouter) -> None:
        """Test that loading zones clears previous state."""
        router.load_zones([{"name": "zone1.com", "visibility": "public", "records": []}])
        assert len(router.zones) == 1

        router.load_zones([{"name": "zone2.com", "visibility": "public", "records": []}])
        assert len(router.zones) == 1
        assert "zone1.com" not in router.zones
        assert "zone2.com" in router.zones


class TestZoneFinding:
    """Test zone finding logic."""

    @pytest.fixture
    def router_with_zones(self) -> SelectiveRouter:
        """Create router with test zones."""
        router = SelectiveRouter()
        router.load_zones(
            [
                {"name": "example.com", "visibility": "public", "records": []},
                {"name": "internal.example.com", "visibility": "internal", "records": []},
            ]
        )
        return router

    def test_find_zone_exact_match(self, router_with_zones: SelectiveRouter) -> None:
        """Test exact zone match."""
        zone = router_with_zones.find_zone_for_domain("example.com")

        assert zone is not None
        assert zone["name"] == "example.com"

    def test_find_zone_subdomain(self, router_with_zones: SelectiveRouter) -> None:
        """Test subdomain walks to parent zone."""
        zone = router_with_zones.find_zone_for_domain("www.example.com")

        assert zone is not None
        assert zone["name"] == "example.com"

    def test_find_zone_deeper_subdomain(self, router_with_zones: SelectiveRouter) -> None:
        """Test deeper subdomain walks to parent zone."""
        zone = router_with_zones.find_zone_for_domain("api.internal.example.com")

        assert zone is not None
        assert zone["name"] == "internal.example.com"

    def test_find_zone_not_found(self, router_with_zones: SelectiveRouter) -> None:
        """Test no zone found."""
        zone = router_with_zones.find_zone_for_domain("other.com")

        assert zone is None


class TestVisibilityMatrix:
    """Test the full split-horizon visibility matrix."""

    @pytest.fixture
    def router_with_zones(self) -> SelectiveRouter:
        """Create router with all visibility levels."""
        router = SelectiveRouter()
        router.load_zones(
            [
                {"name": "public.com", "visibility": "public", "allowed_teams": [], "records": []},
                {
                    "name": "internal.com",
                    "visibility": "internal",
                    "allowed_teams": ["team-a", "team-b"],
                    "records": [],
                },
                {
                    "name": "internal-no-teams.com",
                    "visibility": "internal",
                    "allowed_teams": [],
                    "records": [],
                },
                {
                    "name": "restricted.com",
                    "visibility": "restricted",
                    "allowed_teams": ["team-x"],
                    "records": [],
                },
                {"name": "private.com", "visibility": "private", "allowed_teams": [], "records": []},
            ]
        )
        return router

    # PUBLIC VISIBILITY

    def test_public_zone_no_token(self, router_with_zones: SelectiveRouter) -> None:
        """Public zone: no token → allow."""
        result = router_with_zones.check_zone_permission("public.com", None)
        assert result is True

    def test_public_zone_with_token(self, router_with_zones: SelectiveRouter) -> None:
        """Public zone: with token → allow."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.check_zone_permission("public.com", token)
        assert result is True

    # INTERNAL VISIBILITY - WITH TEAM RESTRICTIONS

    def test_internal_with_teams_no_token(self, router_with_zones: SelectiveRouter) -> None:
        """Internal zone with teams: no token → deny."""
        result = router_with_zones.check_zone_permission("internal.com", None)
        assert result is False

    def test_internal_with_teams_user_in_allowed_team(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Internal zone: user in allowed team → allow."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.check_zone_permission("internal.com", token)
        assert result is True

    def test_internal_with_teams_user_in_different_team(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Internal zone: user in different team → deny."""
        token = TokenClaims(teams=["team-c"], role="user")
        result = router_with_zones.check_zone_permission("internal.com", token)
        assert result is False

    def test_internal_with_teams_user_in_multiple_teams(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Internal zone: user in multiple teams, one allowed → allow."""
        token = TokenClaims(teams=["team-c", "team-a", "team-d"], role="user")
        result = router_with_zones.check_zone_permission("internal.com", token)
        assert result is True

    # INTERNAL VISIBILITY - NO TEAM RESTRICTIONS

    def test_internal_no_teams_no_token(self, router_with_zones: SelectiveRouter) -> None:
        """Internal zone with no team restrictions: no token → deny."""
        result = router_with_zones.check_zone_permission("internal-no-teams.com", None)
        assert result is False

    def test_internal_no_teams_with_any_token(self, router_with_zones: SelectiveRouter) -> None:
        """Internal zone with no team restrictions: any token → allow."""
        token = TokenClaims(teams=["team-x"], role="user")
        result = router_with_zones.check_zone_permission("internal-no-teams.com", token)
        assert result is True

    def test_internal_no_teams_with_empty_teams_token(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Internal zone with no team restrictions: token with empty teams → allow."""
        token = TokenClaims(teams=[], role="user")
        result = router_with_zones.check_zone_permission("internal-no-teams.com", token)
        assert result is True

    # RESTRICTED VISIBILITY

    def test_restricted_zone_no_token(self, router_with_zones: SelectiveRouter) -> None:
        """Restricted zone: no token → deny."""
        result = router_with_zones.check_zone_permission("restricted.com", None)
        assert result is False

    def test_restricted_zone_user_in_allowed_team(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Restricted zone: user in allowed team → allow."""
        token = TokenClaims(teams=["team-x"], role="user")
        result = router_with_zones.check_zone_permission("restricted.com", token)
        assert result is True

    def test_restricted_zone_user_not_in_allowed_team(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Restricted zone: user not in allowed team → deny."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.check_zone_permission("restricted.com", token)
        assert result is False

    def test_restricted_zone_user_in_multiple_teams_one_allowed(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Restricted zone: user in multiple teams, one allowed → allow."""
        token = TokenClaims(teams=["team-a", "team-x", "team-b"], role="user")
        result = router_with_zones.check_zone_permission("restricted.com", token)
        assert result is True

    # PRIVATE VISIBILITY

    def test_private_zone_no_token(self, router_with_zones: SelectiveRouter) -> None:
        """Private zone: no token → deny."""
        result = router_with_zones.check_zone_permission("private.com", None)
        assert result is False

    def test_private_zone_user_role(self, router_with_zones: SelectiveRouter) -> None:
        """Private zone: non-admin user → deny."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.check_zone_permission("private.com", token)
        assert result is False

    def test_private_zone_admin_role(self, router_with_zones: SelectiveRouter) -> None:
        """Private zone: admin user → allow."""
        token = TokenClaims(teams=[], role="admin")
        result = router_with_zones.check_zone_permission("private.com", token)
        assert result is True

    def test_private_zone_maintainer_role(self, router_with_zones: SelectiveRouter) -> None:
        """Private zone: non-admin role (maintainer) → deny."""
        token = TokenClaims(teams=[], role="maintainer")
        result = router_with_zones.check_zone_permission("private.com", token)
        assert result is False

    # NO MATCHING ZONE

    def test_no_zone_match_no_token(self, router_with_zones: SelectiveRouter) -> None:
        """No matching zone: no token → allow (fall through to public recursion)."""
        result = router_with_zones.check_zone_permission("other.com", None)
        assert result is True

    def test_no_zone_match_with_token(self, router_with_zones: SelectiveRouter) -> None:
        """No matching zone: with token → allow (fall through to public recursion)."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.check_zone_permission("other.com", token)
        assert result is True


class TestShouldServeZone:
    """Test operational mode logic."""

    @pytest.fixture
    def router_with_zones(self) -> SelectiveRouter:
        """Create router with test zones."""
        router = SelectiveRouter()
        router.load_zones(
            [
                {"name": "public.com", "visibility": "public", "records": []},
                {
                    "name": "internal.com",
                    "visibility": "internal",
                    "allowed_teams": ["team-a"],
                    "records": [],
                },
            ]
        )
        return router

    def test_normal_mode_public_zone(self, router_with_zones: SelectiveRouter) -> None:
        """Normal mode: public zone → allow."""
        result = router_with_zones.should_serve_zone("public.com", None, "normal")
        assert result is True

    def test_normal_mode_internal_zone_with_token(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Normal mode: internal zone with valid token → allow."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.should_serve_zone("internal.com", token, "normal")
        assert result is True

    def test_cached_mode_public_zone(self, router_with_zones: SelectiveRouter) -> None:
        """Cached mode: public zone → allow (same as normal)."""
        result = router_with_zones.should_serve_zone("public.com", None, "cached")
        assert result is True

    def test_cached_mode_internal_zone_with_token(
        self, router_with_zones: SelectiveRouter
    ) -> None:
        """Cached mode: internal zone with token → allow."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.should_serve_zone("internal.com", token, "cached")
        assert result is True

    def test_degraded_mode_public_zone(self, router_with_zones: SelectiveRouter) -> None:
        """Degraded mode: public zone → allow."""
        result = router_with_zones.should_serve_zone("public.com", None, "degraded")
        assert result is True

    def test_degraded_mode_internal_zone(self, router_with_zones: SelectiveRouter) -> None:
        """Degraded mode: internal zone → deny (public-only mode)."""
        token = TokenClaims(teams=["team-a"], role="user")
        result = router_with_zones.should_serve_zone("internal.com", token, "degraded")
        assert result is False

    def test_degraded_mode_non_custom_zone(self, router_with_zones: SelectiveRouter) -> None:
        """Degraded mode: non-custom zone → allow (fall through to public recursion)."""
        result = router_with_zones.should_serve_zone("other.com", None, "degraded")
        assert result is True


class TestGetZoneRecords:
    """Test zone record retrieval."""

    @pytest.fixture
    def router_with_zones(self) -> SelectiveRouter:
        """Create router with test zones."""
        router = SelectiveRouter()
        router.load_zones(
            [
                {
                    "name": "internal.com",
                    "visibility": "internal",
                    "records": [
                        {"name": "internal.com", "type": "A", "ttl": 300, "value": "10.0.0.1"},
                        {"name": "db.internal.com", "type": "A", "ttl": 300, "value": "10.0.0.2"},
                    ],
                },
            ]
        )
        return router

    def test_get_zone_records_match(self, router_with_zones: SelectiveRouter) -> None:
        """Test getting records for matching zone."""
        records = router_with_zones.get_zone_records("db.internal.com")

        assert records is not None
        assert len(records) == 2

    def test_get_zone_records_no_match(self, router_with_zones: SelectiveRouter) -> None:
        """Test getting records for non-matching zone."""
        records = router_with_zones.get_zone_records("other.com")

        assert records is None


class TestGetStats:
    """Test statistics."""

    @pytest.fixture
    def router_with_zones(self) -> SelectiveRouter:
        """Create router with test zones."""
        router = SelectiveRouter()
        router.load_zones(
            [
                {"name": "public1.com", "visibility": "public", "records": []},
                {"name": "public2.com", "visibility": "public", "records": []},
                {"name": "internal.com", "visibility": "internal", "records": []},
                {"name": "private.com", "visibility": "private", "records": []},
            ]
        )
        return router

    def test_get_stats(self, router_with_zones: SelectiveRouter) -> None:
        """Test statistics generation."""
        stats = router_with_zones.get_stats()

        assert stats["total_zones"] == 4
        assert stats["visibility_breakdown"]["public"] == 2
        assert stats["visibility_breakdown"]["internal"] == 1
        assert stats["visibility_breakdown"]["private"] == 1
