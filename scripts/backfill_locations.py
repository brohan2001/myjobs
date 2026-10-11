#!/usr/bin/env python3
"""Backfill locations_raw on existing job_posting rows.

Detects non-US countries from job titles (fast) then descriptions (slower).
Jobs confirmed as non-US get locations_raw set to the country name array.
US-only and unknown jobs keep locations_raw = NULL (the filter treats NULL
as "include" — conservative, avoids dropping legitimate US/Remote jobs).

Usage:
    python scripts/backfill_locations.py
"""

from __future__ import annotations

import asyncio
import time

import asyncpg

DB_DSN = "postgresql://crawler:crawler@localhost:5432/crawler"

# ── Country patterns for title-based detection ───────────────────────
# Each entry: (ARRAY literal for locations_raw, ilike pattern)
# Order matters: more specific patterns first.

_TITLE_PATTERNS: list[tuple[str, str]] = [
    # Non-US countries — explicit city/country names in titles
    ("ARRAY['India']",        "%India%"),
    ("ARRAY['India']",        "%Bangalore%"),
    ("ARRAY['India']",        "%Bengaluru%"),
    ("ARRAY['India']",        "%Mumbai%"),
    ("ARRAY['India']",        "%Delhi%"),
    ("ARRAY['India']",        "%Hyderabad%"),
    ("ARRAY['India']",        "%Pune%"),
    ("ARRAY['India']",        "%Chennai%"),
    ("ARRAY['India']",        "%Kolkata%"),
    ("ARRAY['India']",        "%Gurugram%"),
    ("ARRAY['India']",        "%Noida%"),
    ("ARRAY['Egypt']",        "%Egypt%"),
    ("ARRAY['Egypt']",        "%Cairo%"),
    ("ARRAY['Nigeria']",      "%Nigeria%"),
    ("ARRAY['Nigeria']",      "%Lagos%"),
    ("ARRAY['Nigeria']",      "%Abuja%"),
    ("ARRAY['Pakistan']",     "%Pakistan%"),
    ("ARRAY['Pakistan']",     "%Karachi%"),
    ("ARRAY['Pakistan']",     "%Lahore%"),
    ("ARRAY['Bangladesh']",   "%Bangladesh%"),
    ("ARRAY['Bangladesh']",   "%Dhaka%"),
    ("ARRAY['Australia']",    "%Australia%"),
    ("ARRAY['Australia']",    "%Sydney%"),
    ("ARRAY['Australia']",    "%Melbourne%"),
    ("ARRAY['Australia']",    "%Brisbane%"),
    ("ARRAY['Australia']",    "%Perth%"),
    ("ARRAY['New Zealand']",  "%New Zealand%"),
    ("ARRAY['New Zealand']",  "%Auckland%"),
    ("ARRAY['New Zealand']",  "%Wellington%"),
    ("ARRAY['United Kingdom']", "%United Kingdom%"),
    ("ARRAY['United Kingdom']", "% UK%"),
    ("ARRAY['United Kingdom']", "%London%"),
    ("ARRAY['United Kingdom']", "%Manchester%"),
    ("ARRAY['United Kingdom']", "%Birmingham%"),
    ("ARRAY['United Kingdom']", "%Edinburgh%"),
    ("ARRAY['Germany']",      "%Germany%"),
    ("ARRAY['Germany']",      "%Berlin%"),
    ("ARRAY['Germany']",      "%Munich%"),
    ("ARRAY['Germany']",      "%Hamburg%"),
    ("ARRAY['Germany']",      "%Frankfurt%"),
    ("ARRAY['France']",       "%France%"),
    ("ARRAY['France']",       "%Paris%"),
    ("ARRAY['Canada']",       "%Canada%"),
    ("ARRAY['Canada']",       "%Toronto%"),
    ("ARRAY['Canada']",       "%Vancouver%"),
    ("ARRAY['Canada']",       "%Montreal%"),
    ("ARRAY['Canada']",       "%Ottawa%"),
    ("ARRAY['Singapore']",    "%Singapore%"),
    ("ARRAY['Poland']",       "%Poland%"),
    ("ARRAY['Poland']",       "%Warsaw%"),
    ("ARRAY['Poland']",       "%Kraków%"),
    ("ARRAY['Netherlands']",  "%Netherlands%"),
    ("ARRAY['Netherlands']",  "%Amsterdam%"),
    ("ARRAY['Spain']",        "%Spain%"),
    ("ARRAY['Spain']",        "%Madrid%"),
    ("ARRAY['Spain']",        "%Barcelona%"),
    ("ARRAY['Italy']",        "%Italy%"),
    ("ARRAY['Italy']",        "%Milan%"),
    ("ARRAY['Italy']",        "%Rome%"),
    ("ARRAY['Ireland']",      "%Ireland%"),
    ("ARRAY['Ireland']",      "%Dublin%"),
    ("ARRAY['South Africa']", "%South Africa%"),
    ("ARRAY['South Africa']", "%Johannesburg%"),
    ("ARRAY['South Africa']", "%Cape Town%"),
    ("ARRAY['Kenya']",        "%Kenya%"),
    ("ARRAY['Kenya']",        "%Nairobi%"),
    ("ARRAY['Israel']",       "%Israel%"),
    ("ARRAY['Israel']",       "%Tel Aviv%"),
    ("ARRAY['UAE']",          "%UAE%"),
    ("ARRAY['UAE']",          "% Dubai%"),
    ("ARRAY['UAE']",          "%Abu Dhabi%"),
    ("ARRAY['Japan']",        "%Japan%"),
    ("ARRAY['Japan']",        "%Tokyo%"),
    ("ARRAY['Japan']",        "%Osaka%"),
    ("ARRAY['China']",        "%China%"),
    ("ARRAY['China']",        "%Beijing%"),
    ("ARRAY['China']",        "%Shanghai%"),
    ("ARRAY['China']",        "%Shenzhen%"),
    ("ARRAY['South Korea']",  "%South Korea%"),
    ("ARRAY['South Korea']",  "%Seoul%"),
    ("ARRAY['Brazil']",       "%Brazil%"),
    ("ARRAY['Brazil']",       "%São Paulo%"),
    ("ARRAY['Brazil']",       "%Sao Paulo%"),
    ("ARRAY['Mexico']",       "%Mexico%"),
    ("ARRAY['Argentina']",    "%Argentina%"),
    ("ARRAY['Argentina']",    "%Buenos Aires%"),
    ("ARRAY['Philippines']",  "%Philippines%"),
    ("ARRAY['Philippines']",  "%Manila%"),
    ("ARRAY['Indonesia']",    "%Indonesia%"),
    ("ARRAY['Indonesia']",    "%Jakarta%"),
    ("ARRAY['Vietnam']",      "%Vietnam%"),
    ("ARRAY['Vietnam']",      "%Ho Chi Minh%"),
    ("ARRAY['Thailand']",     "%Thailand%"),
    ("ARRAY['Thailand']",     "%Bangkok%"),
    ("ARRAY['Malaysia']",     "%Malaysia%"),
    ("ARRAY['Malaysia']",     "%Kuala Lumpur%"),
    ("ARRAY['Sweden']",       "%Sweden%"),
    ("ARRAY['Sweden']",       "%Stockholm%"),
    ("ARRAY['Switzerland']",  "%Switzerland%"),
    ("ARRAY['Switzerland']",  "%Zurich%"),
    ("ARRAY['Switzerland']",  "%Geneva%"),
    ("ARRAY['Norway']",       "%Norway%"),
    ("ARRAY['Norway']",       "%Oslo%"),
    ("ARRAY['Denmark']",      "%Denmark%"),
    ("ARRAY['Denmark']",      "%Copenhagen%"),
    ("ARRAY['Finland']",      "%Finland%"),
    ("ARRAY['Finland']",      "%Helsinki%"),
    ("ARRAY['Czech Republic']", "%Czech Republic%"),
    ("ARRAY['Czech Republic']", "%Prague%"),
    ("ARRAY['Romania']",      "%Romania%"),
    ("ARRAY['Romania']",      "%Bucharest%"),
    ("ARRAY['Ukraine']",      "%Ukraine%"),
    ("ARRAY['Ukraine']",      "%Kyiv%"),
    ("ARRAY['Russia']",       "%Russia%"),
    ("ARRAY['Russia']",       "%Moscow%"),
    ("ARRAY['Turkey']",       "%Turkey%"),
    ("ARRAY['Turkey']",       "%Istanbul%"),
    ("ARRAY['Saudi Arabia']", "%Saudi Arabia%"),
    ("ARRAY['Saudi Arabia']", "%Riyadh%"),
    ("ARRAY['Hong Kong']",    "%Hong Kong%"),
    ("ARRAY['Taiwan']",       "%Taiwan%"),
    ("ARRAY['Taiwan']",       "%Taipei%"),
]

# For description-based detection: non-US terms that are unambiguous
_DESC_NON_US: list[tuple[str, str]] = [
    ("ARRAY['India']",        r"\yIndia\y"),
    ("ARRAY['India']",        r"\yBangalore\y"),
    ("ARRAY['India']",        r"\yBengaluru\y"),
    ("ARRAY['India']",        r"\yMumbai\y"),
    ("ARRAY['India']",        r"\yDelhi\y"),
    ("ARRAY['India']",        r"\yHyderabad\y"),
    ("ARRAY['India']",        r"\yPune\y"),
    ("ARRAY['India']",        r"\yChennai\y"),
    ("ARRAY['Egypt']",        r"\yEgypt\y"),
    ("ARRAY['Egypt']",        r"\yCairo\y"),
    ("ARRAY['Nigeria']",      r"\yNigeria\y"),
    ("ARRAY['Nigeria']",      r"\yLagos\y"),
    ("ARRAY['Australia']",    r"\yAustralia\y"),
    ("ARRAY['New Zealand']",  r"\yNew Zealand\y"),
    ("ARRAY['New Zealand']",  r"\yAuckland\y"),
    ("ARRAY['United Kingdom']", r"\yUnited Kingdom\y"),
    ("ARRAY['Germany']",      r"\yGermany\y"),
    ("ARRAY['France']",       r"\yFrance\y"),
    ("ARRAY['Canada']",       r"\yCanada\y"),
    ("ARRAY['Singapore']",    r"\ySingapore\y"),
    ("ARRAY['Japan']",        r"\yJapan\y"),
    ("ARRAY['China']",        r"\bChina\b"),
    ("ARRAY['Brazil']",       r"\yBrazil\y"),
    ("ARRAY['Mexico']",       r"\yMexico\y"),
]


async def run_title_backfill(conn: asyncpg.Connection) -> int:
    print("Step 1: Title-based location detection…")
    t0 = time.time()
    total_updated = 0

    for array_lit, pattern in _TITLE_PATTERNS:
        sql = (
            f"UPDATE job_posting SET locations_raw = {array_lit} "
            f"WHERE locations_raw IS NULL AND titles[1] ILIKE $1"
        )
        result = await conn.execute(sql, pattern)
        n = int(result.split()[-1])
        if n:
            total_updated += n

    print(f"  title-based: {total_updated:,} rows updated in {time.time()-t0:.1f}s")
    return total_updated


async def run_description_backfill(conn: asyncpg.Connection) -> int:
    print("Step 2: Description-based location detection…")
    t0 = time.time()

    # Check if descriptions table exists
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='descriptions')"
    )
    if not exists:
        print("  no descriptions table — skipping")
        return 0

    total_updated = 0
    for array_lit, pattern in _DESC_NON_US:
        sql = (
            f"UPDATE job_posting jp SET locations_raw = {array_lit} "
            f"FROM descriptions d "
            f"WHERE d.posting_id = jp.id AND d.locale = 'en' "
            f"AND jp.locations_raw IS NULL "
            f"AND d.html ~* $1"
        )
        result = await conn.execute(sql, pattern)
        n = int(result.split()[-1])
        if n:
            total_updated += n

    print(f"  description-based: {total_updated:,} rows updated in {time.time()-t0:.1f}s")
    return total_updated


async def main() -> None:
    print(f"Connecting to {DB_DSN}")
    conn = await asyncpg.connect(DB_DSN)
    try:
        t1 = await run_title_backfill(conn)
        t2 = await run_description_backfill(conn)

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM job_posting WHERE locations_raw IS NOT NULL AND is_active"
        )
        active = await conn.fetchval("SELECT COUNT(*) FROM job_posting WHERE is_active")
        print(f"\nDone. locations_raw set on {total:,}/{active:,} active jobs "
              f"({total/max(active,1)*100:.1f}%)")
        print(f"  (null = unknown/US — included by the US filter conservatively)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
