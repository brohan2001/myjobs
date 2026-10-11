"""SQL for the public feed API.

``build_jobs_query`` is pure (filters → SQL + args) so it can be unit-tested
without a database. Every user-supplied value is a bind parameter.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

WORK_MODES = ("remote", "hybrid", "onsite")
MAX_LIMIT = 100
_SINCE_RE = re.compile(r"^(\d{1,3})([hd])$")


class InvalidFilter(ValueError):
    """Raised for malformed query parameters (mapped to HTTP 400)."""


@dataclass(frozen=True)
class JobFilters:
    q: str | None = None
    location_ids: tuple[int, ...] | None = None  # already expanded to descendants
    company: str | None = None  # company slug
    work_mode: str | None = None
    since: datetime | None = None
    seniority: str | None = None
    occupation: str | None = None
    max_years: int | None = None  # jobs whose minimum experience requirement is <= this (or unstated)
    cursor: tuple[datetime, UUID] | None = None
    limit: int = 50


# ---------------------------------------------------------------------------
# Parameter parsing
# ---------------------------------------------------------------------------


def parse_since(value: str | None, *, now: datetime | None = None) -> datetime | None:
    """``24h`` / ``7d`` / ISO-8601 timestamp → aware datetime."""
    if not value:
        return None
    now = now or datetime.now(timezone.utc)
    m = _SINCE_RE.match(value.strip().lower())
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
        return now - delta
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidFilter("since must look like 24h, 7d or an ISO-8601 timestamp") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def encode_cursor(first_seen_at: datetime, posting_id: UUID | str) -> str:
    raw = json.dumps([first_seen_at.isoformat(), str(posting_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str | None) -> tuple[datetime, UUID] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        ts, pid = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return datetime.fromisoformat(ts), UUID(pid)
    except (binascii.Error, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise InvalidFilter("invalid cursor") from exc


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

_JOB_COLUMNS = """
    jp.id,
    jp.titles[1]        AS title,
    jp.source_url       AS url,
    jp.location_ids,
    jp.location_types,
    jp.locations_raw,
    jp.employment_type,
    jp.salary_min,
    jp.salary_max,
    jp.salary_currency,
    jp.salary_period,
    jp.experience_min,
    jp.experience_max,
    jp.first_seen_at,
    jp.last_seen_at,
    c.slug              AS company_slug,
    c.name              AS company_name,
    c.website           AS company_website,
    c.logo              AS company_logo,
    jb.crawler_type     AS ats
"""


def build_jobs_query(f: JobFilters) -> tuple[str, list]:
    # URL-only boards insert a posting before its detail page is scraped; hide it until it has a title.
    where = ["jp.is_active", "jp.titles[1] IS NOT NULL"]
    args: list = []

    def arg(value) -> str:
        args.append(value)
        return f"${len(args)}"

    if f.q:
        p = arg(_like_pattern(f.q))
        where.append(f"(lower(jp.titles[1]) LIKE {p} OR lower(c.name) LIKE {p})")
    if f.location_ids is not None:
        where.append(f"jp.location_ids && {arg(list(f.location_ids))}::int[]")
    if f.company:
        where.append(f"c.slug = {arg(f.company)}")
    if f.work_mode:
        if f.work_mode not in WORK_MODES:
            raise InvalidFilter(f"work_mode must be one of {', '.join(WORK_MODES)}")
        where.append(f"{arg(f.work_mode)} = ANY(jp.location_types)")
    if f.since:
        where.append(f"jp.first_seen_at >= {arg(f.since)}")
    if f.seniority:
        where.append(f"jp.seniority_id = (SELECT id FROM seniority WHERE slug = {arg(f.seniority)})")
    if f.occupation:
        p = arg(f.occupation)
        where.append(
            f"jp.occupation_id IN (SELECT id FROM occupation WHERE slug = {p} "
            f"OR parent_id = (SELECT id FROM occupation WHERE slug = {p}))"
        )
    if f.max_years is not None:
        where.append(f"(jp.experience_min IS NULL OR jp.experience_min <= {arg(int(f.max_years))})")
    if f.cursor:
        ts, pid = f.cursor
        where.append(f"(jp.first_seen_at, jp.id) < ({arg(ts)}, {arg(pid)})")

    limit = max(1, min(int(f.limit), MAX_LIMIT))
    sql = (
        f"SELECT {_JOB_COLUMNS}\n"
        "FROM job_posting jp\n"
        "JOIN company c ON c.id = jp.company_id\n"
        "LEFT JOIN job_board jb ON jb.id = jp.board_id\n"
        f"WHERE {' AND '.join(where)}\n"
        "ORDER BY jp.first_seen_at DESC, jp.id DESC\n"
        f"LIMIT {arg(limit + 1)}"  # one extra row tells us whether there is a next page
    )
    return sql, args


async def fetch_jobs(pool: asyncpg.Pool, f: JobFilters) -> tuple[list[asyncpg.Record], str | None]:
    sql, args = build_jobs_query(f)
    limit = max(1, min(int(f.limit), MAX_LIMIT))
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last["first_seen_at"], last["id"])
    return rows, next_cursor


_JOB_DETAIL = f"""
SELECT {_JOB_COLUMNS},
    jp.is_active,
    d.html AS description_html
FROM job_posting jp
JOIN company c ON c.id = jp.company_id
LEFT JOIN job_board jb ON jb.id = jp.board_id
LEFT JOIN LATERAL (
    SELECT html FROM descriptions
    WHERE posting_id = jp.id
    ORDER BY (locale = 'en') DESC, updated_at DESC
    LIMIT 1
) d ON true
WHERE jp.id = $1
"""


async def fetch_job(pool: asyncpg.Pool, posting_id: UUID) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(_JOB_DETAIL, posting_id)


# ---------------------------------------------------------------------------
# Companies and stats
# ---------------------------------------------------------------------------

_COMPANIES = """
SELECT c.slug, c.name, c.website, c.logo, COUNT(jp.id) AS active_jobs,
       MAX(jp.first_seen_at) AS latest_job_at
FROM company c
JOIN job_posting jp ON jp.company_id = c.id AND jp.is_active
WHERE ($1::text IS NULL OR lower(c.name) LIKE $1)
GROUP BY c.id
ORDER BY active_jobs DESC, c.name
LIMIT $2
"""


async def fetch_companies(pool: asyncpg.Pool, q: str | None, limit: int) -> list[asyncpg.Record]:
    pattern = _like_pattern(q) if q else None
    async with pool.acquire() as conn:
        return await conn.fetch(_COMPANIES, pattern, max(1, min(limit, 500)))


_STATS = """
SELECT
    (SELECT COUNT(*) FROM job_posting WHERE is_active)                                         AS active_jobs,
    (SELECT COUNT(*) FROM job_posting WHERE is_active AND first_seen_at >= now() - interval '24 hours') AS new_last_24h,
    (SELECT COUNT(DISTINCT company_id) FROM job_posting WHERE is_active)                       AS companies_hiring,
    (SELECT COUNT(*) FROM job_board WHERE is_enabled)                                          AS boards_enabled,
    (SELECT COUNT(*) FROM job_board WHERE is_enabled AND last_success_at >= now() - interval '24 hours') AS boards_fresh_24h,
    (SELECT COUNT(*) FROM job_board WHERE is_enabled AND consecutive_failures > 0)             AS boards_failing,
    (SELECT MAX(last_success_at) FROM job_board)                                               AS last_updated
"""


async def fetch_stats(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_STATS)
    return dict(row)


# ---------------------------------------------------------------------------
# Coverage / source health
# ---------------------------------------------------------------------------

_COVERAGE_BY_ATS = """
SELECT jb.crawler_type AS ats,
       COUNT(*) FILTER (WHERE jb.is_enabled)                                         AS boards,
       COUNT(*) FILTER (WHERE jb.is_enabled AND jb.consecutive_failures = 0
                        AND jb.last_success_at >= now() - interval '24 hours')       AS healthy,
       COUNT(*) FILTER (WHERE jb.is_enabled AND jb.consecutive_failures > 0)         AS failing,
       COUNT(*) FILTER (WHERE jb.board_status = 'gone')                              AS gone,
       MAX(jb.last_success_at)                                                       AS last_success_at
FROM job_board jb
GROUP BY jb.crawler_type
ORDER BY boards DESC
"""

_COVERAGE_BY_COUNTRY = """
SELECT COALESCE(c.extras->>'country', 'unknown') AS country,
       COUNT(DISTINCT c.id)                       AS companies,
       COUNT(DISTINCT c.id) FILTER (WHERE EXISTS (
           SELECT 1 FROM job_posting jp WHERE jp.company_id = c.id AND jp.is_active)) AS companies_hiring
FROM company c
GROUP BY 1
ORDER BY companies DESC
"""

_COVERAGE_BY_CITY = """
SELECT c.extras->>'hq_city' AS city, COUNT(*) AS companies
FROM company c
WHERE c.extras->>'country' = 'IN' AND c.extras->>'hq_city' IS NOT NULL
GROUP BY 1
ORDER BY companies DESC
"""


async def fetch_coverage(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        by_ats = await conn.fetch(_COVERAGE_BY_ATS)
        by_country = await conn.fetch(_COVERAGE_BY_COUNTRY)
        by_city = await conn.fetch(_COVERAGE_BY_CITY)
    return {
        "by_ats": [dict(r) for r in by_ats],
        "by_country": [dict(r) for r in by_country],
        "india_by_city": [dict(r) for r in by_city],
    }
