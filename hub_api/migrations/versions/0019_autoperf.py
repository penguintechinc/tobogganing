"""Create autoperf_policies and autoperf_state tables.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-14 18:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create autoperf tables."""
    op.create_table(
        "autoperf_policies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("t1_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("t2_interval_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("t3_interval_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("deescalate_after_clean", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_autoperf_policies"),
    )

    op.create_table(
        "autoperf_state",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("policy_id", sa.String(36), nullable=False, unique=True),
        sa.Column("current_tier", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("clean_cycles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_cycle_at", sa.DateTime(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_autoperf_state"),
    )


def downgrade() -> None:
    """Drop autoperf tables."""
    op.drop_table("autoperf_state")
    op.drop_table("autoperf_policies")
