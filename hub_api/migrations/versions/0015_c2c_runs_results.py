"""Create C2C matrix runs and pair results tables.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-10 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create c2c_matrix_runs and c2c_pair_results tables."""
    # Create c2c_matrix_runs table
    op.create_table(
        "c2c_matrix_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("test_types", sa.JSON(), nullable=True),
        sa.Column("total_pairs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_pairs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_pairs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_c2c_matrix_runs"),
    )
    # Index for common queries: tenant + status
    op.create_index(
        "ix_c2c_matrix_runs_tenant_status",
        "c2c_matrix_runs",
        ["tenant", "status"],
        unique=False,
    )

    # Create c2c_pair_results table
    op.create_table(
        "c2c_pair_results",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("run_id", sa.String(36), nullable=False, index=True),
        sa.Column("source_endpoint_id", sa.String(36), nullable=False),
        sa.Column("dest_endpoint_id", sa.String(36), nullable=False),
        sa.Column("source_region", sa.String(100), nullable=False),
        sa.Column("dest_region", sa.String(100), nullable=False),
        sa.Column("test_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("throughput", sa.Float(), nullable=True),
        sa.Column("loss_pct", sa.Float(), nullable=True),
        sa.Column("test_output", sa.Text(), nullable=True),
        sa.Column("measured_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_c2c_pair_results"),
        sa.UniqueConstraint(
            "tenant",
            "run_id",
            "source_endpoint_id",
            "dest_endpoint_id",
            "test_type",
            name="uq_c2c_pair_results_tenant_run_endpoints_type",
        ),
    )
    # Index for common queries: tenant + run_id
    op.create_index(
        "ix_c2c_pair_run",
        "c2c_pair_results",
        ["tenant", "run_id"],
        unique=False,
    )
    # Index for region queries
    op.create_index(
        "ix_c2c_pair_regions",
        "c2c_pair_results",
        ["tenant", "source_region", "dest_region"],
        unique=False,
    )


def downgrade() -> None:
    """Drop c2c_matrix_runs and c2c_pair_results tables."""
    op.drop_index("ix_c2c_pair_regions", "c2c_pair_results")
    op.drop_index("ix_c2c_pair_run", "c2c_pair_results")
    op.drop_table("c2c_pair_results")
    op.drop_index("ix_c2c_matrix_runs_tenant_status", "c2c_matrix_runs")
    op.drop_table("c2c_matrix_runs")
