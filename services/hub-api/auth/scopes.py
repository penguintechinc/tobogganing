"""
OIDC-compliant scope vocabulary and role bundle system for Tobogganing Hub API.

Scopes follow the RFC 9068 / OAuth 2.0 convention: ``resource:action``
(e.g. ``policies:read``, ``users:admin``).  Wildcard scopes use ``*`` as the
resource segment (``*:read`` satisfies any ``<resource>:read`` requirement).
``*:*`` satisfies every requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Primitive scope definition
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ScopeDefinition:
    """Represents a single permission scope as resource + action pair."""

    resource: str
    action: str

    @property
    def scope_string(self) -> str:
        """Return the canonical ``resource:action`` representation."""
        return f"{self.resource}:{self.action}"


# ---------------------------------------------------------------------------
# All defined scopes as module-level constants
# ---------------------------------------------------------------------------

# --- policies ---
POLICIES_READ   = ScopeDefinition(resource="policies",     action="read")
POLICIES_WRITE  = ScopeDefinition(resource="policies",     action="write")
POLICIES_ADMIN  = ScopeDefinition(resource="policies",     action="admin")
POLICIES_DELETE = ScopeDefinition(resource="policies",     action="delete")

# --- hubs ---
HUBS_READ   = ScopeDefinition(resource="hubs",   action="read")
HUBS_WRITE  = ScopeDefinition(resource="hubs",   action="write")
HUBS_ADMIN  = ScopeDefinition(resource="hubs",   action="admin")
HUBS_DELETE = ScopeDefinition(resource="hubs",   action="delete")

# --- clusters ---
CLUSTERS_READ   = ScopeDefinition(resource="clusters",   action="read")
CLUSTERS_WRITE  = ScopeDefinition(resource="clusters",   action="write")
CLUSTERS_ADMIN  = ScopeDefinition(resource="clusters",   action="admin")
CLUSTERS_DELETE = ScopeDefinition(resource="clusters",   action="delete")

# --- clients ---
CLIENTS_READ   = ScopeDefinition(resource="clients",   action="read")
CLIENTS_WRITE  = ScopeDefinition(resource="clients",   action="write")
CLIENTS_ADMIN  = ScopeDefinition(resource="clients",   action="admin")
CLIENTS_DELETE = ScopeDefinition(resource="clients",   action="delete")

# --- users ---
USERS_READ   = ScopeDefinition(resource="users",   action="read")
USERS_WRITE  = ScopeDefinition(resource="users",   action="write")
USERS_ADMIN  = ScopeDefinition(resource="users",   action="admin")
USERS_DELETE = ScopeDefinition(resource="users",   action="delete")

# --- tenants ---
TENANTS_READ   = ScopeDefinition(resource="tenants",   action="read")
TENANTS_WRITE  = ScopeDefinition(resource="tenants",   action="write")
TENANTS_ADMIN  = ScopeDefinition(resource="tenants",   action="admin")
TENANTS_DELETE = ScopeDefinition(resource="tenants",   action="delete")

# --- teams ---
TEAMS_READ   = ScopeDefinition(resource="teams",   action="read")
TEAMS_WRITE  = ScopeDefinition(resource="teams",   action="write")
TEAMS_ADMIN  = ScopeDefinition(resource="teams",   action="admin")
TEAMS_DELETE = ScopeDefinition(resource="teams",   action="delete")

# --- identity ---
IDENTITY_READ   = ScopeDefinition(resource="identity",   action="read")
IDENTITY_WRITE  = ScopeDefinition(resource="identity",   action="write")
IDENTITY_ADMIN  = ScopeDefinition(resource="identity",   action="admin")
IDENTITY_DELETE = ScopeDefinition(resource="identity",   action="delete")

# --- spiffe ---
SPIFFE_READ   = ScopeDefinition(resource="spiffe",   action="read")
SPIFFE_WRITE  = ScopeDefinition(resource="spiffe",   action="write")
SPIFFE_ADMIN  = ScopeDefinition(resource="spiffe",   action="admin")
SPIFFE_DELETE = ScopeDefinition(resource="spiffe",   action="delete")

# --- certificates ---
CERTIFICATES_READ   = ScopeDefinition(resource="certificates",   action="read")
CERTIFICATES_WRITE  = ScopeDefinition(resource="certificates",   action="write")
CERTIFICATES_ADMIN  = ScopeDefinition(resource="certificates",   action="admin")
CERTIFICATES_DELETE = ScopeDefinition(resource="certificates",   action="delete")

# --- settings ---
SETTINGS_READ   = ScopeDefinition(resource="settings",   action="read")
SETTINGS_WRITE  = ScopeDefinition(resource="settings",   action="write")
SETTINGS_ADMIN  = ScopeDefinition(resource="settings",   action="admin")
SETTINGS_DELETE = ScopeDefinition(resource="settings",   action="delete")

# --- audit ---
AUDIT_READ   = ScopeDefinition(resource="audit",   action="read")
AUDIT_WRITE  = ScopeDefinition(resource="audit",   action="write")
AUDIT_ADMIN  = ScopeDefinition(resource="audit",   action="admin")
AUDIT_DELETE = ScopeDefinition(resource="audit",   action="delete")

# --- wildcards ---
WILDCARD_READ   = ScopeDefinition(resource="*", action="read")
WILDCARD_WRITE  = ScopeDefinition(resource="*", action="write")
WILDCARD_ADMIN  = ScopeDefinition(resource="*", action="admin")
WILDCARD_DELETE = ScopeDefinition(resource="*", action="delete")
WILDCARD_ALL    = ScopeDefinition(resource="*", action="*")


# ---------------------------------------------------------------------------
# Role scope bundles (built-in defaults, DB overrides take precedence)
# ---------------------------------------------------------------------------

#: Built-in role→layer→[scope_string, ...] mapping.
#:
#: Structure::
#:
#:     {
#:         "<role>": {
#:             "<layer>": ["scope:action", ...],
#:         }
#:     }
#:
#: Supported roles:  ``admin``, ``maintainer``, ``viewer``
#: Supported layers: ``global``, ``tenant``, ``team``
ROLE_SCOPE_BUNDLES: dict[str, dict[str, list[str]]] = {
    "admin": {
        "global": [
            "*:read",
            "*:write",
            "*:admin",
            "*:delete",
            "settings:write",
            "users:admin",
            "tenants:admin",
        ],
        "tenant": [
            "*:read",
            "*:write",
            "*:admin",
            "*:delete",
            "users:admin",
        ],
        "team": [
            "*:read",
            "*:write",
            "teams:admin",
        ],
    },
    "maintainer": {
        "global": [
            "*:read",
            "*:write",
            "teams:read",
        ],
        "tenant": [
            "*:read",
            "*:write",
        ],
        "team": [
            "*:read",
            "*:write",
        ],
    },
    "viewer": {
        "global": ["*:read"],
        "tenant": ["*:read"],
        "team":   ["*:read"],
    },
}


# ---------------------------------------------------------------------------
# Public helper functions
# ---------------------------------------------------------------------------

def expand_role_to_scopes(
    role: str,
    layer: str = "global",
    db: Any = None,
) -> list[str]:
    """Return the list of scope strings granted to *role* at *layer*.

    Resolution order:

    1. If *db* is provided, query the ``role_scope_bundles`` table for a row
       matching ``(role, layer)``.  If found, use the stored ``scopes`` value
       (expected to be a list already or a space-delimited string).
    2. Fall back to :data:`ROLE_SCOPE_BUNDLES`.
    3. Return an empty list for any unrecognised role / layer combination.

    Args:
        role:  Role name (e.g. ``"admin"``, ``"viewer"``).
        layer: Scope layer — ``"global"``, ``"tenant"``, or ``"team"``.
        db:    Optional PyDAL ``DAL`` instance.  When *None* the built-in
               bundles are used exclusively.

    Returns:
        A list of scope strings (e.g. ``["*:read", "*:write"]``).
    """
    if db is not None:
        try:
            row = db(
                (db.role_scope_bundles.role == role)
                & (db.role_scope_bundles.layer == layer)
            ).select(db.role_scope_bundles.scopes).first()

            if row is not None:
                raw = row.scopes
                if isinstance(raw, list):
                    return list(raw)
                if isinstance(raw, str):
                    return parse_scope_string(raw)
        except Exception:  # noqa: BLE001 — DB may not have the table yet
            pass

    role_entry = ROLE_SCOPE_BUNDLES.get(role)
    if role_entry is None:
        return []

    return list(role_entry.get(layer, []))


def scope_matches(required: str, available: str) -> bool:
    """Return ``True`` when *available* satisfies the *required* scope.

    Matching rules:

    * Exact match: ``"policies:read"`` satisfies ``"policies:read"``.
    * Wildcard resource: ``"*:read"`` satisfies ``"policies:read"`` (and any
      other ``<resource>:read``).
    * Full wildcard: ``"*:*"`` satisfies everything.
    * The resource segment of *required* is never wildcarded here — callers
      must enumerate concrete required scopes.

    Args:
        required:  The scope that must be granted (e.g. ``"policies:read"``).
        available: A scope held by the principal (e.g. ``"*:read"``).

    Returns:
        ``True`` if *available* covers *required*.
    """
    if available == required:
        return True

    avail_resource, _, avail_action = available.partition(":")
    req_resource,   _, req_action   = required.partition(":")

    # "*:*" matches anything
    if avail_resource == "*" and avail_action == "*":
        return True

    # "*:<action>" matches any resource with the same action
    if avail_resource == "*" and avail_action == req_action:
        return True

    # "<resource>:*" matches any action on the same resource
    if avail_resource == req_resource and avail_action == "*":
        return True

    return False


def has_required_scopes(
    required_scopes: list[str],
    user_scopes: list[str],
) -> bool:
    """Return ``True`` only when *user_scopes* satisfies **all** *required_scopes*.

    Each entry in *required_scopes* is checked against the full *user_scopes*
    list via :func:`scope_matches`; the principal must have at least one
    matching grant for every required scope.

    Args:
        required_scopes: Scopes the endpoint or action demands.
        user_scopes:     Scopes carried by the authenticated principal.

    Returns:
        ``True`` if every required scope is covered.
    """
    for required in required_scopes:
        if not any(scope_matches(required, available) for available in user_scopes):
            return False
    return True


def parse_scope_string(scope_string: str) -> list[str]:
    """Split a space-delimited RFC 9068 scope string into individual scopes.

    Empty tokens produced by consecutive spaces are discarded.

    Args:
        scope_string: A string such as ``"policies:read users:write *:admin"``.

    Returns:
        A list such as ``["policies:read", "users:write", "*:admin"]``.
    """
    return [s for s in scope_string.split(" ") if s]
