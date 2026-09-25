"""Create test results, configs, and server keys tables for WaddlePerf.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-09 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create perf_test_results, client_configs, and server_keys tables."""
    # Create perf_test_results table
    op.create_table(
        "perf_test_results",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("device_id", sa.String(36), nullable=False, index=True),
        sa.Column("test_type", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("throughput", sa.Float(), nullable=True),
        sa.Column("test_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_perf_test_results"),
    )
    # Create composite indexes for common queries
    op.create_index("idx_perf_test_results_tenant_device", "perf_test_results", ["tenant", "device_id"], unique=False)
    op.create_index("idx_perf_test_results_tenant_type", "perf_test_results", ["tenant", "test_type"], unique=False)

    # Create client_configs table
    op.create_table(
        "client_configs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("org_unit_id", sa.String(36), nullable=True, index=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_client_configs"),
    )

    # Create server_keys table
    op.create_table(
        "server_keys",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("key_id", sa.String(255), nullable=False, index=True),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_server_keys"),
    )


def downgrade() -> None:
    """Drop perf_test_results, client_configs, and server_keys tables."""
    op.drop_table("server_keys")
    op.drop_table("client_configs")
    op.drop_index("idx_perf_test_results_tenant_type", "perf_test_results")
    op.drop_index("idx_perf_test_results_tenant_device", "perf_test_results")
    op.drop_table("perf_test_results")
