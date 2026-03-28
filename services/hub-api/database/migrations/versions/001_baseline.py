"""001 — baseline: mark existing schema as current.

Revision ID: 001_baseline
Revises:
Create Date: 2025-03-27

This migration is a no-op upgrade / no-op downgrade.  It exists to
establish Alembic version tracking on databases that were originally
created by PyDAL (migrate=True) and already contain the full schema.

New installations should run ``alembic upgrade head`` which will mark
this revision as applied, then any subsequent data-migration revisions
will run on top of it.

If you are migrating a live database from PyDAL:
1. Ensure the schema is up-to-date (all PyDAL-generated tables exist).
2. Run: alembic stamp 001_baseline
3. Future migrations will apply on top of this baseline.
"""

from __future__ import annotations

from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers — used by Alembic
# ---------------------------------------------------------------------------
revision: str = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op — schema already exists for databases migrated from PyDAL.

    For fresh installations Alembic will record this revision, and
    subsequent migrations will create tables from scratch.
    """
    pass


def downgrade() -> None:
    """No-op — cannot roll back the initial baseline."""
    pass
