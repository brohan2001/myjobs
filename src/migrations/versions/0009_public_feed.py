"""Public feed: drop single-user scoring/report state, add feed indexes.

- Drops the myjobs scoring/visa/shortlist columns (0006) and ``daily_runs``.
  The product is now a public latest-jobs feed; per-user scoring returns
  later in its own tables.
- Adds ``location.code`` (ISO-3166 alpha-2 for countries, GeoNames admin1
  code for regions, slug for macros), filled by scripts/load_geonames.py.
- Adds indexes for the feed: newest-first keyset pagination, location
  overlap (GIN), and trigram title search.

Revision ID: 0009
Create Date: 2026-10-11
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jp_total_score")
    op.execute("DROP INDEX IF EXISTS idx_jp_status")
    op.execute("""
        ALTER TABLE job_posting
            DROP COLUMN IF EXISTS visa_signal,
            DROP COLUMN IF EXISTS early_career,
            DROP COLUMN IF EXISTS role_category,
            DROP COLUMN IF EXISTS skill_score,
            DROP COLUMN IF EXISTS role_score,
            DROP COLUMN IF EXISTS visa_score,
            DROP COLUMN IF EXISTS recency_score,
            DROP COLUMN IF EXISTS company_score,
            DROP COLUMN IF EXISTS total_score,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS applied_at
    """)
    op.execute("DROP TABLE IF EXISTS daily_runs")

    op.execute("ALTER TABLE location ADD COLUMN IF NOT EXISTS code TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_loc_code ON location(code)")

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jp_feed "
        "ON job_posting (first_seen_at DESC, id DESC) WHERE is_active"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jp_location_ids "
        "ON job_posting USING GIN (location_ids) WHERE is_active"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jp_title_trgm "
        "ON job_posting USING GIN ((lower(titles[1])) gin_trgm_ops) WHERE is_active"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jp_title_trgm")
    op.execute("DROP INDEX IF EXISTS idx_jp_location_ids")
    op.execute("DROP INDEX IF EXISTS idx_jp_feed")
    op.execute("DROP INDEX IF EXISTS idx_loc_code")
    op.execute("ALTER TABLE location DROP COLUMN IF EXISTS code")
    # Scoring columns and daily_runs are not restored; re-run 0006 manually if needed.
