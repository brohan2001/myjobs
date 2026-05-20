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
CREATE TABLE IF NOT EXISTS boards (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id            INTEGER NOT NULL REFERENCES companies(id),
    board_slug            TEXT    UNIQUE NOT NULL,
    board_url             TEXT    NOT NULL,
    monitor_type          TEXT    NOT NULL,
    monitor_config        TEXT,
    scraper_type          TEXT    NOT NULL,
    scraper_config        TEXT,
    is_enabled            INTEGER DEFAULT 1,
    last_monitored_at     TEXT,
    last_success_at       TEXT,
    consecutive_failures  INTEGER DEFAULT 0,
    last_error            TEXT,
    metadata              TEXT
);

CREATE TABLE IF NOT EXISTS raw_jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id       INTEGER REFERENCES boards(id),
    source_url     TEXT    NOT NULL UNIQUE,
    discovered_at  TEXT    DEFAULT (datetime('now')),
    payload        TEXT    NOT NULL,
    payload_source TEXT    NOT NULL,
    parsed         INTEGER DEFAULT 0,
    parse_error    TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_jobs_board_parsed ON raw_jobs(board_id, parsed);
CREATE INDEX IF NOT EXISTS idx_boards_company ON boards(company_id);

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
    salary_min_usd INTEGER,
    salary_max_usd INTEGER,

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
    "ALTER TABLE jobs ADD COLUMN salary_min_usd INTEGER",
    "ALTER TABLE jobs ADD COLUMN salary_max_usd INTEGER",
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
            row.setdefault("salary_min_usd", None)
            row.setdefault("salary_max_usd", None)
            row.setdefault("exp_years_max", None)
            row.pop("_company_name", None)
            conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (external_id, company_id, title, description, location, remote,
                    url, posted_date, posted_at, ats_type,
                    salary_min_usd, salary_max_usd, exp_years_max)
                   VALUES (:external_id, :company_id, :title, :description,
                           :location, :remote, :url, :posted_date, :posted_at, :ats_type,
                           :salary_min_usd, :salary_max_usd, :exp_years_max)""",
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


# ── Boards + raw_jobs helpers (Phase 3 additions) ─────────────────────────────

def upsert_company_from_board(conn: sqlite3.Connection, company_slug: str, company_name: str, industry: int, tier: int) -> int:
    """Ensure a company row exists and return its id. Used when syncing CSV→DB."""
    conn.execute(
        """INSERT OR IGNORE INTO companies (name, slug, ats_type, domain, industry, tier)
           VALUES (?, ?, 'jobseek', NULL, ?, ?)""",
        (company_name, company_slug, str(industry), tier),
    )
    conn.execute(
        "UPDATE companies SET industry=?, tier=? WHERE slug=?",
        (str(industry), tier, company_slug),
    )
    row = conn.execute("SELECT id FROM companies WHERE slug=?", (company_slug,)).fetchone()
    if row is None:
        # Two CSV rows share the same name but different slugs (e.g. "goldmansachs" and
        # "goldman-sachs"). INSERT OR IGNORE was a no-op due to the UNIQUE(name) constraint.
        # Fall back to the existing row by name so both slugs share one company_id.
        row = conn.execute("SELECT id FROM companies WHERE name=?", (company_name,)).fetchone()
    return row["id"]


def upsert_board(conn: sqlite3.Connection, company_id: int, board_slug: str, board_url: str,
                 monitor_type: str, monitor_config: dict,
                 scraper_type: str, scraper_config: dict) -> int:
    """Insert or update a board row. Returns the board id."""
    mc = json.dumps(monitor_config) if monitor_config else None
    sc = json.dumps(scraper_config) if scraper_config else None
    conn.execute(
        """INSERT INTO boards
               (company_id, board_slug, board_url, monitor_type, monitor_config,
                scraper_type, scraper_config)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(board_slug) DO UPDATE SET
               board_url=excluded.board_url,
               monitor_type=excluded.monitor_type,
               monitor_config=excluded.monitor_config,
               scraper_type=excluded.scraper_type,
               scraper_config=excluded.scraper_config""",
        (company_id, board_slug, board_url, monitor_type, mc, scraper_type, sc),
    )
    row = conn.execute("SELECT id FROM boards WHERE board_slug=?", (board_slug,)).fetchone()
    return row["id"]


def list_enabled_boards(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all enabled boards joined with their company name."""
    return conn.execute(
        """SELECT b.*, c.name as company_name, c.slug as company_slug,
                  c.tier, c.industry
           FROM boards b
           JOIN companies c ON b.company_id=c.id
           WHERE b.is_enabled=1 AND c.active=1
           ORDER BY b.id""",
    ).fetchall()


def get_board(conn: sqlite3.Connection, board_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM boards WHERE id=?", (board_id,)).fetchone()


def update_board_success(conn: sqlite3.Connection, board_id: int) -> None:
    conn.execute(
        """UPDATE boards SET consecutive_failures=0, last_success_at=datetime('now'),
           last_monitored_at=datetime('now'), last_error=NULL
           WHERE id=?""",
        (board_id,),
    )


def update_board_failure(conn: sqlite3.Connection, board_id: int, error: str) -> None:
    conn.execute(
        """UPDATE boards SET consecutive_failures=consecutive_failures+1,
           last_monitored_at=datetime('now'), last_error=?
           WHERE id=?""",
        (error[:500], board_id),
    )


def record_raw_job(conn: sqlite3.Connection, board_id: int, source_url: str,
                   payload: dict, source: str) -> int | None:
    """Insert a raw job row. Uses INSERT OR IGNORE so re-discovery is idempotent.

    Returns the row id if inserted, None if already existed.
    """
    conn.execute(
        """INSERT OR IGNORE INTO raw_jobs (board_id, source_url, payload, payload_source)
           VALUES (?, ?, ?, ?)""",
        (board_id, source_url, json.dumps(payload), source),
    )
    row = conn.execute("SELECT id FROM raw_jobs WHERE source_url=?", (source_url,)).fetchone()
    return row["id"] if row else None


def get_unscraped_url_only_raw_jobs(conn: sqlite3.Connection, limit: int = 2000) -> list[sqlite3.Row]:
    """Return raw_jobs rows that came from URL-only monitors and need scraping."""
    return conn.execute(
        """SELECT r.*, b.scraper_type, b.scraper_config, b.company_id,
                  b.board_slug, b.monitor_type
           FROM raw_jobs r
           JOIN boards b ON r.board_id=b.id
           WHERE r.parsed=0 AND r.payload_source='monitor'
             AND b.scraper_type != 'skip' AND b.scraper_type != ''
           LIMIT ?""",
        (limit,),
    ).fetchall()


def get_unparsed_raw_jobs(conn: sqlite3.Connection, limit: int = 5000) -> list[sqlite3.Row]:
    """Return raw_jobs rows that haven't been converted to jobs rows yet."""
    return conn.execute(
        """SELECT r.*, b.scraper_type, b.scraper_config, b.company_id,
                  b.board_slug, b.monitor_type
           FROM raw_jobs r
           JOIN boards b ON r.board_id=b.id
           WHERE r.parsed=0
           LIMIT ?""",
        (limit,),
    ).fetchall()


def update_raw_job_payload(conn: sqlite3.Connection, raw_id: int,
                           payload: dict, source: str) -> None:
    """Replace the payload of a raw_job row after scraping."""
    conn.execute(
        "UPDATE raw_jobs SET payload=?, payload_source=? WHERE id=?",
        (json.dumps(payload), source, raw_id),
    )


def mark_raw_parsed(conn: sqlite3.Connection, raw_id: int,
                    jobs_row_id: int | None, error: str | None) -> None:
    conn.execute(
        "UPDATE raw_jobs SET parsed=1, parse_error=? WHERE id=?",
        (error[:500] if error else None, raw_id),
    )
