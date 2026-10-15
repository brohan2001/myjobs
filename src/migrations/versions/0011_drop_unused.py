"""Drop schema nothing uses: the notice-period columns (feature cut, D26) and jobseek's
IndexNow and exporter tables (we don't publish to IndexNow or export snapshots).

Revision ID: 0011
Create Date: 2026-10-15
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE job_posting
            DROP COLUMN IF EXISTS notice_max_days,
            DROP COLUMN IF EXISTS notice_desc_hash
    """)
    op.execute("DROP TABLE IF EXISTS indexnow_submission")
    op.execute("DROP TABLE IF EXISTS exporter_state")


def downgrade() -> None:
    # The dropped data was derived or unused; recreate only the notice columns.
    op.execute("""
        ALTER TABLE job_posting
            ADD COLUMN IF NOT EXISTS notice_max_days SMALLINT,
            ADD COLUMN IF NOT EXISTS notice_desc_hash BIGINT
    """)
