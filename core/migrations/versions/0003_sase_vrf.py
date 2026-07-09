"""Add SASE VRF and OSPF tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create VRF, OSPF area, and OSPF neighbor tables for SASE module."""
    # Create vrfs table
    op.create_table(
        "vrfs",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rd", sa.String(50), nullable=False),
        sa.Column("rt_import", sa.Text(), nullable=True),
        sa.Column("rt_export", sa.Text(), nullable=True),
        sa.Column("ip_ranges", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="inactive"),
        sa.Column("ospf_enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("ospf_router_id", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_vrfs"),
        sa.UniqueConstraint("name", name="uq_vrfs_name"),
    )
    op.create_index("ix_vrfs_tenant", "vrfs", ["tenant"], unique=False)
    op.create_index("ix_vrfs_name", "vrfs", ["name"], unique=False)
    op.create_index("ix_vrfs_is_active", "vrfs", ["is_active"], unique=False)

    # Create ospf_areas table
    op.create_table(
        "ospf_areas",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("vrf_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("area_id", sa.String(20), nullable=False),
        sa.Column("area_type", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("networks", sa.Text(), nullable=True),
        sa.Column("auth_type", sa.String(20), nullable=True),
        sa.Column("auth_key", sa.String(255), nullable=True),
        sa.Column("stub_default_cost", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ospf_areas"),
    )
    op.create_index("ix_ospf_areas_tenant", "ospf_areas", ["tenant"], unique=False)
    op.create_index("ix_ospf_areas_vrf_id", "ospf_areas", ["vrf_id"], unique=False)

    # Create ospf_neighbors table
    op.create_table(
        "ospf_neighbors",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column("vrf_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("neighbor_id", sa.String(50), nullable=False),
        sa.Column("neighbor_ip", sa.String(50), nullable=False),
        sa.Column("interface", sa.String(50), nullable=False),
        sa.Column("area_id", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="Down"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dead_interval", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("hello_interval", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ospf_neighbors"),
    )
    op.create_index("ix_ospf_neighbors_tenant", "ospf_neighbors", ["tenant"], unique=False)
    op.create_index("ix_ospf_neighbors_vrf_id", "ospf_neighbors", ["vrf_id"], unique=False)


def downgrade() -> None:
    """Drop VRF, OSPF area, and OSPF neighbor tables."""
    op.drop_index("ix_ospf_neighbors_vrf_id", table_name="ospf_neighbors")
    op.drop_index("ix_ospf_neighbors_tenant", table_name="ospf_neighbors")
    op.drop_table("ospf_neighbors")

    op.drop_index("ix_ospf_areas_vrf_id", table_name="ospf_areas")
    op.drop_index("ix_ospf_areas_tenant", table_name="ospf_areas")
    op.drop_table("ospf_areas")

    op.drop_index("ix_vrfs_is_active", table_name="vrfs")
    op.drop_index("ix_vrfs_name", table_name="vrfs")
    op.drop_index("ix_vrfs_tenant", table_name="vrfs")
    op.drop_table("vrfs")
