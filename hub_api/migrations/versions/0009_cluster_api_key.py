"""Add per-cluster API key hash for authentication.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-09 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add api_key_hash column to clusters table for per-cluster authentication."""
    # SQLite requires batch mode for column additions with index
    with op.batch_alter_table("clusters", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("api_key_hash", sa.String(255), nullable=True, index=True)
        )


def downgrade() -> None:
    """Remove api_key_hash column from clusters table."""
    with op.batch_alter_table("clusters", schema=None) as batch_op:
        batch_op.drop_column("api_key_hash")
