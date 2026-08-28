"""Create auto_checkins and auto_checkin_state tables.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create auto_checkins and auto_checkin_state tables."""
    op.create_table(
        "auto_checkins",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("test_types", sa.Text(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("jitter_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("samples_per_run", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("threshold_stddev_min", sa.Float(), nullable=True),
        sa.Column("threshold_stddev_max", sa.Float(), nullable=True),
        sa.Column("threshold_mean", sa.Float(), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_checkin_id", sa.String(36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_auto_checkins"),
    )
    op.create_index(
        "ix_auto_checkins_parent", "auto_checkins", ["parent_checkin_id"], unique=False,
    )

    op.create_table(
        "auto_checkin_state",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("checkin_id", sa.String(36), nullable=False, unique=True),
        sa.Column("last_breached", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_mean_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_stddev_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_auto_checkin_state"),
    )


def downgrade() -> None:
    """Drop auto_checkin_state and auto_checkins tables."""
    op.drop_table("auto_checkin_state")
    op.drop_index("ix_auto_checkins_parent", table_name="auto_checkins")
    op.drop_table("auto_checkins")
