"""Add taxonomy tables required by the processing pipeline.

Creates: location, location_name, location_macro_member, currency_rate,
taxonomy_miss, occupation, seniority, technology (with name columns).

These are empty on first install; they are populated by GeoNames seed scripts
and the sync command respectively. The pipeline handles empty tables gracefully.

Revision ID: 0007
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- location taxonomy (GeoNames) ----------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE location_type AS ENUM ('macro', 'country', 'region', 'city');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS location (
            id        INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES location(id),
            type      location_type NOT NULL,
            population INTEGER,
            languages TEXT[] NOT NULL DEFAULT '{}',
            lat       REAL,
            lng       REAL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_loc_parent ON location(parent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_loc_type ON location(type)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS location_name (
            location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
            locale      TEXT NOT NULL,
            name        TEXT NOT NULL,
            is_display  BOOLEAN NOT NULL DEFAULT false,
            PRIMARY KEY (location_id, locale, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_locname_lower ON location_name(lower(name), locale)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS location_macro_member (
            macro_id   INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
            country_id INTEGER NOT NULL REFERENCES location(id) ON DELETE CASCADE,
            PRIMARY KEY (macro_id, country_id)
        )
    """)

    # -- currency rates -------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS currency_rate (
            currency   TEXT PRIMARY KEY,
            to_eur     NUMERIC(10,6) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Seed with approximate rates
    op.execute("""
        INSERT INTO currency_rate (currency, to_eur) VALUES
            ('EUR', 1.000000), ('USD', 0.870000), ('GBP', 1.170000),
            ('CHF', 1.040000), ('CAD', 0.670000), ('AUD', 0.580000),
            ('JPY', 0.006100), ('CNY', 0.126000), ('INR', 0.010300),
            ('SGD', 0.680000), ('HKD', 0.112000), ('NZD', 0.530000),
            ('SEK', 0.089000), ('NOK', 0.086000), ('DKK', 0.134000),
            ('PLN', 0.233000), ('BRL', 0.160000), ('MXN', 0.048000),
            ('KRW', 0.000650), ('TWD', 0.026500), ('ZAR', 0.050000)
        ON CONFLICT (currency) DO NOTHING
    """)

    # -- taxonomy miss tracking -----------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_miss (
            id          SERIAL PRIMARY KEY,
            taxonomy    TEXT NOT NULL,
            raw_value   TEXT NOT NULL,
            sample_value TEXT NOT NULL,
            hit_count   INTEGER NOT NULL DEFAULT 1,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            status      TEXT NOT NULL DEFAULT 'pending',
            resolved_to TEXT,
            UNIQUE (taxonomy, raw_value)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tm_pending ON taxonomy_miss (taxonomy, hit_count DESC) "
        "WHERE status = 'pending'"
    )

    # -- occupation -----------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS occupation (
            id        SERIAL PRIMARY KEY,
            slug      TEXT NOT NULL UNIQUE,
            parent_id INTEGER REFERENCES occupation(id),
            domain_id INTEGER
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS occupation_domain (
            id   SERIAL PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE
        )
    """)

    # -- seniority ------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS seniority (
            id   SERIAL PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE
        )
    """)

    # -- technology -----------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS technology (
            id       SERIAL PRIMARY KEY,
            slug     TEXT NOT NULL UNIQUE,
            name     TEXT,
            category TEXT
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS technology")
    op.execute("DROP TABLE IF EXISTS seniority")
    op.execute("DROP TABLE IF EXISTS occupation")
    op.execute("DROP TABLE IF EXISTS occupation_domain")
    op.execute("DROP TABLE IF EXISTS taxonomy_miss")
    op.execute("DROP TABLE IF EXISTS currency_rate")
    op.execute("DROP TABLE IF EXISTS location_macro_member")
    op.execute("DROP TABLE IF EXISTS location_name")
    op.execute("DROP TABLE IF EXISTS location")
    op.execute("DROP TYPE IF EXISTS location_type")
