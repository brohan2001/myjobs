"""Backfill: undated jobs from a bulk first sighting in the last 7 days are backlog (D38).

From now on the monitor marks them (``_MARK_BULK_BACKLOG``): one check that finds at least 50 new undated jobs,
more than a quarter of the board's others, found old jobs rather than fresh posts. Here a "check" is approximated
by the board and the hour the jobs were first seen.

Revision ID: 0014
Create Date: 2026-11-02
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        WITH bursts AS (
            SELECT board_id, date_trunc('hour', first_seen_at) AS h, count(*) AS n
            FROM job_posting
            WHERE is_active AND posted_at IS NULL AND NOT backlog AND first_seen_at > now() - interval '7 days'
            GROUP BY 1, 2 HAVING count(*) >= 50
        ), sizes AS (
            SELECT board_id, count(*) AS active FROM job_posting WHERE is_active GROUP BY 1
        )
        UPDATE job_posting p SET backlog = true
        FROM bursts b JOIN sizes s USING (board_id)
        WHERE p.board_id = b.board_id AND date_trunc('hour', p.first_seen_at) = b.h
          AND p.is_active AND p.posted_at IS NULL AND NOT p.backlog
          AND b.n * 4 > s.active - b.n
    """)


def downgrade() -> None:
    pass  # a data backfill; D38's rows can't be told apart from these afterwards
