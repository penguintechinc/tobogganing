"""Create test schedules table for WaddlePerf client.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-09 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create test_schedules table."""
    op.create_table(
        "test_schedules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("org_unit_id", sa.String(36), nullable=True, index=True),
        sa.Column("test_type", sa.String(50), nullable=False),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_test_schedules"),
        sa.UniqueConstraint(
            "tenant",
            "org_unit_id",
            "test_type",
            "target",
            name="uq_test_schedules_tenant_ou_type_target",
        ),
    )
    # Index for common queries: tenant + org_unit_id
    op.create_index(
        "ix_test_schedules_tenant_ou",
        "test_schedules",
        ["tenant", "org_unit_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop test_schedules table."""
    op.drop_index("ix_test_schedules_tenant_ou", "test_schedules")
    op.drop_table("test_schedules")
