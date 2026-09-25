"""Add domain_categories table for SWG category-to-domain mapping.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create domain_categories table for SWG module."""
    op.create_table(
        "domain_categories",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("categories", sa.Text(), nullable=False),  # JSON array
        sa.Column("source", sa.String(50), nullable=False),  # feed name or "custom"
        sa.Column("tenant", sa.String(255), nullable=True),  # NULL for global feeds, set for custom
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_domain_categories"),
    )
    op.create_index("ix_domain_categories_domain", "domain_categories", ["domain"], unique=False)
    op.create_index(
        "ix_domain_categories_source", "domain_categories", ["source"], unique=False
    )
    op.create_index("ix_domain_categories_tenant", "domain_categories", ["tenant"], unique=False)
    op.create_index(
        "ix_domain_categories_domain_source_tenant",
        "domain_categories",
        ["domain", "source", "tenant"],
        unique=False,
    )


def downgrade() -> None:
    """Drop domain_categories table."""
    op.drop_index(
        "ix_domain_categories_domain_source_tenant", table_name="domain_categories"
    )
    op.drop_index("ix_domain_categories_tenant", table_name="domain_categories")
    op.drop_index("ix_domain_categories_source", table_name="domain_categories")
    op.drop_index("ix_domain_categories_domain", table_name="domain_categories")
    op.drop_table("domain_categories")
