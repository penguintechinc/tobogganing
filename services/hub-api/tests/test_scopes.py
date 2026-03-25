"""Tests for the scope vocabulary and role bundle system."""
import pytest
from auth.scopes import (
    ScopeDefinition,
    POLICIES_READ,
    WILDCARD_ALL,
    WILDCARD_READ,
    ROLE_SCOPE_BUNDLES,
    expand_role_to_scopes,
    scope_matches,
    has_required_scopes,
    parse_scope_string,
)


class TestScopeDefinition:
    def test_scope_string(self):
        sd = ScopeDefinition(resource="policies", action="read")
        assert sd.scope_string == "policies:read"

    def test_wildcard_scope_string(self):
        assert WILDCARD_ALL.scope_string == "*:*"

    def test_policies_read_constant(self):
        assert POLICIES_READ.scope_string == "policies:read"

    def test_wildcard_read_constant(self):
        assert WILDCARD_READ.scope_string == "*:read"

    def test_slots_set(self):
        # @dataclass(slots=True) means __dict__ is absent
        sd = ScopeDefinition(resource="hubs", action="write")
        assert not hasattr(sd, "__dict__")

    def test_equality(self):
        a = ScopeDefinition(resource="users", action="admin")
        b = ScopeDefinition(resource="users", action="admin")
        assert a == b

    def test_inequality(self):
        a = ScopeDefinition(resource="users", action="read")
        b = ScopeDefinition(resource="users", action="write")
        assert a != b


class TestScopeMatches:
    def test_exact_match(self):
        assert scope_matches("policies:read", "policies:read") is True

    def test_exact_mismatch(self):
        assert scope_matches("policies:read", "policies:write") is False

    def test_wildcard_resource(self):
        assert scope_matches("policies:read", "*:read") is True

    def test_wildcard_resource_wrong_action(self):
        assert scope_matches("policies:read", "*:write") is False

    def test_wildcard_action(self):
        assert scope_matches("policies:read", "policies:*") is True

    def test_wildcard_action_wrong_resource(self):
        assert scope_matches("policies:read", "hubs:*") is False

    def test_full_wildcard(self):
        assert scope_matches("policies:read", "*:*") is True
        assert scope_matches("users:admin", "*:*") is True

    def test_full_wildcard_admin(self):
        assert scope_matches("tenants:admin", "*:*") is True

    def test_no_reverse_wildcard(self):
        # The required scope being a wildcard does not grant anything
        assert scope_matches("*:read", "policies:read") is False

    def test_different_resource_exact(self):
        assert scope_matches("hubs:read", "policies:read") is False

    def test_wildcard_resource_with_admin_action(self):
        assert scope_matches("users:admin", "*:admin") is True

    def test_wildcard_resource_admin_wrong_action(self):
        assert scope_matches("users:read", "*:admin") is False

    def test_all_defined_resources_wildcard_read(self):
        resources = ["policies", "hubs", "clusters", "clients", "users",
                     "tenants", "teams", "identity", "spiffe", "certificates",
                     "settings", "audit"]
        for resource in resources:
            assert scope_matches(f"{resource}:read", "*:read") is True

    def test_all_defined_resources_wildcard_all(self):
        resources = ["policies", "hubs", "clusters", "clients", "users",
                     "tenants", "teams", "identity", "spiffe", "certificates",
                     "settings", "audit"]
        for resource in resources:
            for action in ["read", "write", "admin", "delete"]:
                assert scope_matches(f"{resource}:{action}", "*:*") is True


class TestHasRequiredScopes:
    def test_all_present(self):
        assert has_required_scopes(
            ["policies:read", "hubs:read"],
            ["policies:read", "hubs:read", "users:read"],
        ) is True

    def test_missing_one(self):
        assert has_required_scopes(
            ["policies:read", "hubs:write"],
            ["policies:read"],
        ) is False

    def test_wildcard_satisfies(self):
        assert has_required_scopes(
            ["policies:read", "hubs:read"],
            ["*:read"],
        ) is True

    def test_full_wildcard_satisfies_all(self):
        assert has_required_scopes(
            ["policies:read", "hubs:write", "users:admin"],
            ["*:*"],
        ) is True

    def test_empty_required(self):
        assert has_required_scopes([], ["policies:read"]) is True

    def test_empty_required_empty_available(self):
        assert has_required_scopes([], []) is True

    def test_empty_available(self):
        assert has_required_scopes(["policies:read"], []) is False

    def test_multiple_required_partial_wildcard(self):
        # *:read covers read but not write
        assert has_required_scopes(
            ["policies:read", "hubs:write"],
            ["*:read"],
        ) is False

    def test_multiple_scopes_in_available(self):
        assert has_required_scopes(
            ["policies:read", "hubs:write"],
            ["*:read", "*:write"],
        ) is True

    def test_single_required_single_available_match(self):
        assert has_required_scopes(["audit:read"], ["audit:read"]) is True

    def test_single_required_single_available_mismatch(self):
        assert has_required_scopes(["audit:write"], ["audit:read"]) is False


class TestExpandRoleToScopes:
    def test_admin_global(self):
        scopes = expand_role_to_scopes("admin", "global")
        assert "*:read" in scopes
        assert "*:write" in scopes
        assert "*:admin" in scopes
        assert "users:admin" in scopes

    def test_admin_global_has_delete(self):
        scopes = expand_role_to_scopes("admin", "global")
        assert "*:delete" in scopes

    def test_admin_global_has_settings_write(self):
        scopes = expand_role_to_scopes("admin", "global")
        assert "settings:write" in scopes

    def test_admin_global_has_tenants_admin(self):
        scopes = expand_role_to_scopes("admin", "global")
        assert "tenants:admin" in scopes

    def test_admin_tenant(self):
        scopes = expand_role_to_scopes("admin", "tenant")
        assert "*:read" in scopes
        assert "*:write" in scopes
        assert "*:admin" in scopes
        assert "users:admin" in scopes

    def test_admin_team(self):
        scopes = expand_role_to_scopes("admin", "team")
        assert "*:read" in scopes
        assert "*:write" in scopes
        assert "teams:admin" in scopes

    def test_maintainer_global(self):
        scopes = expand_role_to_scopes("maintainer", "global")
        assert "*:read" in scopes
        assert "*:write" in scopes
        assert "teams:read" in scopes

    def test_maintainer_global_no_admin(self):
        scopes = expand_role_to_scopes("maintainer", "global")
        assert "*:admin" not in scopes

    def test_maintainer_tenant(self):
        scopes = expand_role_to_scopes("maintainer", "tenant")
        assert "*:read" in scopes
        assert "*:write" in scopes

    def test_viewer_global(self):
        scopes = expand_role_to_scopes("viewer", "global")
        assert scopes == ["*:read"]

    def test_viewer_tenant(self):
        scopes = expand_role_to_scopes("viewer", "tenant")
        assert scopes == ["*:read"]

    def test_viewer_team(self):
        scopes = expand_role_to_scopes("viewer", "team")
        assert scopes == ["*:read"]

    def test_unknown_role(self):
        assert expand_role_to_scopes("nonexistent", "global") == []

    def test_unknown_layer(self):
        assert expand_role_to_scopes("admin", "nonexistent") == []

    def test_unknown_role_and_layer(self):
        assert expand_role_to_scopes("ghost", "nowhere") == []

    def test_returns_copy_not_reference(self):
        # Modifying the returned list must not affect ROLE_SCOPE_BUNDLES
        scopes = expand_role_to_scopes("viewer", "global")
        scopes.append("injected:scope")
        fresh = expand_role_to_scopes("viewer", "global")
        assert "injected:scope" not in fresh

    def test_db_override(self):
        # When a DB row is returned, its scopes take precedence
        mock_row = type("Row", (), {"scopes": ["custom:read", "custom:write"]})()
        mock_query = type("Q", (), {"select": lambda self, *a: type("Sel", (), {"first": lambda self: mock_row})()})()
        db = type("DB", (), {
            "role_scope_bundles": type("T", (), {
                "role": "role",
                "layer": "layer",
            })(),
            "__call__": lambda self, *a, **kw: mock_query,
        })()
        result = expand_role_to_scopes("viewer", "global", db=db)
        assert "custom:read" in result
        assert "custom:write" in result

    def test_db_override_string_scopes(self):
        # DB can return a space-separated string as well
        mock_row = type("Row", (), {"scopes": "custom:read custom:write"})()
        mock_query = type("Q", (), {"select": lambda self, *a: type("Sel", (), {"first": lambda self: mock_row})()})()
        db = type("DB", (), {
            "role_scope_bundles": type("T", (), {
                "role": "role",
                "layer": "layer",
            })(),
            "__call__": lambda self, *a, **kw: mock_query,
        })()
        result = expand_role_to_scopes("viewer", "global", db=db)
        assert "custom:read" in result
        assert "custom:write" in result

    def test_db_none_row_falls_back(self):
        # DB returns None row → fall back to built-in bundles
        mock_query = type("Q", (), {"select": lambda self, *a: type("Sel", (), {"first": lambda self: None})()})()
        db = type("DB", (), {
            "role_scope_bundles": type("T", (), {
                "role": "role",
                "layer": "layer",
            })(),
            "__call__": lambda self, *a, **kw: mock_query,
        })()
        result = expand_role_to_scopes("viewer", "global", db=db)
        assert result == ["*:read"]

    def test_db_exception_falls_back(self):
        # DB raises an exception → fall back to built-in bundles silently
        def _raise(*a, **kw):
            raise RuntimeError("db offline")

        db = type("DB", (), {"__call__": _raise})()
        result = expand_role_to_scopes("viewer", "global", db=db)
        assert result == ["*:read"]


class TestParseScopeString:
    def test_basic(self):
        assert parse_scope_string("policies:read users:write") == ["policies:read", "users:write"]

    def test_extra_spaces(self):
        assert parse_scope_string("  policies:read   users:write  ") == ["policies:read", "users:write"]

    def test_empty(self):
        assert parse_scope_string("") == []

    def test_single_scope(self):
        assert parse_scope_string("policies:read") == ["policies:read"]

    def test_whitespace_only(self):
        assert parse_scope_string("   ") == []

    def test_wildcard_scopes(self):
        result = parse_scope_string("*:read *:write *:admin")
        assert result == ["*:read", "*:write", "*:admin"]

    def test_full_wildcard(self):
        assert parse_scope_string("*:*") == ["*:*"]

    def test_many_scopes(self):
        raw = "policies:read hubs:read clusters:write users:admin tenants:admin"
        result = parse_scope_string(raw)
        assert len(result) == 5
        assert "policies:read" in result
        assert "tenants:admin" in result
