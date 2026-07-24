"""Create org_units table for WaddlePerf cluster support.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-09 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create org_units table for organizational hierarchy."""
    op.create_table(
        "org_units",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.String(36), nullable=True, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1", index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_org_units"),
        sa.UniqueConstraint("tenant", "name", name="uq_org_units_tenant_name"),
    )


def downgrade() -> None:
    """Drop org_units table."""
    op.drop_table("org_units")
