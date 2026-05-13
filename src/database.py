from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "jobs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    slug         TEXT NOT NULL,
    ats_type     TEXT NOT NULL,
    domain       TEXT,
    industry     TEXT,
    tier         INTEGER DEFAULT 2,
    active       INTEGER DEFAULT 1,
    last_scraped TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id   TEXT NOT NULL,
    company_id    INTEGER REFERENCES companies(id),
    title         TEXT NOT NULL,
    description   TEXT,
    location      TEXT,
    remote        INTEGER DEFAULT 0,
    url           TEXT NOT NULL,
    posted_date   TEXT,
    posted_at     TEXT,
    scraped_at    TEXT DEFAULT (datetime('now')),
    ats_type      TEXT,

    visa_signal   INTEGER DEFAULT 0,
    early_career  INTEGER DEFAULT 0,
    role_category TEXT,
    exp_years_max INTEGER,

    skill_score   REAL DEFAULT 0,
    role_score    REAL DEFAULT 0,
    visa_score    REAL DEFAULT 0,
    recency_score REAL DEFAULT 0,
    company_score REAL DEFAULT 0,
    total_score   REAL DEFAULT 0,

    status        TEXT DEFAULT 'new',
    is_duplicate  INTEGER DEFAULT 0,

    UNIQUE(external_id, ats_type),
    UNIQUE(url)
);

CREATE TABLE IF NOT EXISTS daily_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date         TEXT NOT NULL UNIQUE,
    started_at       TEXT,
    finished_at      TEXT,
    jobs_scraped     INTEGER DEFAULT 0,
    jobs_new         INTEGER DEFAULT 0,
    jobs_shortlisted INTEGER DEFAULT 0,
    errors           TEXT,
    status           TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER REFERENCES jobs(id),
    applied_at  TEXT DEFAULT (datetime('now')),
    method      TEXT DEFAULT 'manual',
    notes       TEXT,
    status      TEXT DEFAULT 'submitted'
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_total_score ON jobs(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);
CREATE INDEX IF NOT EXISTS idx_jobs_company_id ON jobs(company_id);
"""

_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN posted_at TEXT",
    "ALTER TABLE companies ADD COLUMN h1b_petitions_recent INTEGER",
]

# ── US location detection ──────────────────────────────────────────────────────

_NON_US = {
    "india", "canada", "united kingdom", "ireland", "germany", "australia",
    "singapore", "poland", "netherlands", "france", "spain", "brazil",
    "mexico", "japan", "china", "taiwan", "south korea", "hong kong",
    "israel", "sweden", "denmark", "norway", "finland", "belgium",
    "switzerland", "austria", "portugal", "romania", "czech republic",
}
_US_SIGNALS = {"united states", "usa", ", us", " us ", "remote"}
_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    # Common abbreviations as standalone signals
    "san francisco", "new york city", "nyc", "los angeles", "seattle",
    "boston", "austin", "chicago", "denver", "atlanta", "raleigh",
    "pittsburgh", "portland", "phoenix", "dallas", "houston",
    "mountain view", "palo alto", "sunnyvale", "san jose", "menlo park",
    "san diego", "santa clara", "redwood city", "bellevue", "kirkland",
}


def is_us_location(loc: str) -> bool:
    """Return True if the location string appears to be a US/remote position."""
    if not loc:
        return True  # blank → assume US (company-specific ATS boards default to US)
    loc_l = loc.lower()
    for s in _NON_US:
        if s in loc_l:
            return False
    for s in _US_SIGNALS:
        if s in loc_l:
            return True
    for state in _US_STATES:
        if state in loc_l:
            return True
    return True  # default include — avoid false negatives


# ── H1-B data helpers ──────────────────────────────────────────────────────────

def _normalize_company_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(
        r"\b(inc|llc|corp|ltd|technologies|systems|networks|labs|software|"
        r"services|solutions|group|holdings|global|international|enterprises)\b\.?",
        "",
        name,
    )
    return re.sub(r"\s+", " ", name).strip()


def populate_h1b_data(conn: sqlite3.Connection, h1b_data: dict) -> None:
    """Update companies table with H1-B petition counts from USCIS data."""
    companies = conn.execute("SELECT id, name, slug FROM companies").fetchall()
    updated = 0
    for c in companies:
        key = _normalize_company_name(c["name"])
        entry = h1b_data.get(key) or h1b_data.get(c["slug"])
        if entry:
            total = entry.get("total", 0)
            conn.execute(
                "UPDATE companies SET h1b_petitions_recent=? WHERE id=?",
                (total, c["id"]),
            )
            updated += 1
    return updated


# ── DB helpers ─────────────────────────────────────────────────────────────────

@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists


def upsert_company(conn: sqlite3.Connection, company: dict) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO companies (name, slug, ats_type, domain, industry, tier)
           VALUES (:name, :slug, :ats_type, :domain, :industry, :tier)""",
        company,
    )
    # Sync ats_type/slug/domain/tier in case config changed (e.g. linkedin→google)
    conn.execute(
        """UPDATE companies SET slug=:slug, ats_type=:ats_type, domain=:domain,
           industry=:industry, tier=:tier WHERE name=:name""",
        company,
    )
    row = conn.execute(
        "SELECT id FROM companies WHERE name=?",
        (company["name"],),
    ).fetchone()
    return row["id"]


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> tuple[int, list[int]]:
    inserted = 0
    inserted_ids: list[int] = []
    for job in jobs:
        try:
            row = dict(job)
            row.setdefault("posted_at", None)
            row.pop("_company_name", None)
            conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (external_id, company_id, title, description, location, remote,
                    url, posted_date, posted_at, ats_type)
                   VALUES (:external_id, :company_id, :title, :description,
                           :location, :remote, :url, :posted_date, :posted_at, :ats_type)""",
                row,
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
                inserted_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        except sqlite3.IntegrityError:
            pass
    return inserted, inserted_ids


def get_new_jobs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT j.*, c.name as company_name, c.industry, c.tier, c.domain
           FROM jobs j JOIN companies c ON j.company_id=c.id
           WHERE j.status='new' AND j.is_duplicate=0
           ORDER BY j.scraped_at DESC"""
    ).fetchall()


def get_jobs_for_rerank(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT j.*, c.name as company_name, c.industry, c.tier, c.domain
           FROM jobs j JOIN companies c ON j.company_id=c.id
           WHERE j.is_duplicate=0
             AND julianday('now') - julianday(j.scraped_at) < 7
             AND j.status NOT IN ('applied', 'skipped')"""
    ).fetchall()


def update_job_signals(conn: sqlite3.Connection, job_id: int, signals: dict) -> None:
    fields = ", ".join(f"{k}=:{k}" for k in signals)
    conn.execute(
        f"UPDATE jobs SET {fields} WHERE id=:id",
        {**signals, "id": job_id},
    )


def update_job_scores(conn: sqlite3.Connection, job_id: int, scores: dict) -> None:
    conn.execute(
        """UPDATE jobs SET
               skill_score=:skill_score, role_score=:role_score,
               visa_score=:visa_score,   recency_score=:recency_score,
               company_score=:company_score, total_score=:total_score
           WHERE id=:id""",
        {**scores, "id": job_id},
    )


def get_top_unshortlisted(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT j.*, c.name as company_name, c.industry, c.tier, c.domain
           FROM jobs j JOIN companies c ON j.company_id=c.id
           WHERE j.status='new' AND j.is_duplicate=0 AND j.visa_signal != -1
           ORDER BY j.total_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()


def mark_shortlisted(conn: sqlite3.Connection, job_ids: list[int]) -> None:
    conn.executemany(
        "UPDATE jobs SET status='shortlisted' WHERE id=?",
        [(jid,) for jid in job_ids],
    )


def get_shortlist(
    conn: sqlite3.Connection,
    run_date: str,
    limit: int = 50,
    us_only: bool = False,
    new_grad_only: bool = False,
) -> list[sqlite3.Row]:
    sql = """SELECT j.*, c.name as company_name, c.industry, c.tier, c.domain,
                    c.h1b_petitions_recent
             FROM jobs j JOIN companies c ON j.company_id=c.id
             WHERE j.status='shortlisted'
               AND date(j.scraped_at)=?"""
    params: list = [run_date]
    if new_grad_only:
        sql += " AND (j.early_career=1 OR j.exp_years_max IS NULL OR j.exp_years_max <= 2)"
    sql += " ORDER BY j.total_score DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    if us_only:
        rows = [r for r in rows if is_us_location(r["location"] or "")]
    return rows


def update_company_scraped(conn: sqlite3.Connection, slug: str, ats_type: str) -> None:
    conn.execute(
        "UPDATE companies SET last_scraped=datetime('now') WHERE slug=? AND ats_type=?",
        (slug, ats_type),
    )


def create_daily_run(conn: sqlite3.Connection, run_date: str) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO daily_runs (run_date, started_at, status)
           VALUES (?, datetime('now'), 'running')""",
        (run_date,),
    )


def update_daily_run(conn: sqlite3.Connection, run_date: str, data: dict) -> None:
    fields = ", ".join(f"{k}=:{k}" for k in data)
    conn.execute(
        f"UPDATE daily_runs SET {fields} WHERE run_date=:run_date",
        {**data, "run_date": run_date},
    )


def log_run_error(conn: sqlite3.Connection, run_date: str, error: str) -> None:
    row = conn.execute(
        "SELECT errors FROM daily_runs WHERE run_date=?", (run_date,)
    ).fetchone()
    if row:
        errors = json.loads(row["errors"] or "[]")
        errors.append(error)
        conn.execute(
            "UPDATE daily_runs SET errors=? WHERE run_date=?",
            (json.dumps(errors), run_date),
        )


def get_all_active_companies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM companies WHERE active=1").fetchall()


def get_job_by_id(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT j.*, c.name as company_name, c.industry, c.tier
           FROM jobs j JOIN companies c ON j.company_id=c.id
           WHERE j.id=?""",
        (job_id,),
    ).fetchone()


def get_applications(conn: sqlite3.Connection, days: int = 30) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT a.*, j.title, c.name as company_name, j.url
           FROM applications a
           JOIN jobs j ON a.job_id=j.id
           JOIN companies c ON j.company_id=c.id
           WHERE a.applied_at >= datetime('now', ?)
           ORDER BY a.applied_at DESC""",
        (f"-{days} days",),
    ).fetchall()


def get_existing_keys(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    rows = conn.execute("SELECT external_id, ats_type FROM jobs").fetchall()
    return {(r["external_id"], r["ats_type"]) for r in rows}


def get_daily_run(conn: sqlite3.Connection, run_date: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM daily_runs WHERE run_date=?", (run_date,)
    ).fetchone()


def get_shortlisted_jobs(
    conn: sqlite3.Connection,
    days: int = 14,
    us_only: bool = False,
    new_grad_only: bool = False,
    company_id: int | None = None,
    industry: str | None = None,
) -> list[dict]:
    sql = """SELECT j.*, c.name as company_name, c.industry, c.tier, c.domain,
                    c.h1b_petitions_recent
             FROM jobs j JOIN companies c ON j.company_id=c.id
             WHERE j.status='shortlisted'
               AND julianday('now') - julianday(j.scraped_at) <= ?"""
    params: list = [days]
    if new_grad_only:
        sql += " AND (j.early_career=1 OR j.exp_years_max IS NULL OR j.exp_years_max <= 2)"
    if company_id is not None:
        sql += " AND j.company_id=?"
        params.append(company_id)
    if industry is not None:
        sql += " AND c.industry=?"
        params.append(industry)
    sql += " ORDER BY j.total_score DESC"
    rows = conn.execute(sql, params).fetchall()
    result = [dict(r) for r in rows]
    if us_only:
        result = [r for r in result if is_us_location(r.get("location") or "")]
    return result


def get_jobs_by_company(
    conn: sqlite3.Connection,
    company_id: int,
    limit: int = 50,
) -> list[dict]:
    """All non-applied/skipped jobs for a company, newest first (ignores shortlist status)."""
    rows = conn.execute(
        """SELECT j.*, c.name as company_name, c.industry, c.tier, c.domain,
                  c.h1b_petitions_recent
           FROM jobs j JOIN companies c ON j.company_id=c.id
           WHERE j.company_id=?
             AND j.status NOT IN ('applied', 'skipped')
             AND j.is_duplicate=0
           ORDER BY COALESCE(j.posted_at, j.scraped_at) DESC
           LIMIT ?""",
        (company_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_companies_with_jobs(conn: sqlite3.Connection) -> list[dict]:
    """Companies that have at least one shortlisted job, grouped by industry."""
    rows = conn.execute(
        """SELECT c.id, c.name, c.industry, c.tier, c.slug, c.ats_type,
                  COUNT(j.id) as job_count
           FROM companies c
           JOIN jobs j ON j.company_id=c.id
           WHERE c.active=1
             AND j.status='shortlisted'
             AND j.is_duplicate=0
           GROUP BY c.id
           ORDER BY c.tier ASC, c.industry ASC, job_count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_last_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM daily_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
