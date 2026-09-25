"""Add SASE block_routes table for block routing configuration.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create block_routes table for SASE module."""
    op.create_table(
        "block_routes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(255), nullable=False),
        sa.Column("destination_kind", sa.String(20), nullable=False),
        sa.Column("page_id", sa.String(36), nullable=True),
        sa.Column("external_url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("ticket", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("expiry", sa.DateTime(), nullable=True),
        sa.Column("review_date", sa.DateTime(), nullable=True),
        sa.Column("scope", sa.String(255), nullable=True),
        sa.Column("risk", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_block_routes"),
    )
    op.create_index("ix_block_routes_tenant", "block_routes", ["tenant"], unique=False)
    op.create_index(
        "ix_block_routes_tenant_source_type",
        "block_routes",
        ["tenant", "source_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop block_routes table."""
    op.drop_index("ix_block_routes_tenant_source_type", table_name="block_routes")
    op.drop_index("ix_block_routes_tenant", table_name="block_routes")
    op.drop_table("block_routes")
