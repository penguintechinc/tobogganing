"""Add attestation composite hash index on clients.config JSON field.

Revision ID: 001_attestation
Revises: None
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa

revision = "001_attestation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL / MariaDB virtual generated column + index on the attestation
    # composite_hash stored inside the clients.config JSON field.
    # This enables fast lookups by fingerprint hash without schema changes.
    op.execute(
        """
        ALTER TABLE clients
        ADD COLUMN attestation_hash VARCHAR(64) GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(config, '$.attestation.fingerprint.composite_hash'))
        ) VIRTUAL
        """
    )
    op.create_index(
        "ix_clients_attestation_hash",
        "clients",
        ["attestation_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_clients_attestation_hash", table_name="clients")
    op.execute("ALTER TABLE clients DROP COLUMN attestation_hash")
