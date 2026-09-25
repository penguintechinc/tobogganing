"""Add netsvcs control plane tables for DNS management.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create netsvcs control plane tables."""
    # dns_zones table
    op.create_table(
        "dns_zones",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("visibility", sa.String(50), nullable=False, server_default="public"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dns_zones"),
        sa.UniqueConstraint("tenant", "name", name="uq_dns_zones_tenant_name"),
    )
    op.create_index("ix_dns_zones_tenant", "dns_zones", ["tenant"], unique=False)

    # dns_records table
    op.create_table(
        "dns_records",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("zone_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("value", sa.String(1024), nullable=False),
        sa.Column("ttl", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dns_records"),
        sa.ForeignKeyConstraint(["zone_id"], ["dns_zones.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("zone_id", "name", "type", name="uq_dns_records_zone_name_type"),
    )
    op.create_index("ix_dns_records_tenant", "dns_records", ["tenant"], unique=False)
    op.create_index("ix_dns_records_zone_id", "dns_records", ["zone_id"], unique=False)
    op.create_index("ix_dns_records_zone_name_type", "dns_records", ["zone_id", "name", "type"], unique=False)

    # dns_servers table
    op.create_table(
        "dns_servers",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="offline"),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dns_servers"),
    )
    op.create_index("ix_dns_servers_tenant", "dns_servers", ["tenant"], unique=False)

    # dns_server_metrics table
    op.create_table(
        "dns_server_metrics",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("server_id", sa.String(36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("queries_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_response_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dns_server_metrics"),
        sa.ForeignKeyConstraint(["server_id"], ["dns_servers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("server_id", "timestamp", name="uq_dns_server_metrics_server_timestamp"),
    )
    op.create_index("ix_dns_server_metrics_tenant", "dns_server_metrics", ["tenant"], unique=False)
    op.create_index("ix_dns_server_metrics_server_id", "dns_server_metrics", ["server_id"], unique=False)
    op.create_index("ix_dns_server_metrics_server_timestamp", "dns_server_metrics", ["server_id", "timestamp"], unique=False)

    # dns_resolver_tokens table
    op.create_table(
        "dns_resolver_tokens",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dns_resolver_tokens"),
        sa.UniqueConstraint("token", name="uq_dns_resolver_tokens_token"),
        sa.UniqueConstraint("tenant", "name", name="uq_dns_resolver_tokens_tenant_name"),
    )
    op.create_index("ix_dns_resolver_tokens_tenant", "dns_resolver_tokens", ["tenant"], unique=False)
    op.create_index("ix_dns_resolver_tokens_token", "dns_resolver_tokens", ["token"], unique=False)

    # dns_config_versions table
    op.create_table(
        "dns_config_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("scope_key", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dns_config_versions"),
        sa.UniqueConstraint("tenant", "scope_key", name="uq_dns_config_versions_tenant_scope"),
    )
    op.create_index("ix_dns_config_versions_tenant", "dns_config_versions", ["tenant"], unique=False)


def downgrade() -> None:
    """Drop netsvcs control plane tables."""
    op.drop_index("ix_dns_config_versions_tenant", table_name="dns_config_versions")
    op.drop_table("dns_config_versions")

    op.drop_index("ix_dns_resolver_tokens_token", table_name="dns_resolver_tokens")
    op.drop_index("ix_dns_resolver_tokens_tenant", table_name="dns_resolver_tokens")
    op.drop_table("dns_resolver_tokens")

    op.drop_index("ix_dns_server_metrics_server_timestamp", table_name="dns_server_metrics")
    op.drop_index("ix_dns_server_metrics_server_id", table_name="dns_server_metrics")
    op.drop_index("ix_dns_server_metrics_tenant", table_name="dns_server_metrics")
    op.drop_table("dns_server_metrics")

    op.drop_index("ix_dns_servers_tenant", table_name="dns_servers")
    op.drop_table("dns_servers")

    op.drop_index("ix_dns_records_zone_name_type", table_name="dns_records")
    op.drop_index("ix_dns_records_zone_id", table_name="dns_records")
    op.drop_index("ix_dns_records_tenant", table_name="dns_records")
    op.drop_table("dns_records")

    op.drop_index("ix_dns_zones_tenant", table_name="dns_zones")
    op.drop_table("dns_zones")
