"""How often each board is checked (D33, D36).

Boards of companies that may hire in India keep the base interval: hourly, or every 3 h for slow board types. Companies
whose open tech jobs are all outside India are checked every 12 h, and companies with no open tech jobs every 8 h.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import Counter

import asyncpg

from src.logger import get_logger
from src.redis_queue import get_redis

log = get_logger(__name__)

SLOW_MONITORS = {"dom", "sitemap", "icims", "workday", "api_sniffer"}
NO_INDIA_MINUTES = 720
NO_JOBS_MINUTES = 480
REFRESH_SECONDS = 6 * 3600
RETRY_SECONDS = 600

# A company "may hire in India" if any open tech job is in India or has no resolved location.
_CLASSIFY = """
WITH RECURSIVE india AS (
    SELECT id FROM location WHERE type = 'country' AND code = 'IN'
    UNION SELECT l.id FROM location l JOIN india ON l.parent_id = india.id
), company_class AS (
    SELECT p.company_id,
           bool_or(p.location_ids && (SELECT array_agg(id) FROM india)
                   OR p.location_ids IS NULL OR cardinality(p.location_ids) = 0) AS india
    FROM job_posting p WHERE p.is_active AND p.is_tech GROUP BY p.company_id
)
SELECT b.id::text AS id, b.crawler_type, b.monitor_needs_browser, b.check_interval_minutes,
       CASE WHEN cc.company_id IS NULL THEN 'none' WHEN cc.india THEN 'india' ELSE 'no_india' END AS cls
FROM job_board b LEFT JOIN company_class cc ON cc.company_id = b.company_id
WHERE b.is_enabled
"""

_UPDATE = """
UPDATE job_board b SET check_interval_minutes = v.minutes, updated_at = now()
FROM unnest($1::uuid[], $2::int[]) AS v(id, minutes) WHERE b.id = v.id
"""


def base_interval(monitor_type: str | None, browser: bool) -> int:
    return 180 if browser or monitor_type in SLOW_MONITORS else 60


def check_interval(cls: str, monitor_type: str | None, browser: bool) -> int:
    if cls == "no_india":
        return NO_INDIA_MINUTES
    if cls == "none":
        return NO_JOBS_MINUTES
    return base_interval(monitor_type, browser)


async def apply_india_priority(conn: asyncpg.Connection) -> Counter:
    """Set every enabled board's check interval from its company's class, in Postgres and in the Redis board hash."""
    counts: Counter = Counter()
    ids, minutes = [], []
    for row in await conn.fetch(_CLASSIFY):
        counts[row["cls"]] += 1
        want = check_interval(row["cls"], row["crawler_type"], row["monitor_needs_browser"])
        if want != row["check_interval_minutes"]:
            ids.append(row["id"])
            minutes.append(want)
    if ids:
        await conn.execute(_UPDATE, ids, minutes)
        r = get_redis()
        pipe = r.pipeline()
        for board_id in ids:
            pipe.exists(f"board:{board_id}")
        exists = await pipe.execute()
        pipe = r.pipeline()
        for board_id, want, ok in zip(ids, minutes, exists):
            if ok:  # never create a partial hash for a board that isn't queued
                pipe.hset(f"board:{board_id}", "check_interval_minutes", str(want))
        await pipe.execute()
    counts["changed"] = len(ids)
    log.info("priority.applied", extra=dict(counts))
    return counts


async def priority_loop(pool: asyncpg.Pool, shutdown_event: asyncio.Event) -> None:
    """Re-classify every 6 h. A Redis lock lets only one worker process do it; a failed run frees it for a retry.

    The first run waits 10 min: the worker's startup sync has just applied the intervals.
    """
    wait = RETRY_SECONDS
    while True:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(shutdown_event.wait(), timeout=wait)
        if shutdown_event.is_set():
            return
        wait = REFRESH_SECONDS
        r = get_redis()
        try:
            if await r.set("lock:priority", "1", nx=True, ex=REFRESH_SECONDS - 60):
                async with pool.acquire() as conn:
                    await apply_india_priority(conn)
        except Exception:
            log.exception("priority.failed")
            with contextlib.suppress(Exception):
                await r.delete("lock:priority")
            wait = RETRY_SECONDS
