"""Create notification_channels and notification_deliveries tables.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create notification tables."""
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notification_channels"),
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("channel_id", sa.String(36), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notification_deliveries"),
    )


def downgrade() -> None:
    """Drop notification tables."""
    op.drop_table("notification_deliveries")
    op.drop_table("notification_channels")
