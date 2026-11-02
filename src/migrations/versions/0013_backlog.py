"""Backlog jobs: undated postings found by a board's first crawl sort after every dated job.

- ``backlog``: set on insert when the board has never had a successful check, or not for 2 days
  (a new board, or one re-enabled after failing, D37). Those crawls return the board's whole backlog,
  and without a publish date every job looked "just posted".
- ``listed_at``: an undated backlog job gets the Unix epoch, so the feed sorts it last and the
  "new in 24 h" count skips it. It turns into a normal job once a later crawl finds its date.
- Backfill: only the last 2 days (the boards re-enabled on 2026-11-02). Older first crawls already
  sit weeks deep in the feed.

Revision ID: 0013
Create Date: 2026-11-02
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_LISTED_AT = "LEAST(COALESCE(posted_at, first_seen_at), first_seen_at)"


def upgrade() -> None:
    op.execute("ALTER TABLE job_posting ADD COLUMN IF NOT EXISTS backlog BOOLEAN NOT NULL DEFAULT false")
    op.execute("""
        CREATE OR REPLACE FUNCTION job_posting_mark_backlog() RETURNS trigger AS $$
        BEGIN
            NEW.backlog := EXISTS (
                SELECT 1 FROM job_board b
                WHERE b.id = NEW.board_id
                  AND (b.last_success_at IS NULL OR b.last_success_at < now() - interval '2 days'));
            RETURN NEW;
        END $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER job_posting_backlog BEFORE INSERT ON job_posting
        FOR EACH ROW EXECUTE FUNCTION job_posting_mark_backlog()
    """)
    # Backfill: each board's first crawl in the last 2 days, and today's bulk inserts from re-enabled boards.
    op.execute("""
        WITH firsts AS (
            SELECT board_id, min(first_seen_at) AS t0 FROM job_posting GROUP BY board_id
        ), bursts AS (
            SELECT board_id, date_trunc('hour', first_seen_at) AS h FROM job_posting
            WHERE posted_at IS NULL AND first_seen_at >= '2026-11-02 08:50+00'
            GROUP BY 1, 2 HAVING count(*) >= 50
        )
        UPDATE job_posting p SET backlog = true
        FROM firsts f
        WHERE f.board_id = p.board_id AND p.posted_at IS NULL
          AND ((f.t0 > now() - interval '2 days' AND p.first_seen_at < f.t0 + interval '2 hours')
               OR EXISTS (SELECT 1 FROM bursts bu
                          WHERE bu.board_id = p.board_id AND bu.h = date_trunc('hour', p.first_seen_at)))
    """)
    op.execute("DROP INDEX IF EXISTS idx_jp_feed")
    op.execute("ALTER TABLE job_posting DROP COLUMN listed_at")
    op.execute(f"""
        ALTER TABLE job_posting ADD COLUMN listed_at TIMESTAMPTZ GENERATED ALWAYS AS (
            CASE WHEN backlog AND posted_at IS NULL THEN 'epoch'::timestamptz ELSE {_LISTED_AT} END
        ) STORED
    """)
    op.execute("CREATE INDEX idx_jp_feed ON job_posting (listed_at DESC, id DESC) WHERE is_active AND is_tech")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jp_feed")
    op.execute("ALTER TABLE job_posting DROP COLUMN listed_at")
    op.execute(f"ALTER TABLE job_posting ADD COLUMN listed_at TIMESTAMPTZ GENERATED ALWAYS AS ({_LISTED_AT}) STORED")
    op.execute("CREATE INDEX idx_jp_feed ON job_posting (listed_at DESC, id DESC) WHERE is_active AND is_tech")
    op.execute("DROP TRIGGER IF EXISTS job_posting_backlog ON job_posting")
    op.execute("DROP FUNCTION IF EXISTS job_posting_mark_backlog()")
    op.execute("ALTER TABLE job_posting DROP COLUMN IF EXISTS backlog")
