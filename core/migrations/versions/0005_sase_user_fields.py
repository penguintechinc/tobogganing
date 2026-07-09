"""Add role column to users and create sessions table for SASE auth.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add role column to users table and create sessions table."""
    # Add role column to users table
    op.add_column(
        "users",
        sa.Column("role", sa.String(50), nullable=True, server_default="reporter"),
    )

    # Create sessions table for SASE auth
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_tenant", "sessions", ["tenant"], unique=False)
    op.create_index("ix_sessions_token", "sessions", ["token"], unique=False)


def downgrade() -> None:
    """Drop sessions table and remove role column from users."""
    op.drop_index("ix_sessions_token", table_name="sessions")
    op.drop_index("ix_sessions_tenant", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_column("users", "role")
