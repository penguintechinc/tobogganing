"""Add dns_zones.allowed_teams; move global threat feeds to the system tenant.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-27 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_NIL = "00000000-0000-0000-0000-000000000000"
_SYSTEM = "system"
# Fixed table names (not user input) that hold global threat-feed rows.
_GLOBAL_FEED_TABLES = ("threat_indicators", "feed_updates")


def upgrade() -> None:
    """Add allowed_teams (JSON array of team UUIDs) to dns_zones.

    The resolver's SelectiveRouter filters internal/restricted zones by the
    caller's JWT ``teams`` claim against this list; empty means no restriction
    for ``internal`` and deny-all for ``restricted``.
    """
    with op.batch_alter_table("dns_zones") as batch:
        batch.add_column(
            sa.Column("allowed_teams", sa.JSON(), nullable=False, server_default="[]")
        )


    # Global threat feeds move from the legacy nil-UUID tenant to the reserved
    # operator-plane "system" tenant.
    for table in _GLOBAL_FEED_TABLES:
        op.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :new WHERE tenant_id = :old").bindparams(
                new=_SYSTEM, old=_NIL
            )
        )


def downgrade() -> None:
    """Drop dns_zones.allowed_teams; restore the nil-UUID global feed tenant."""
    for table in _GLOBAL_FEED_TABLES:
        op.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :old WHERE tenant_id = :new").bindparams(
                new=_SYSTEM, old=_NIL
            )
        )
    with op.batch_alter_table("dns_zones") as batch:
        batch.drop_column("allowed_teams")
