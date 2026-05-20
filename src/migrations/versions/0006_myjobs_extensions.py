"""Myjobs-specific extensions to the jobseek schema.

Adds scoring columns to job_posting, tier/industry to company,
and the daily_runs tracking table.

Revision ID: 0006
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scoring + application tracking on job_posting
    op.execute("""
        ALTER TABLE job_posting
            ADD COLUMN IF NOT EXISTS visa_signal   INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS early_career  INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS role_category TEXT,
            ADD COLUMN IF NOT EXISTS skill_score   REAL NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS role_score    REAL NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS visa_score    REAL NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS recency_score REAL NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS company_score REAL NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS total_score   REAL NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'new',
            ADD COLUMN IF NOT EXISTS applied_at    TIMESTAMPTZ
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_jp_total_score ON job_posting (total_score DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jp_status ON job_posting (status)")

    # Company tier (used by ranker.company_score)
    # Note: company.industry SMALLINT already exists from migration 0002.
    op.execute("""
        ALTER TABLE company
            ADD COLUMN IF NOT EXISTS tier INTEGER NOT NULL DEFAULT 2
    """)

    # Daily run tracking
    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_runs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_date         DATE NOT NULL UNIQUE,
            started_at       TIMESTAMPTZ,
            finished_at      TIMESTAMPTZ,
            jobs_scraped     INTEGER DEFAULT 0,
            jobs_new         INTEGER DEFAULT 0,
            jobs_shortlisted INTEGER DEFAULT 0,
            error            TEXT
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_runs")
    op.execute("ALTER TABLE company DROP COLUMN IF EXISTS tier")
    op.execute("DROP INDEX IF EXISTS idx_jp_status")
    op.execute("DROP INDEX IF EXISTS idx_jp_total_score")
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
