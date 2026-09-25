"""Create devices and enrollment tables for WaddlePerf cluster.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-09 15:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create devices, device_api_keys, and device_enrollment_secrets tables."""
    # Create devices table
    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("org_unit_id", sa.String(36), nullable=True, index=True),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("serial", sa.String(255), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("os", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="offline", index=True),
        sa.Column("last_heartbeat", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("tenant", "serial", name="uq_devices_tenant_serial"),
    )

    # Create device_api_keys table
    op.create_table(
        "device_api_keys",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("device_id", sa.String(36), nullable=False, index=True),
        sa.Column("api_key_hash", sa.String(255), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_device_api_keys"),
    )

    # Create device_enrollment_secrets table
    op.create_table(
        "device_enrollment_secrets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False, index=True),
        sa.Column("org_unit_id", sa.String(36), nullable=True, index=True),
        sa.Column("secret_hash", sa.String(255), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_device_enrollment_secrets"),
    )


def downgrade() -> None:
    """Drop devices, device_api_keys, and device_enrollment_secrets tables."""
    op.drop_table("device_enrollment_secrets")
    op.drop_table("device_api_keys")
    op.drop_table("devices")
