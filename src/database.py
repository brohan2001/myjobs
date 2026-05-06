from __future__ import annotations

import json
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


def upsert_company(conn: sqlite3.Connection, company: dict) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO companies (name, slug, ats_type, domain, industry, tier)
           VALUES (:name, :slug, :ats_type, :domain, :industry, :tier)""",
        company,
    )
    row = conn.execute(
        "SELECT id FROM companies WHERE slug=? AND ats_type=?",
        (company["slug"], company["ats_type"]),
    ).fetchone()
    return row["id"]


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> int:
    inserted = 0
    for job in jobs:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (external_id, company_id, title, description, location, remote,
                    url, posted_date, ats_type)
                   VALUES (:external_id, :company_id, :title, :description,
                           :location, :remote, :url, :posted_date, :ats_type)""",
                job,
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
        except sqlite3.IntegrityError:
            pass
    return inserted


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


def get_shortlist(conn: sqlite3.Connection, run_date: str, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT j.*, c.name as company_name, c.industry, c.tier, c.domain
           FROM jobs j JOIN companies c ON j.company_id=c.id
           WHERE j.status='shortlisted'
             AND date(j.scraped_at)=?
           ORDER BY j.total_score DESC
           LIMIT ?""",
        (run_date, limit),
    ).fetchall()


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
