"""Add SASE orchestrator tables (clusters, clients).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-09 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create clusters and clients tables for SASE orchestrator."""
    # Create clusters table
    op.create_table(
        "clusters",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("datacenter", sa.String(100), nullable=False),
        sa.Column("headend_url", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("last_heartbeat", sa.DateTime(), nullable=False),
        sa.Column("client_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_clusters"),
        sa.UniqueConstraint("tenant", "id", name="uq_clusters_tenant_id"),
    )
    op.create_index("ix_clusters_tenant", "clusters", ["tenant"], unique=False)
    op.create_index("ix_clusters_region", "clusters", ["region"], unique=False)
    op.create_index("ix_clusters_datacenter", "clusters", ["datacenter"], unique=False)

    # Create clients table
    op.create_table(
        "clients",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("cluster_id", sa.String(255), nullable=False),
        sa.Column("api_key_hash", sa.String(255), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_clients"),
        sa.UniqueConstraint("tenant", "id", name="uq_clients_tenant_id"),
        sa.UniqueConstraint("api_key_hash", name="uq_clients_api_key_hash"),
    )
    op.create_index("ix_clients_tenant", "clients", ["tenant"], unique=False)
    op.create_index("ix_clients_cluster_id", "clients", ["cluster_id"], unique=False)
    op.create_index("ix_clients_api_key_hash", "clients", ["api_key_hash"], unique=False)


def downgrade() -> None:
    """Drop clusters and clients tables."""
    op.drop_index("ix_clients_api_key_hash", table_name="clients")
    op.drop_index("ix_clients_cluster_id", table_name="clients")
    op.drop_index("ix_clients_tenant", table_name="clients")
    op.drop_table("clients")

    op.drop_index("ix_clusters_datacenter", table_name="clusters")
    op.drop_index("ix_clusters_region", table_name="clusters")
    op.drop_index("ix_clusters_tenant", table_name="clusters")
    op.drop_table("clusters")
