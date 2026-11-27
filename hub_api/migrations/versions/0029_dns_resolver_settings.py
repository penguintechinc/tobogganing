"""Add per-tenant dns_resolver_settings (cache + resolver behaviour).

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-27 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create dns_resolver_settings, one row per tenant.

    Replaces the hardcoded cache/settings block ConfigService used to push to
    resolvers; a tenant without a row gets the column server defaults.
    """
    op.create_table(
        "dns_resolver_settings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("cache_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cache_ttl", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("cache_max_entries", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("log_queries", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enable_dnssec", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ioc_filtering", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dns_resolver_settings"),
        sa.UniqueConstraint("tenant", name="uq_dns_resolver_settings_tenant"),
    )


def downgrade() -> None:
    """Drop dns_resolver_settings."""
    op.drop_table("dns_resolver_settings")
