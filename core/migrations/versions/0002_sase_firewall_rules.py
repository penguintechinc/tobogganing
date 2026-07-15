"""Add SASE firewall_rules table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create firewall_rules table for SASE module."""
    op.create_table(
        "firewall_rules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("access_type", sa.String(20), nullable=False),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("src_ip", sa.String(100), nullable=True),
        sa.Column("dst_ip", sa.String(100), nullable=True),
        sa.Column("protocol", sa.String(20), nullable=True),
        sa.Column("src_port", sa.String(100), nullable=True),
        sa.Column("dst_port", sa.String(100), nullable=True),
        sa.Column("direction", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_firewall_rules"),
    )
    op.create_index("ix_firewall_rules_tenant", "firewall_rules", ["tenant"], unique=False)
    op.create_index("ix_firewall_rules_user_id", "firewall_rules", ["user_id"], unique=False)
    op.create_index("ix_firewall_rules_is_active", "firewall_rules", ["is_active", "priority"], unique=False)


def downgrade() -> None:
    """Drop firewall_rules table."""
    op.drop_index("ix_firewall_rules_is_active", table_name="firewall_rules")
    op.drop_index("ix_firewall_rules_user_id", table_name="firewall_rules")
    op.drop_index("ix_firewall_rules_tenant", table_name="firewall_rules")
    op.drop_table("firewall_rules")
