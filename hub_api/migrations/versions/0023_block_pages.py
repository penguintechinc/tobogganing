"""Add SASE block_pages table for enforcement customization.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create block_pages table for SASE module."""
    op.create_table(
        "block_pages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_block_pages"),
    )
    op.create_index("ix_block_pages_tenant", "block_pages", ["tenant"], unique=False)
    op.create_index("ix_block_pages_tenant_name", "block_pages", ["tenant", "name"], unique=False)


def downgrade() -> None:
    """Drop block_pages table."""
    op.drop_index("ix_block_pages_tenant_name", table_name="block_pages")
    op.drop_index("ix_block_pages_tenant", table_name="block_pages")
    op.drop_table("block_pages")
