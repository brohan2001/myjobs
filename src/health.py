"""Crawler health checks with alert thresholds (REVAMP_PLAN 2B.8).

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
       count(*) FILTER (WHERE consecutive_failures > 0)                          AS failing,
       count(*) FILTER (WHERE last_checked_at IS NOT NULL
                          AND coalesce(last_non_empty_at, '-infinity') < now() - interval '3 days') AS empty_3d
FROM job_board
WHERE is_enabled AND board_status <> 'gone'
GROUP BY crawler_type
"""


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
