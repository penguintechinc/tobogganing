"""Create C2C endpoints table.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create c2c_endpoints table."""
    op.create_table(
        "c2c_endpoints",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("region", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("engine_url", sa.String(500), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("api_key_hash", sa.String(255), nullable=True, index=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_c2c_endpoints"),
        sa.UniqueConstraint(
            "tenant",
            "region",
            "name",
            name="uq_c2c_endpoints_tenant_region_name",
        ),
    )
    # Index for common queries: tenant + region
    op.create_index(
        "ix_c2c_endpoints_tenant_region",
        "c2c_endpoints",
        ["tenant", "region"],
        unique=False,
    )


def downgrade() -> None:
    """Drop c2c_endpoints table."""
    op.drop_index("ix_c2c_endpoints_tenant_region", "c2c_endpoints")
    op.drop_table("c2c_endpoints")
