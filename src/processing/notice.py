"""Fill ``job_posting.notice_max_days`` from stored descriptions (REVAMP_PLAN 2A.5).

Runs beside the crawl pipeline in ``myjobs worker``: picks active postings whose description
changed since it was last parsed, extracts the notice period, writes it back. Batches run
back to back while there is a backlog, then the loop idles.
"""

from __future__ import annotations

import asyncio

import asyncpg

from src.core.notice_period import extract_notice_period
from src.logger import get_logger

log = get_logger(__name__)

BATCH_SIZE = 1000
IDLE_SECONDS = 120

_PENDING = """
SELECT jp.id, d.html, d.hash
FROM job_posting jp
JOIN LATERAL (
    SELECT html, hash FROM descriptions
    WHERE posting_id = jp.id
    ORDER BY (locale = 'en') DESC, updated_at DESC
    LIMIT 1
) d ON true
WHERE jp.is_active AND jp.notice_desc_hash IS DISTINCT FROM d.hash
LIMIT $1
"""

_UPDATE = """
UPDATE job_posting jp
SET notice_max_days = u.days, notice_desc_hash = u.hash
FROM unnest($1::uuid[], $2::smallint[], $3::bigint[]) AS u(id, days, hash)
WHERE jp.id = u.id
"""


async def enrich_notice_batch(pool: asyncpg.Pool, limit: int = BATCH_SIZE) -> int:
    """Parse one batch; returns how many postings were processed."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_PENDING, limit)
        if not rows:
            return 0
        ids, days, hashes = [], [], []
        for r in rows:
            ids.append(r["id"])
            days.append(extract_notice_period(r["html"]))
            hashes.append(r["hash"])
        await conn.execute(_UPDATE, ids, days, hashes)
    return len(rows)


async def run_notice_loop(pool: asyncpg.Pool, shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        try:
            n = await enrich_notice_batch(pool)
        except Exception:  # noqa: BLE001 - enrichment must never take the worker down
            log.warning("notice.batch_failed", exc_info=True)
            n = 0
        if n:
            log.info("notice.batch", extra={"processed": n})
        if n < BATCH_SIZE:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=IDLE_SECONDS)
            except TimeoutError:
                pass
