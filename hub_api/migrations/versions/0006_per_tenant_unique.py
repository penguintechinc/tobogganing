"""Add per-tenant uniqueness constraints.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add per-tenant uniqueness constraints to users, vrfs, and ospf_areas."""
    # SQLite requires batch mode for constraint changes
    with op.batch_alter_table("users", schema=None) as batch_op:
        # Drop old global unique constraints on users table
        try:
            batch_op.drop_constraint("uq_users_email", type_="unique")
        except Exception:
            pass
        try:
            batch_op.drop_constraint("uq_users_username", type_="unique")
        except Exception:
            pass

        # Drop old indexes (will be recreated as non-unique)
        try:
            batch_op.drop_index("ix_users_email")
        except Exception:
            pass
        try:
            batch_op.drop_index("ix_users_username")
        except Exception:
            pass

        # Add new per-tenant unique constraints on users
        batch_op.create_unique_constraint(
            "uq_users_tenant_email", ["tenant", "email"]
        )
        batch_op.create_unique_constraint(
            "uq_users_tenant_username", ["tenant", "username"]
        )

        # Recreate indexes (non-unique)
        batch_op.create_index("ix_users_email", ["email"], unique=False)
        batch_op.create_index("ix_users_username", ["username"], unique=False)

    with op.batch_alter_table("vrfs", schema=None) as batch_op:
        # Drop old global unique constraint on vrfs table
        try:
            batch_op.drop_constraint("uq_vrfs_name", type_="unique")
        except Exception:
            pass

        # Drop old index (will be recreated as non-unique)
        try:
            batch_op.drop_index("ix_vrfs_name")
        except Exception:
            pass

        # Add per-tenant unique constraint on vrfs
        batch_op.create_unique_constraint(
            "uq_vrfs_tenant_name", ["tenant", "name"]
        )

        # Recreate index (non-unique)
        batch_op.create_index("ix_vrfs_name", ["name"], unique=False)

    with op.batch_alter_table("ospf_areas", schema=None) as batch_op:
        # Add per-tenant uniqueness constraint on ospf_areas
        batch_op.create_unique_constraint(
            "uq_ospf_areas_tenant_vrf_area", ["tenant", "vrf_id", "area_id"]
        )


def downgrade() -> None:
    """Revert per-tenant uniqueness constraints."""
    with op.batch_alter_table("ospf_areas", schema=None) as batch_op:
        # Drop per-tenant uniqueness constraint on ospf_areas
        try:
            batch_op.drop_constraint("uq_ospf_areas_tenant_vrf_area", type_="unique")
        except Exception:
            pass

    with op.batch_alter_table("vrfs", schema=None) as batch_op:
        # Drop per-tenant unique constraint on vrfs
        try:
            batch_op.drop_constraint("uq_vrfs_tenant_name", type_="unique")
        except Exception:
            pass

        # Restore old global unique constraint on vrfs
        try:
            batch_op.drop_index("ix_vrfs_name")
        except Exception:
            pass
        batch_op.create_unique_constraint("uq_vrfs_name", ["name"])

    with op.batch_alter_table("users", schema=None) as batch_op:
        # Drop per-tenant unique constraints on users
        try:
            batch_op.drop_constraint("uq_users_tenant_email", type_="unique")
        except Exception:
            pass
        try:
            batch_op.drop_constraint("uq_users_tenant_username", type_="unique")
        except Exception:
            pass

        # Restore old global unique constraints on users
        try:
            batch_op.drop_index("ix_users_email")
        except Exception:
            pass
        try:
            batch_op.drop_index("ix_users_username")
        except Exception:
            pass
        batch_op.create_unique_constraint("uq_users_email", ["email"])
        batch_op.create_unique_constraint("uq_users_username", ["username"])
