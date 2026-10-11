"""Notice period: the longest notice a posting accepts (days; 0 = immediate joiners).

Filled out-of-band by ``src/processing/notice.py`` from the stored description, so the
positional monitor/scrape write paths stay untouched. ``notice_desc_hash`` records which
description version was parsed; a changed description is re-parsed.

Revision ID: 0010
Create Date: 2026-10-12
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE job_posting
            ADD COLUMN IF NOT EXISTS notice_max_days SMALLINT,
            ADD COLUMN IF NOT EXISTS notice_desc_hash BIGINT
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE job_posting
            DROP COLUMN IF EXISTS notice_max_days,
            DROP COLUMN IF EXISTS notice_desc_hash
    """)
