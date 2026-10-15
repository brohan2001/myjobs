"""Apply the tech gate (D27) to postings already in the database.

Run after enabling the gate, and again whenever ``src/core/tech_gate.py`` changes:
- Postings a board check would now drop are deactivated. The monitor will never report them
  again, so leaving them active would let them pile up as "missing" and trip the delist guards.
- The remaining postings on URL-only boards get ``is_tech`` from their scraped title; the
  monitor keeps seeing them, so they stay active and the feed hides the non-tech ones.
"""

from __future__ import annotations

import json

import asyncpg

from src.core.static_registry import is_rich_monitor
from src.core.tech_gate import drop_at_monitor, is_tech_title
from src.logger import get_logger

log = get_logger(__name__)

_BATCH = 5000

_SELECT = """
SELECT jp.id, jp.titles[1] AS title, jp.source_url, jp.is_tech, b.crawler_type, b.metadata
FROM job_posting jp JOIN job_board b ON b.id = jp.board_id
WHERE jp.is_active AND jp.id > $1
ORDER BY jp.id
LIMIT $2
"""

_DEACTIVATE = "UPDATE job_posting SET is_active = false, updated_at = now() WHERE id = ANY($1::uuid[])"
_SET_TECH = """
UPDATE job_posting jp SET is_tech = u.is_tech
FROM unnest($1::uuid[], $2::boolean[]) AS u(id, is_tech)
WHERE jp.id = u.id
"""


def classify(row) -> str | None:
    """'drop', 'tech', 'non_tech', or None when nothing changes."""
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata or "{}")
    if is_rich_monitor(row["crawler_type"], metadata):
        return "drop" if drop_at_monitor(row["source_url"], row["title"]) else None
    if drop_at_monitor(row["source_url"], None):
        return "drop"
    if row["title"]:
        tech = is_tech_title(row["title"])
        if tech != row["is_tech"]:
            return "tech" if tech else "non_tech"
    return None


async def apply_tech_gate(pool: asyncpg.Pool) -> dict[str, int]:
    counts = {"scanned": 0, "deactivated": 0, "tech": 0, "non_tech": 0}
    last_id = "00000000-0000-0000-0000-000000000000"
    while True:
        rows = await pool.fetch(_SELECT, last_id, _BATCH)
        if not rows:
            return counts
        last_id = rows[-1]["id"]
        drop, tag_ids, tag_vals = [], [], []
        for row in rows:
            verdict = classify(row)
            if verdict == "drop":
                drop.append(row["id"])
            elif verdict is not None:
                tag_ids.append(row["id"])
                tag_vals.append(verdict == "tech")
                counts[verdict] += 1
        async with pool.acquire() as conn, conn.transaction():
            if drop:
                await conn.execute(_DEACTIVATE, drop)
            if tag_ids:
                await conn.execute(_SET_TECH, tag_ids, tag_vals)
        counts["scanned"] += len(rows)
        counts["deactivated"] += len(drop)
        log.info("tech_gate.batch", extra=counts)
