"""
Tenant and Team CRUD routes for Tobogganing Hub API.

All endpoints are scope-gated via :func:`auth.middleware.require_scope`.
All responses use the standard envelope::

    {"status": "success", "data": {...}, "meta": {...}}
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from py4web import action, request, response

from auth.middleware import require_scope
from auth.scopes import parse_scope_string

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _tenant_to_dict(row) -> dict:
    return {
        "tenant_id": row.tenant_id,
        "name": row.name,
        "spiffe_trust_domain": row.spiffe_trust_domain,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _team_to_dict(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "tenant_id": row.tenant_id,
        "description": getattr(row, "description", ""),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _err(status: int, msg: str) -> dict:
    response.status = status
    return {"status": "error", "data": None, "meta": {"error": msg}}


# ---------------------------------------------------------------------------
# Tenant CRUD
# ---------------------------------------------------------------------------

@action("api/v1/tenants", method=["GET"])
@action.uses("json")
@require_scope("tenants:read")
async def list_tenants():
    """List all tenants.  Platform admins see all; tenant users see only their own."""
    try:
        from database import get_read_db
        db = get_read_db()

        # Tenant-scoped callers may only see their own record.
        tenant_ctx = getattr(request, "tenant", None)
        if tenant_ctx:
            query = db(db.tenants.tenant_id == tenant_ctx.tenant_id)
        else:
            query = db(db.tenants)

        rows = query.select(orderby=db.tenants.name)
        tenants = [_tenant_to_dict(r) for r in rows]
        return {
            "status": "success",
            "data": {"tenants": tenants},
            "meta": {"total": len(tenants)},
        }
    except Exception as exc:
        logger.error("list_tenants error", error=str(exc))
        return _err(500, "Internal server error")


@action("api/v1/tenants", method=["POST"])
@action.uses("json")
@require_scope("tenants:write")
async def create_tenant():
    """Create a new tenant (platform admin only)."""
    try:
        data = await request.json()
        required = ["name"]
        for field in required:
            if field not in data:
                return _err(400, f"Missing required field: {field}")

        name = str(data["name"]).strip()
        if not name:
            return _err(400, "name must not be blank")

        tenant_id = data.get("tenant_id") or str(uuid.uuid4())
        spiffe_trust_domain = data.get("spiffe_trust_domain", "")

        from database import get_db
        db = get_db()

        # Uniqueness guard
        existing = db(db.tenants.tenant_id == tenant_id).select().first()
        if existing:
            return _err(409, f"Tenant with id '{tenant_id}' already exists")

        row_id = db.tenants.insert(
            tenant_id=tenant_id,
            name=name,
            spiffe_trust_domain=spiffe_trust_domain,
            is_active=data.get("is_active", True),
        )
        db.commit()

        row = db.tenants[row_id]
        response.status = 201
        return {"status": "success", "data": _tenant_to_dict(row), "meta": {}}
    except Exception as exc:
        logger.error("create_tenant error", error=str(exc))
        return _err(500, "Internal server error")


@action("api/v1/tenants/<tenant_id>", method=["GET"])
@action.uses("json")
@require_scope("tenants:read")
async def get_tenant(tenant_id: str):
    """Fetch a single tenant by tenant_id."""
    try:
        from database import get_read_db
        db = get_read_db()
        row = db(db.tenants.tenant_id == tenant_id).select().first()
        if not row:
            return _err(404, "Tenant not found")

        # Tenant-scoped callers may only read their own record.
        ctx = getattr(request, "tenant", None)
        if ctx and ctx.tenant_id != tenant_id:
            return _err(403, "Access denied")

        return {"status": "success", "data": _tenant_to_dict(row), "meta": {}}
    except Exception as exc:
        logger.error("get_tenant error", error=str(exc))
        return _err(500, "Internal server error")


@action("api/v1/tenants/<tenant_id>", method=["PUT"])
@action.uses("json")
@require_scope("tenants:write")
async def update_tenant(tenant_id: str):
    """Update mutable fields of a tenant."""
    try:
        from database import get_db
        db = get_db()
        row = db(db.tenants.tenant_id == tenant_id).select().first()
        if not row:
            return _err(404, "Tenant not found")

        ctx = getattr(request, "tenant", None)
        if ctx and ctx.tenant_id != tenant_id:
            return _err(403, "Access denied")

        data = await request.json()
        updatable = {"name", "spiffe_trust_domain", "is_active"}
        update_fields = {k: v for k, v in data.items() if k in updatable}

        if "name" in update_fields:
            update_fields["name"] = str(update_fields["name"]).strip()
            if not update_fields["name"]:
                return _err(400, "name must not be blank")

        if update_fields:
            row.update_record(**update_fields)
            db.commit()

        updated = db(db.tenants.tenant_id == tenant_id).select().first()
        return {"status": "success", "data": _tenant_to_dict(updated), "meta": {}}
    except Exception as exc:
        logger.error("update_tenant error", error=str(exc))
        return _err(500, "Internal server error")


@action("api/v1/tenants/<tenant_id>", method=["DELETE"])
@action.uses("json")
@require_scope("tenants:delete")
async def delete_tenant(tenant_id: str):
    """Soft-delete (deactivate) a tenant.  Hard-delete requires platform admin."""
    try:
        from database import get_db
        db = get_db()
        row = db(db.tenants.tenant_id == tenant_id).select().first()
        if not row:
            return _err(404, "Tenant not found")

        ctx = getattr(request, "tenant", None)
        if ctx and ctx.tenant_id != tenant_id:
            return _err(403, "Access denied")

        # Soft-delete: mark inactive
        row.update_record(is_active=False)
        db.commit()
        return {
            "status": "success",
            "data": {"tenant_id": tenant_id, "status": "deactivated"},
            "meta": {},
        }
    except Exception as exc:
        logger.error("delete_tenant error", error=str(exc))
        return _err(500, "Internal server error")


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------

@action("api/v1/teams", method=["GET"])
@action.uses("json")
@require_scope("teams:read")
async def list_teams():
    """List teams.  Tenant-scoped callers see only their tenant's teams."""
    try:
        from database import get_read_db
        db = get_read_db()

        tenant_ctx = getattr(request, "tenant", None)
        if tenant_ctx:
            query = db(db.teams.tenant_id == tenant_ctx.tenant_id)
        else:
            query = db(db.teams)

        rows = query.select(orderby=db.teams.name)
        teams = [_team_to_dict(r) for r in rows]
        return {
            "status": "success",
            "data": {"teams": teams},
            "meta": {"total": len(teams)},
        }
    except Exception as exc:
        logger.error("list_teams error", error=str(exc))
        return _err(500, "Internal server error")


@action("api/v1/teams", method=["POST"])
@action.uses("json")
@require_scope("teams:write")
async def create_team():
    """Create a new team within the caller's tenant."""
    try:
        data = await request.json()
        required = ["name"]
        for field in required:
            if field not in data:
                return _err(400, f"Missing required field: {field}")

        name = str(data["name"]).strip()
        if not name:
            return _err(400, "name must not be blank")

        # Resolve tenant: prefer token context, allow explicit override for admins.
        tenant_ctx = getattr(request, "tenant", None)
        if tenant_ctx:
            tenant_id = tenant_ctx.tenant_id
        elif "tenant_id" in data:
            tenant_id = data["tenant_id"]
        else:
            return _err(400, "tenant_id is required when no tenant context is present")

        from database import get_db
        db = get_db()

        # Uniqueness within tenant
        existing = db(
            (db.teams.tenant_id == tenant_id) & (db.teams.name == name)
        ).select().first()
        if existing:
            return _err(409, f"Team '{name}' already exists in this tenant")

        row_id = db.teams.insert(
            name=name,
            tenant_id=tenant_id,
            description=data.get("description", ""),
        )
        db.commit()

        row = db.teams[row_id]
        response.status = 201
        return {"status": "success", "data": _team_to_dict(row), "meta": {}}
    except Exception as exc:
        logger.error("create_team error", error=str(exc))
        return _err(500, "Internal server error")


@action("api/v1/teams/<team_id:int>", method=["GET"])
@action.uses("json")
@require_scope("teams:read")
async def get_team(team_id: int):
    """Fetch a single team by numeric ID."""
    try:
        from database import get_read_db
        db = get_read_db()
        row = db.teams[team_id]
        if not row:
            return _err(404, "Team not found")

        tenant_ctx = getattr(request, "tenant", None)
        if tenant_ctx and row.tenant_id != tenant_ctx.tenant_id:
            return _err(403, "Access denied")

        return {"status": "success", "data": _team_to_dict(row), "meta": {}}
    except Exception as exc:
        logger.error("get_team error", error=str(exc))
        return _err(500, "Internal server error")


@action("api/v1/teams/<team_id:int>/members", method=["POST"])
@action.uses("json")
@require_scope("teams:admin")
async def add_team_member(team_id: int):
    """Add a user to a team.

    Body: ``{"user_id": "<uuid>", "role": "member|admin"}``
    """
    try:
        from database import get_db
        db = get_db()

        team = db.teams[team_id]
        if not team:
            return _err(404, "Team not found")

        tenant_ctx = getattr(request, "tenant", None)
        if tenant_ctx and team.tenant_id != tenant_ctx.tenant_id:
            return _err(403, "Access denied")

        data = await request.json()
        if "user_id" not in data:
            return _err(400, "Missing required field: user_id")

        user_id = str(data["user_id"]).strip()
        role = data.get("role", "member")
        if role not in ("member", "admin"):
            return _err(400, "role must be 'member' or 'admin'")

        # Verify the user exists
        user = db(db.auth_user.id == user_id).select(db.auth_user.id).first()
        if not user:
            return _err(404, "User not found")

        # Upsert membership
        existing = db(
            (db.team_members.team_id == team_id)
            & (db.team_members.user_id == user_id)
        ).select().first()

        if existing:
            existing.update_record(role=role)
        else:
            db.team_members.insert(
                team_id=team_id,
                user_id=user_id,
                role=role,
            )
        db.commit()

        return {
            "status": "success",
            "data": {
                "team_id": team_id,
                "user_id": user_id,
                "role": role,
            },
            "meta": {},
        }
    except Exception as exc:
        logger.error("add_team_member error", error=str(exc))
        return _err(500, "Internal server error")
