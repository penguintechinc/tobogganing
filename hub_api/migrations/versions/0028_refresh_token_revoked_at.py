"""Add revoked_at to refresh_tokens for single-use rotation + replay detection.

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-01 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable revoked_at timestamp to refresh_tokens.

    NULL means the token has not yet been consumed/rotated; a non-NULL value
    means it was already used once and any further presentation of it is a
    replay attempt (security-review finding HIGH-A: refresh tokens must be
    single-use and rotated on every refresh).
    """
    op.add_column(
        "refresh_tokens",
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Drop revoked_at from refresh_tokens."""
    op.drop_column("refresh_tokens", "revoked_at")
