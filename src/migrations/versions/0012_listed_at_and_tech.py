"""Real posting dates and the tech flag.

- ``posted_at``: the ATS's own publish date, when the monitor or page gives one.
- ``listed_at``: what the feed sorts and shows. The publish date, but never later than when we
  first saw the job (a future or bogus date can't jump the queue); ``first_seen_at`` without one.
- ``is_tech`` (D27): false for postings whose scraped title isn't tech-adjacent. Rich monitors
  drop non-tech jobs before storing them; URL-only ones are judged after their one scrape.

Revision ID: 0012
Create Date: 2026-10-15
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE job_posting
            ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS is_tech BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN IF NOT EXISTS listed_at TIMESTAMPTZ
                GENERATED ALWAYS AS (LEAST(COALESCE(posted_at, first_seen_at), first_seen_at)) STORED
    """)
    op.execute("DROP INDEX IF EXISTS idx_jp_feed")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jp_feed "
        "ON job_posting (listed_at DESC, id DESC) WHERE is_active AND is_tech"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jp_feed")
    op.execute("ALTER TABLE job_posting DROP COLUMN IF EXISTS listed_at")
    op.execute("ALTER TABLE job_posting DROP COLUMN IF EXISTS is_tech, DROP COLUMN IF EXISTS posted_at")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jp_feed "
        "ON job_posting (first_seen_at DESC, id DESC) WHERE is_active"
    )
