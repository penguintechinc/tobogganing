"""Add threatintel_feed_sources table for user-managed feed sources.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-20 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create threatintel_feed_sources table.

    Represents a user-configured threat-intel feed source (MISP/STIX/TAXII/CSV)
    that can be listed, created, deleted, and manually refreshed. Distinct from
    the hardcoded built-in feeds (Blackweb/Spamhaus/IPVoid/DNSBL) driven by
    SecurityFeedsManager.feed_configs, which need no persistent configuration.
    """
    op.create_table(
        "threatintel_feed_sources",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
        sa.Column("last_refresh_status", sa.String(16), nullable=True),
        sa.Column("last_refresh_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_threatintel_feed_sources"),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_threatintel_feed_sources_tenant_name"
        ),
    )
    op.create_index(
        "ix_threatintel_feed_sources_tenant_id",
        "threatintel_feed_sources",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_threatintel_feed_sources_source_type",
        "threatintel_feed_sources",
        ["source_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop threatintel_feed_sources table."""
    op.drop_index(
        "ix_threatintel_feed_sources_source_type", table_name="threatintel_feed_sources"
    )
    op.drop_index(
        "ix_threatintel_feed_sources_tenant_id", table_name="threatintel_feed_sources"
    )
    op.drop_table("threatintel_feed_sources")
