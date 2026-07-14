"""Create scheduled_jobs table for core scheduler.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create scheduled_jobs table."""
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(36), nullable=False, index=True),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_jobs"),
    )
    # Index for sweep queries: tenant + next_run_at for due jobs
    op.create_index(
        "ix_scheduled_jobs_tenant_next_run",
        "scheduled_jobs",
        ["tenant", "next_run_at"],
        unique=False,
    )
    # Index for module/job_type filtering
    op.create_index(
        "ix_scheduled_jobs_module_type",
        "scheduled_jobs",
        ["module", "job_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop scheduled_jobs table."""
    op.drop_index("ix_scheduled_jobs_module_type", "scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_tenant_next_run", "scheduled_jobs")
    op.drop_table("scheduled_jobs")
