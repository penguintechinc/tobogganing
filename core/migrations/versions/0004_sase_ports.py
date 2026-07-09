"""Add SASE port_ranges table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create port_ranges table for SASE module."""
    op.create_table(
        "port_ranges",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("headend_id", sa.String(255), nullable=False),
        sa.Column("cluster_id", sa.String(255), nullable=False),
        sa.Column("start_port", sa.Integer(), nullable=False),
        sa.Column("end_port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_port_ranges"),
    )
    op.create_index("ix_port_ranges_tenant", "port_ranges", ["tenant"], unique=False)
    op.create_index("ix_port_ranges_headend_id", "port_ranges", ["headend_id"], unique=False)
    op.create_index("ix_port_ranges_cluster_id", "port_ranges", ["cluster_id"], unique=False)


def downgrade() -> None:
    """Drop port_ranges table."""
    op.drop_index("ix_port_ranges_cluster_id", table_name="port_ranges")
    op.drop_index("ix_port_ranges_headend_id", table_name="port_ranges")
    op.drop_index("ix_port_ranges_tenant", table_name="port_ranges")
    op.drop_table("port_ranges")
