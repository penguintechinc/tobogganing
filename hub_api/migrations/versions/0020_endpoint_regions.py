"""Add region/visibility/health columns to c2c_endpoints.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-14 18:30:00.000000

Columns added:
  - visibility: String(16) NOT NULL default 'private'
  - provider: String(64) NULL
  - health_status: String(16) NOT NULL default 'unknown'
  - last_health_check: DateTime NULL

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add region/visibility/health columns to c2c_endpoints."""
    op.add_column(
        "c2c_endpoints",
        sa.Column(
            "visibility",
            sa.String(16),
            nullable=False,
            server_default="private",
        ),
    )
    op.add_column(
        "c2c_endpoints",
        sa.Column(
            "provider",
            sa.String(64),
            nullable=True,
        ),
    )
    op.add_column(
        "c2c_endpoints",
        sa.Column(
            "health_status",
            sa.String(16),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "c2c_endpoints",
        sa.Column(
            "last_health_check",
            sa.DateTime(),
            nullable=True,
        ),
    )

    # Index for region queries
    op.create_index(
        "ix_c2c_endpoints_visibility",
        "c2c_endpoints",
        ["visibility"],
        unique=False,
    )


def downgrade() -> None:
    """Remove region/visibility/health columns from c2c_endpoints."""
    op.drop_index("ix_c2c_endpoints_visibility", "c2c_endpoints")
    op.drop_column("c2c_endpoints", "last_health_check")
    op.drop_column("c2c_endpoints", "health_status")
    op.drop_column("c2c_endpoints", "provider")
    op.drop_column("c2c_endpoints", "visibility")
