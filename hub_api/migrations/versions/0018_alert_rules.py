"""Create alert_rules and alert_events tables.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-14 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create alert tables."""
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("comparator", sa.String(8), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("device_id", sa.String(36), nullable=True),
        sa.Column("test_type", sa.String(32), nullable=True),
        sa.Column("channel_id", sa.String(36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_alert_rules"),
    )

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=True),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("fired_at", sa.DateTime(), nullable=False),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id", name="pk_alert_events"),
    )


def downgrade() -> None:
    """Drop alert tables."""
    op.drop_table("alert_events")
    op.drop_table("alert_rules")
