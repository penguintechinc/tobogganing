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
    # Drop old global unique indexes on users table
    op.drop_index("ix_users_email", table_name="users", if_exists=True)
    op.drop_index("ix_users_username", table_name="users", if_exists=True)

    # Add new per-tenant unique constraints on users
    op.create_unique_constraint(
        "uq_users_tenant_email", "users", ["tenant", "email"]
    )
    op.create_unique_constraint(
        "uq_users_tenant_username", "users", ["tenant", "username"]
    )

    # Recreate indexes (non-unique)
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    # Drop old global unique index on vrfs table
    op.drop_index("ix_vrfs_name", table_name="vrfs", if_exists=True)

    # Add per-tenant unique constraint on vrfs
    op.create_unique_constraint(
        "uq_vrfs_tenant_name", "vrfs", ["tenant", "name"]
    )

    # Recreate index (non-unique)
    op.create_index("ix_vrfs_name", "vrfs", ["name"], unique=False)

    # Add per-tenant uniqueness constraint on ospf_areas
    op.create_unique_constraint(
        "uq_ospf_areas_tenant_vrf_area", "ospf_areas", ["tenant", "vrf_id", "area_id"]
    )


def downgrade() -> None:
    """Revert per-tenant uniqueness constraints."""
    # Drop per-tenant unique constraints
    op.drop_constraint("uq_ospf_areas_tenant_vrf_area", "ospf_areas", type_="unique")
    op.drop_constraint("uq_vrfs_tenant_name", "vrfs", type_="unique")
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    op.drop_constraint("uq_users_tenant_username", "users", type_="unique")

    # Restore old global unique indexes on users (if not already present)
    op.drop_index("ix_users_email", table_name="users", if_exists=True)
    op.drop_index("ix_users_username", table_name="users", if_exists=True)
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_username", "users", ["username"])

    # Restore old global unique index on vrfs (if not already present)
    op.drop_index("ix_vrfs_name", table_name="vrfs", if_exists=True)
    op.create_unique_constraint("uq_vrfs_name", "vrfs", ["name"])
