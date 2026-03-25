"""
Idempotent seed script for Tobogganing hub-api database.

Provides:
  - seed_defaults(db): Create default tenant, role scope bundles, associate users
  - seed_mock_data(db): Create test tenants, teams, and SPIFFE entries
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def seed_defaults(db) -> None:
    """
    Seed default tenant, role scope bundles, and user associations.

    This function is idempotent and safe to call on every app startup.
    It creates:
      1. Default tenant (INSERT OR IGNORE pattern)
      2. Role scope bundles for admin, maintainer, viewer at each layer
      3. Associates orphaned users (tenant_id IS NULL) with default tenant

    Args:
        db: PyDAL DAL instance
    """
    # -------------------------
    # 1. Create default tenant
    # -------------------------
    default_tenant_exists = db(
        db.tenants.tenant_id == "default"
    ).select().first()

    if not default_tenant_exists:
        try:
            db.tenants.insert(
                tenant_id="default",
                name="Default Tenant",
                domain=None,
                spiffe_trust_domain="default.tobogganing.io",
                is_active=True,
                config=None,
            )
            db.commit()
            logger.info("Created default tenant")
        except Exception as e:
            logger.warning(f"Could not create default tenant: {e}")
            db.rollback()
    else:
        logger.debug("Default tenant already exists")

    # -------------------------
    # 2. Create role scope bundles
    # -------------------------
    bundles = {
        ("admin", "global"): [
            "*:read",
            "*:write",
            "*:admin",
            "*:delete",
            "settings:write",
            "users:admin",
            "tenants:admin",
        ],
        ("admin", "tenant"): [
            "*:read",
            "*:write",
            "*:admin",
            "*:delete",
            "users:admin",
        ],
        ("admin", "team"): [
            "*:read",
            "*:write",
            "teams:admin",
        ],
        ("maintainer", "global"): [
            "*:read",
            "*:write",
            "teams:read",
        ],
        ("maintainer", "tenant"): [
            "*:read",
            "*:write",
        ],
        ("maintainer", "team"): [
            "*:read",
            "*:write",
        ],
        ("viewer", "global"): ["*:read"],
        ("viewer", "tenant"): ["*:read"],
        ("viewer", "team"): ["*:read"],
    }

    for (role_name, layer), scopes in bundles.items():
        existing = db(
            (db.role_scope_bundles.role_name == role_name)
            & (db.role_scope_bundles.layer == layer)
        ).select().first()

        if not existing:
            try:
                db.role_scope_bundles.insert(
                    role_name=role_name,
                    layer=layer,
                    scopes=scopes,
                )
                logger.debug(
                    f"Created role scope bundle: {role_name}/{layer}"
                )
            except Exception as e:
                logger.warning(
                    f"Could not create bundle {role_name}/{layer}: {e}"
                )
                db.rollback()

    db.commit()

    # -------------------------
    # 3. Associate orphaned users
    # -------------------------
    try:
        orphaned_users = db(db.users.tenant_id == None).select()
        if orphaned_users:
            for user in orphaned_users:
                db(db.users.id == user.id).update(tenant_id="default")
            db.commit()
            logger.info(
                f"Associated {len(orphaned_users)} orphaned users with default tenant"
            )
    except Exception as e:
        logger.warning(f"Could not associate orphaned users: {e}")
        db.rollback()

    logger.info("Seed defaults completed")


def seed_mock_data(db) -> None:
    """
    Create mock data for development and testing.

    Creates:
      1. Test tenants: acme, globex (default already created by seed_defaults)
      2. Test teams: infra, platform (acme); ops, dev (globex)
      3. Test SPIFFE entries: 3 entries across tenants

    This function is idempotent — it checks for existing data before
    creating duplicates.

    Args:
        db: PyDAL DAL instance
    """
    # -------------------------
    # 1. Create test tenants
    # -------------------------
    tenants = [
        {
            "tenant_id": "acme",
            "name": "ACME Corporation",
            "domain": "acme.example.com",
            "spiffe_trust_domain": "acme.tobogganing.io",
        },
        {
            "tenant_id": "globex",
            "name": "Globex Corporation",
            "domain": "globex.example.com",
            "spiffe_trust_domain": "globex.tobogganing.io",
        },
    ]

    for tenant_data in tenants:
        existing = db(
            db.tenants.tenant_id == tenant_data["tenant_id"]
        ).select().first()

        if not existing:
            try:
                db.tenants.insert(
                    tenant_id=tenant_data["tenant_id"],
                    name=tenant_data["name"],
                    domain=tenant_data["domain"],
                    spiffe_trust_domain=tenant_data["spiffe_trust_domain"],
                    is_active=True,
                    config=None,
                )
                logger.info(f"Created tenant: {tenant_data['tenant_id']}")
            except Exception as e:
                logger.warning(
                    f"Could not create tenant {tenant_data['tenant_id']}: {e}"
                )
                db.rollback()
        else:
            logger.debug(f"Tenant already exists: {tenant_data['tenant_id']}")

    db.commit()

    # -------------------------
    # 2. Create test teams
    # -------------------------
    teams = [
        {
            "team_id": "acme-infra",
            "tenant_id": "acme",
            "name": "infra",
            "description": "ACME infrastructure team",
        },
        {
            "team_id": "acme-platform",
            "tenant_id": "acme",
            "name": "platform",
            "description": "ACME platform team",
        },
        {
            "team_id": "globex-ops",
            "tenant_id": "globex",
            "name": "ops",
            "description": "Globex operations team",
        },
        {
            "team_id": "globex-dev",
            "tenant_id": "globex",
            "name": "dev",
            "description": "Globex development team",
        },
    ]

    for team_data in teams:
        existing = db(db.teams.team_id == team_data["team_id"]).select().first()

        if not existing:
            try:
                db.teams.insert(
                    team_id=team_data["team_id"],
                    tenant_id=team_data["tenant_id"],
                    name=team_data["name"],
                    description=team_data["description"],
                )
                logger.info(f"Created team: {team_data['team_id']}")
            except Exception as e:
                logger.warning(
                    f"Could not create team {team_data['team_id']}: {e}"
                )
                db.rollback()
        else:
            logger.debug(f"Team already exists: {team_data['team_id']}")

    db.commit()

    # -------------------------
    # 3. Create test SPIFFE entries
    # -------------------------
    spiffe_entries = [
        {
            "spiffe_id": "spiffe://acme.tobogganing.io/aws-us-east-1/backend/api-server",
            "tenant_id": "acme",
            "parent_id": None,
            "selectors": [
                {"type": "aws-ec2:instance-id", "value": "i-1234567890abcdef0"},
                {"type": "aws-ec2:region", "value": "us-east-1"},
            ],
            "ttl": 3600,
            "dns_names": ["api.acme.tobogganing.io"],
        },
        {
            "spiffe_id": "spiffe://acme.tobogganing.io/gcp-europe-west1/platform/ingress",
            "tenant_id": "acme",
            "parent_id": None,
            "selectors": [
                {"type": "gcp:project-id", "value": "acme-prod"},
                {"type": "gcp:zone", "value": "europe-west1-b"},
            ],
            "ttl": 3600,
            "dns_names": ["ingress.acme.tobogganing.io"],
        },
        {
            "spiffe_id": "spiffe://globex.tobogganing.io/onprem-dc1/ops/monitoring",
            "tenant_id": "globex",
            "parent_id": None,
            "selectors": [
                {"type": "hostname", "value": "monitoring-node-01"},
                {"type": "datacenter", "value": "dc1"},
            ],
            "ttl": 3600,
            "dns_names": ["monitoring.globex.tobogganing.io"],
        },
    ]

    for entry_data in spiffe_entries:
        existing = db(
            db.spiffe_entries.spiffe_id == entry_data["spiffe_id"]
        ).select().first()

        if not existing:
            try:
                db.spiffe_entries.insert(
                    spiffe_id=entry_data["spiffe_id"],
                    tenant_id=entry_data["tenant_id"],
                    parent_id=entry_data["parent_id"],
                    selectors=entry_data["selectors"],
                    ttl=entry_data["ttl"],
                    dns_names=entry_data["dns_names"],
                )
                logger.info(f"Created SPIFFE entry: {entry_data['spiffe_id']}")
            except Exception as e:
                logger.warning(
                    f"Could not create SPIFFE entry {entry_data['spiffe_id']}: {e}"
                )
                db.rollback()
        else:
            logger.debug(f"SPIFFE entry already exists: {entry_data['spiffe_id']}")

    db.commit()
    logger.info("Mock data seed completed")
