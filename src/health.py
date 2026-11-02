"""Crawler health checks with alert thresholds (D23).

``myjobs health`` prints the checks and exits 1 when any alert fires, so cron or a
systemd timer can page on it. ``evaluate`` is pure; ``fetch_snapshot`` is the only SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

FEED_STALE_MINUTES = 180  # no new posting anywhere for this long → the worker is likely down
OVERDUE_SHARE = 0.05  # share of active boards >2h past their next check → the worker is behind
ATS_MIN_BOARDS = 5  # ignore ATS types with fewer boards (too noisy)
ATS_FAILING_SHARE = 0.25  # share of an ATS's boards failing → the adapter or the ATS API broke
# D40: a board counts as failing only with no success for a day; a passing timeout is noise.
FAILING_SQL = "consecutive_failures > 0 AND coalesce(last_success_at, '-infinity') < now() - interval '1 day'"
ATS_EMPTY_SHARE = 0.30  # share of an ATS's boards with no jobs for 3 days → the parser silently broke
GONE_PER_DAY = 20  # boards marked gone in 24h → a mass ATS migration or a detection bug


@dataclass(frozen=True)
class Alert:
    check: str
    message: str


@dataclass
class Snapshot:
    feed_age_minutes: float | None
    active_boards: int
    overdue_boards: int
    gone_last_day: int
    # crawler_type → (boards, failing, empty_3d)
    by_ats: dict[str, tuple[int, int, int]] = field(default_factory=dict)


_SNAPSHOT_SQL = """
SELECT
  (SELECT EXTRACT(EPOCH FROM now() - max(first_seen_at)) / 60 FROM job_posting)               AS feed_age_minutes,
  (SELECT count(*) FROM job_board WHERE is_enabled AND board_status <> 'gone')                AS active_boards,
  (SELECT count(*) FROM job_board WHERE is_enabled AND board_status <> 'gone'
      AND next_check_at < now() - interval '2 hours')                                          AS overdue_boards,
  (SELECT count(*) FROM job_board WHERE gone_at > now() - interval '1 day')                   AS gone_last_day
"""

_BY_ATS_SQL = """
SELECT crawler_type,
       count(*)                                                                  AS boards,
       count(*) FILTER (WHERE {failing})                                         AS failing,
       count(*) FILTER (WHERE last_checked_at IS NOT NULL
                          AND coalesce(last_non_empty_at, '-infinity') < now() - interval '3 days') AS empty_3d
FROM job_board
WHERE is_enabled AND board_status <> 'gone'
GROUP BY crawler_type
""".format(failing=FAILING_SQL)


async def fetch_snapshot(pool: asyncpg.Pool) -> Snapshot:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SNAPSHOT_SQL)
        ats_rows = await conn.fetch(_BY_ATS_SQL)
    return Snapshot(
        feed_age_minutes=float(row["feed_age_minutes"]) if row["feed_age_minutes"] is not None else None,
        active_boards=row["active_boards"],
        overdue_boards=row["overdue_boards"],
        gone_last_day=row["gone_last_day"],
        by_ats={r["crawler_type"] or "unknown": (r["boards"], r["failing"], r["empty_3d"]) for r in ats_rows},
    )


def evaluate(s: Snapshot) -> list[Alert]:
    alerts: list[Alert] = []
    if s.feed_age_minutes is None:
        alerts.append(Alert("feed_stale", "no postings at all"))
    elif s.feed_age_minutes > FEED_STALE_MINUTES:
        alerts.append(Alert("feed_stale", f"newest posting is {s.feed_age_minutes / 60:.1f}h old"))
    if s.active_boards and s.overdue_boards / s.active_boards > OVERDUE_SHARE:
        alerts.append(Alert("worker_behind", f"{s.overdue_boards}/{s.active_boards} boards are >2h overdue"))
    if s.gone_last_day > GONE_PER_DAY:
        alerts.append(Alert("boards_gone", f"{s.gone_last_day} boards marked gone in the last 24h"))
    for ats, (boards, failing, empty) in sorted(s.by_ats.items()):
        if boards < ATS_MIN_BOARDS:
            continue
        if failing / boards > ATS_FAILING_SHARE:
            alerts.append(Alert("ats_failing", f"{ats}: {failing}/{boards} boards failing"))
        if empty / boards > ATS_EMPTY_SHARE:
            alerts.append(Alert("ats_empty", f"{ats}: {empty}/{boards} boards had no jobs for 3 days"))
    return alerts


# Board-list filters and orders for `myjobs boards` and /admin/boards (whitelisted SQL, never user text)
BOARD_STATUSES = {
    "all": "true",
    "failing": "b.consecutive_failures > 0 AND b.board_status NOT IN ('gone', 'disabled')",
    "overdue": "b.is_enabled AND b.board_status <> 'gone' AND b.next_check_at < now() - interval '2 hours'",
    "never": "b.is_enabled AND b.last_success_at IS NULL",
    "disabled": "NOT b.is_enabled AND b.board_status <> 'gone'",
    "gone": "b.board_status = 'gone'",
}
BOARD_SORTS = {
    "stale": "b.last_success_at ASC NULLS FIRST",
    "due": "b.next_check_at",
    "recent": "b.last_checked_at DESC NULLS LAST",
    "failures": "b.consecutive_failures DESC, b.last_success_at ASC NULLS FIRST",
}

_BOARDS_SQL = """
SELECT b.id, c.slug AS company, c.name AS company_name, b.board_slug, b.board_url, b.crawler_type, b.board_status,
       b.is_enabled, b.last_checked_at, b.last_success_at, b.next_check_at, b.consecutive_failures,
       left(b.last_error, 300) AS last_error,
       (SELECT count(*) FROM job_posting jp WHERE jp.board_id = b.id AND jp.is_active) AS active_jobs
FROM job_board b JOIN company c ON c.id = b.company_id
WHERE ($1::text IS NULL OR c.slug = $1 OR c.name ILIKE '%' || $1 || '%' OR b.crawler_type = $1 OR b.board_slug = $1)
  AND ($2::text IS NULL OR b.crawler_type = $2)
  AND {status}
ORDER BY {order}
LIMIT $3 OFFSET $4
"""


async def fetch_boards(pool: asyncpg.Pool, term: str | None, limit: int = 50, *, ats: str | None = None,
                       status: str = "all", sort: str = "due", offset: int = 0) -> list[asyncpg.Record]:
    """Boards matching a company slug or name, an ATS type, or a board slug; `status` and `sort` are keys of
    BOARD_STATUSES and BOARD_SORTS."""
    sql = _BOARDS_SQL.format(status=BOARD_STATUSES[status], order=BOARD_SORTS[sort])
    async with pool.acquire() as conn:
        return await conn.fetch(sql, term, ats, limit, offset)


_ERRORS_SQL = """
SELECT left(regexp_replace(last_error, '\\s+', ' ', 'g'), 100) AS error, count(*) AS boards,
       array_agg(DISTINCT crawler_type) AS ats
FROM job_board b
WHERE last_error IS NOT NULL AND consecutive_failures > 0 AND board_status <> 'gone'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 50
"""


async def fetch_errors(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Failing and auto-disabled boards grouped by the start of their last error, most common first."""
    async with pool.acquire() as conn:
        return await conn.fetch(_ERRORS_SQL)
