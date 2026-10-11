"""Add locations_raw text[] column to job_posting.

Stores the raw location strings from the monitor/scraper so we can
do country-based filtering without requiring the GeoNames location table.

Revision ID: 0008
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE job_posting ADD COLUMN IF NOT EXISTS locations_raw text[]")


def downgrade() -> None:
    op.execute("ALTER TABLE job_posting DROP COLUMN IF EXISTS locations_raw")
