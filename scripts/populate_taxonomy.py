#!/usr/bin/env python3
"""Populate seniority + occupation tables from CSVs, then backfill job_posting.

Run once after deploying migration 0007 (taxonomy tables) on a fresh DB.
Safe to re-run — uses ON CONFLICT DO NOTHING for inserts and skips rows
that already have seniority_id / occupation_id.

Usage:
    python scripts/populate_taxonomy.py
"""

from __future__ import annotations

import asyncio
import csv
import sys
import time
from pathlib import Path

import asyncpg

DB_DSN = "postgresql://crawler:crawler@localhost:5432/crawler"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHUNK = 2000

# ── Resolve imports from project root ────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.core.seniority_resolve import match_seniority
from src.core.occupation_resolve import match_occupation


async def load_seniority(conn: asyncpg.Connection) -> dict[str, int]:
    path = DATA_DIR / "seniority.csv"
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row["slug"])

    await conn.executemany(
        "INSERT INTO seniority (slug) VALUES ($1) ON CONFLICT (slug) DO NOTHING",
        [(s,) for s in rows],
    )
    db_rows = await conn.fetch("SELECT id, slug FROM seniority")
    result = {r["slug"]: r["id"] for r in db_rows}
    print(f"  seniority: {len(result)} rows")
    return result


async def load_occupation_domains(conn: asyncpg.Connection) -> dict[str, int]:
    path = DATA_DIR / "occupation_domains.csv"
    slugs = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slugs.append(row["slug"])

    await conn.executemany(
        "INSERT INTO occupation_domain (slug) VALUES ($1) ON CONFLICT (slug) DO NOTHING",
        [(s,) for s in slugs],
    )
    db_rows = await conn.fetch("SELECT id, slug FROM occupation_domain")
    result = {r["slug"]: r["id"] for r in db_rows}
    print(f"  occupation_domain: {len(result)} rows")
    return result


async def load_occupations(
    conn: asyncpg.Connection, domain_ids: dict[str, int]
) -> dict[str, int]:
    path = DATA_DIR / "occupations.csv"
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((row["slug"], row.get("parent") or None, row.get("domain") or None))

    # Two-pass: parents first (parent column may reference a sibling row)
    # Pass 1: insert all rows with parent=NULL
    await conn.executemany(
        "INSERT INTO occupation (slug, parent_id, domain_id) "
        "VALUES ($1, NULL, (SELECT id FROM occupation_domain WHERE slug = $2)) "
        "ON CONFLICT (slug) DO NOTHING",
        [(slug, domain) for slug, parent, domain in rows if not parent],
    )
    # Pass 2: insert rows with a parent (parent already exists from pass 1)
    await conn.executemany(
        "INSERT INTO occupation (slug, parent_id, domain_id) "
        "VALUES ($1, (SELECT id FROM occupation WHERE slug = $2), "
        "        (SELECT id FROM occupation_domain WHERE slug = $3)) "
        "ON CONFLICT (slug) DO NOTHING",
        [(slug, parent, domain) for slug, parent, domain in rows if parent],
    )

    db_rows = await conn.fetch("SELECT id, slug FROM occupation")
    result = {r["slug"]: r["id"] for r in db_rows}
    print(f"  occupation: {len(result)} rows")
    return result


async def backfill_seniority(conn: asyncpg.Connection, sen_ids: dict[str, int]) -> None:
    print("Backfilling seniority_id…")
    t0 = time.time()
    # Fetch all active jobs with NULL seniority_id that have a title
    rows = await conn.fetch(
        "SELECT id, titles[1] AS title FROM job_posting "
        "WHERE seniority_id IS NULL AND array_length(titles, 1) > 0"
    )
    print(f"  {len(rows):,} jobs to classify")

    updates: list[tuple[int, str]] = []
    for row in rows:
        slug = match_seniority(row["title"] or "")
        if slug and slug in sen_ids:
            updates.append((sen_ids[slug], row["id"]))

    print(f"  {len(updates):,} matched ({len(updates)/max(len(rows),1)*100:.1f}%)")

    for i in range(0, len(updates), CHUNK):
        chunk = updates[i : i + CHUNK]
        await conn.executemany(
            "UPDATE job_posting SET seniority_id = $1 WHERE id = $2",
            chunk,
        )
        print(f"  seniority committed {min(i+CHUNK, len(updates)):,}/{len(updates):,}", end="\r")

    print(f"\n  done in {time.time()-t0:.1f}s")


async def backfill_occupation(conn: asyncpg.Connection, occ_ids: dict[str, int]) -> None:
    print("Backfilling occupation_id…")
    t0 = time.time()
    rows = await conn.fetch(
        "SELECT id, titles[1] AS title FROM job_posting "
        "WHERE occupation_id IS NULL AND array_length(titles, 1) > 0"
    )
    print(f"  {len(rows):,} jobs to classify")

    updates: list[tuple[int, str]] = []
    for row in rows:
        slug = match_occupation(row["title"] or "")
        if slug and slug in occ_ids:
            updates.append((occ_ids[slug], row["id"]))

    print(f"  {len(updates):,} matched ({len(updates)/max(len(rows),1)*100:.1f}%)")

    for i in range(0, len(updates), CHUNK):
        chunk = updates[i : i + CHUNK]
        await conn.executemany(
            "UPDATE job_posting SET occupation_id = $1 WHERE id = $2",
            chunk,
        )
        print(f"  occupation committed {min(i+CHUNK, len(updates)):,}/{len(updates):,}", end="\r")

    print(f"\n  done in {time.time()-t0:.1f}s")


async def main() -> None:
    print(f"Connecting to {DB_DSN}")
    conn = await asyncpg.connect(DB_DSN)
    try:
        print("Loading taxonomy tables…")
        sen_ids = await load_seniority(conn)
        domain_ids = await load_occupation_domains(conn)
        occ_ids = await load_occupations(conn, domain_ids)

        await backfill_seniority(conn, sen_ids)
        await backfill_occupation(conn, occ_ids)

        # Final counts
        s = await conn.fetchval("SELECT COUNT(*) FROM job_posting WHERE seniority_id IS NOT NULL AND is_active")
        o = await conn.fetchval("SELECT COUNT(*) FROM job_posting WHERE occupation_id IS NOT NULL AND is_active")
        total = await conn.fetchval("SELECT COUNT(*) FROM job_posting WHERE is_active")
        print(f"\nDone. Active jobs: {total:,}")
        print(f"  seniority_id set: {s:,} ({s/max(total,1)*100:.1f}%)")
        print(f"  occupation_id set: {o:,} ({o/max(total,1)*100:.1f}%)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
