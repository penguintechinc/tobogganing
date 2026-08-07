"""Add category_policies table for SWG category-to-action policy mapping.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create category_policies table for SWG module."""
    op.create_table(
        "category_policies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(50), nullable=False),  # "tenant", "group", "user"
        sa.Column("scope_id", sa.String(255), nullable=True),  # group_id or user_id
        sa.Column("category", sa.String(255), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),  # allow, log_only, soft_block, block, drop
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_category_policies"),
    )
    op.create_index("ix_category_policies_tenant", "category_policies", ["tenant"], unique=False)
    op.create_index(
        "ix_category_policies_category", "category_policies", ["category"], unique=False
    )
    op.create_index(
        "ix_category_policies_scope",
        "category_policies",
        ["tenant", "scope", "scope_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop category_policies table."""
    op.drop_index("ix_category_policies_scope", table_name="category_policies")
    op.drop_index("ix_category_policies_category", table_name="category_policies")
    op.drop_index("ix_category_policies_tenant", table_name="category_policies")
    op.drop_table("category_policies")
