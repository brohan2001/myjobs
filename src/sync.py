"""CSV -> local Postgres + Redis sync.

Reads data/companies.csv and data/boards.csv and upserts rows into
local PostgreSQL (full board config with scheduling columns) and Redis
(board config hashes + initial monitor schedule).

No Supabase, no Typesense — local-only variant of jobseek's sync.py.

Usage:
    crawler sync
    crawler sync --dry-run
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import polars as pl
import structlog

from src.config import settings
from src.core.monitors import api_monitor_types, monitor_needs_browser
from src.core.scrapers import scraper_needs_browser
from src.db import close_all_pools, create_local_pool
from src.redis_queue import close_redis, enqueue_monitor, remove_monitor
from src.shared.logging import setup_logging

_API_MONITOR_TYPES = api_monitor_types()

log = structlog.get_logger()

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_UPSERT_COMPANIES = """
INSERT INTO company (slug, name, website, tier, extras)
SELECT slug, name, website, tier, tags::jsonb
FROM unnest($1::text[], $2::text[], $3::text[], $4::int[], $5::text[])
  AS c(slug, name, website, tier, tags)
ON CONFLICT (slug) DO UPDATE SET
    name    = COALESCE(EXCLUDED.name,    company.name),
    website = COALESCE(EXCLUDED.website, company.website),
    tier    = EXCLUDED.tier,
    extras  = COALESCE(company.extras, '{}'::jsonb) || EXCLUDED.extras,
    updated_at = now()
"""

# Optional registry tags in companies.csv, stored in company.extras.
_COMPANY_TAG_COLUMNS = ("country", "hq_city", "company_type")

# Generate a fresh UUID on first insert; reuse existing on conflict.
# ON CONFLICT (board_url) so we don't need a Supabase-assigned ID.
_UPSERT_BOARDS_LOCAL = """
INSERT INTO job_board (
    id, company_id, board_slug, board_url,
    crawler_type, metadata,
    check_interval_minutes, scrape_interval_hours,
    throttle_key, monitor_needs_browser, scraper_needs_browser,
    is_enabled
)
SELECT
    gen_random_uuid(), c.id, b.board_slug, b.board_url,
    b.crawler_type, b.metadata::jsonb,
    b.check_interval_minutes::int, b.scrape_interval_hours::int,
    b.throttle_key, b.monitor_needs_browser::boolean, b.scraper_needs_browser::boolean,
    true
FROM unnest(
    $1::text[], $2::text[], $3::text[], $4::text[],
    $5::text[], $6::text[], $7::text[],
    $8::text[], $9::text[], $10::text[]
) AS b(
    company_slug, board_slug, board_url, crawler_type,
    metadata, check_interval_minutes, scrape_interval_hours,
    throttle_key, monitor_needs_browser, scraper_needs_browser
)
JOIN company c ON c.slug = b.company_slug
ON CONFLICT (board_url) DO UPDATE SET
    company_id             = EXCLUDED.company_id,
    board_slug             = COALESCE(EXCLUDED.board_slug, job_board.board_slug),
    crawler_type           = EXCLUDED.crawler_type,
    metadata               = EXCLUDED.metadata || jsonb_strip_nulls(jsonb_build_object(
        'sitemap_url',               job_board.metadata -> 'sitemap_url',
        'recent_discovered_counts',  job_board.metadata -> 'recent_discovered_counts',
        'suspect_streak',            job_board.metadata -> 'suspect_streak'
    )),
    check_interval_minutes = EXCLUDED.check_interval_minutes,
    scrape_interval_hours  = EXCLUDED.scrape_interval_hours,
    throttle_key           = EXCLUDED.throttle_key,
    monitor_needs_browser  = EXCLUDED.monitor_needs_browser,
    scraper_needs_browser  = EXCLUDED.scraper_needs_browser,
    is_enabled             = CASE
        WHEN job_board.board_status IN ('disabled', 'gone') THEN false
        ELSE true
    END,
    updated_at             = now()
"""

# A board whose URL changed in the registry (same slug, e.g. an ATS move fixed upstream) keeps its
# row: move it to the new URL and give it a fresh start, so the upsert below updates it instead of
# colliding on the unique board_slug.
_MOVE_CHANGED_URLS = """
UPDATE job_board jb
SET board_url = b.board_url, board_status = 'active', is_enabled = true,
    consecutive_failures = 0, gone_at = NULL, last_error = NULL, updated_at = now()
FROM unnest($1::text[], $2::text[]) AS b(board_slug, board_url)
WHERE jb.board_slug = b.board_slug
  AND jb.board_url <> b.board_url
  AND NOT EXISTS (SELECT 1 FROM job_board o WHERE o.board_url = b.board_url)
"""

_DISABLE_REMOVED_BOARDS = """
UPDATE job_board
SET is_enabled = false, board_status = 'disabled', updated_at = now()
WHERE board_url != ALL($1::text[])
  AND is_enabled = true
"""

# A disabled board is never checked again, so its postings would stay "active" forever (28k did on
# 2026-10-15). They come back through the relisted path if the board is re-enabled.
_DEACTIVATE_DISABLED_BOARD_POSTINGS = """
UPDATE job_posting jp SET is_active = false, updated_at = now()
FROM job_board b
WHERE jp.board_id = b.id AND jp.is_active AND NOT b.is_enabled
"""

_FETCH_DISABLED_BOARDS_FOR_REDIS_CLEANUP = """
SELECT id::text AS board_id, throttle_key
FROM job_board
WHERE is_enabled = false OR board_status IN ('disabled', 'gone')
"""

_FETCH_BOARD_IDS = """
SELECT id, company_id, board_url FROM job_board WHERE board_url = ANY($1::text[])
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _or_none(val: str | None) -> str | None:
    return val if val else None


def _int_or(val: str | None, default: int) -> int:
    if not val:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _compute_throttle_key(monitor_type: str, board_url: str) -> str:
    if monitor_type in _API_MONITOR_TYPES:
        return monitor_type
    return urlparse(board_url).hostname or board_url


def _load_companies() -> pl.DataFrame:
    path = DATA_DIR / "companies.csv"
    df = pl.read_csv(path, infer_schema_length=0)
    log.info("sync.loaded_companies", count=len(df), path=str(path))
    return df


def _load_boards() -> pl.DataFrame:
    path = DATA_DIR / "boards.csv"
    df = pl.read_csv(path, infer_schema_length=0)
    log.info("sync.loaded_boards", count=len(df), path=str(path))
    return df


# ---------------------------------------------------------------------------
# Sync functions
# ---------------------------------------------------------------------------


async def sync_companies(conn, companies: pl.DataFrame, dry_run: bool) -> None:
    if len(companies) == 0:
        return

    slugs: list[str] = []
    names: list[str] = []
    websites: list[str | None] = []
    tiers: list[int] = []
    tags: list[str] = []

    for row in companies.iter_rows(named=True):
        enabled = row.get("enabled", "true")
        if enabled and str(enabled).lower() in ("false", "0", "no"):
            continue
        slugs.append(row["slug"])
        names.append(row["name"])
        websites.append(_or_none(row.get("website")))
        tiers.append(_int_or(row.get("tier"), 2))
        tags.append(json.dumps({k: row[k] for k in _COMPANY_TAG_COLUMNS if row.get(k)}))

    if dry_run:
        log.info("sync.companies.dry_run", count=len(slugs))
        return

    await conn.execute(_UPSERT_COMPANIES, slugs, names, websites, tiers, tags)
    log.info("sync.companies.upserted", count=len(slugs))


async def sync_boards(conn, boards: pl.DataFrame, dry_run: bool) -> None:
    if len(boards) == 0:
        return

    company_slugs: list[str] = []
    board_slugs_list: list[str | None] = []
    board_urls: list[str] = []
    crawler_types: list[str] = []
    metadatas: list[str] = []
    metadata_objs: list[dict] = []
    check_intervals: list[str] = []
    scrape_intervals: list[str] = []
    throttle_keys: list[str] = []
    monitor_browser_flags: list[str] = []
    scraper_browser_flags: list[str] = []
    skipped = 0
    seen_urls: set[str] = set()  # deduplicate by board_url within one batch

    for row in boards.iter_rows(named=True):
        monitor_config_str = row.get("monitor_config") or None
        scraper_type = _or_none(row.get("scraper_type"))
        scraper_config_str = row.get("scraper_config") or None
        metadata_obj: dict = {}

        if monitor_config_str:
            try:
                parsed = json.loads(monitor_config_str)
                if not isinstance(parsed, dict):
                    raise ValueError("monitor_config must be a JSON object")
                metadata_obj.update(parsed)
            except (json.JSONDecodeError, ValueError):
                log.error(
                    "sync.board.invalid_config",
                    board_url=row["board_url"],
                    config=monitor_config_str,
                )
                skipped += 1
                continue

        if scraper_type and scraper_type != "skip":
            metadata_obj["scraper_type"] = scraper_type

        if scraper_config_str:
            try:
                scraper_cfg = json.loads(scraper_config_str)
                if not isinstance(scraper_cfg, dict):
                    raise ValueError("scraper_config must be a JSON object")
                metadata_obj["scraper_config"] = scraper_cfg
            except (json.JSONDecodeError, ValueError):
                log.error(
                    "sync.board.invalid_scraper_config",
                    board_url=row["board_url"],
                    config=scraper_config_str,
                )
                skipped += 1
                continue

        mon_type = row["monitor_type"]
        mon_browser = monitor_needs_browser(mon_type, metadata_obj)
        scr_type = metadata_obj.get("scraper_type")
        scr_cfg = metadata_obj.get("scraper_config")
        scr_browser = scraper_needs_browser(scr_type, scr_cfg) if scr_type else False
        if not scr_browser and scr_cfg and isinstance(scr_cfg, dict):
            for fb in scr_cfg.get("fallback", []):
                fb_type = fb if isinstance(fb, str) else fb.get("type", "")
                fb_cfg = None if isinstance(fb, str) else fb.get("config")
                if scraper_needs_browser(fb_type, fb_cfg):
                    scr_browser = True
                    break

        url = row["board_url"]
        if url in seen_urls:
            log.warning("sync.board.duplicate_url_skipped", board_url=url, company_slug=row["company_slug"])
            skipped += 1
            continue
        seen_urls.add(url)

        company_slugs.append(row["company_slug"])
        board_slugs_list.append(_or_none(row.get("board_slug")))
        board_urls.append(url)
        crawler_types.append(mon_type)
        metadatas.append(json.dumps(metadata_obj) if metadata_obj else "{}")
        metadata_objs.append(metadata_obj)
        check_intervals.append("60")
        scrape_intervals.append("24")
        throttle_keys.append(_compute_throttle_key(mon_type, row["board_url"]))
        monitor_browser_flags.append("1" if mon_browser else "0")
        scraper_browser_flags.append("1" if scr_browser else "0")

    if dry_run:
        log.info("sync.boards.dry_run", count=len(board_urls), skipped=skipped)
        return

    if not board_urls:
        log.info("sync.boards.all_skipped", skipped=skipped)
        return

    moved = await conn.execute(_MOVE_CHANGED_URLS, board_slugs_list, board_urls)
    log.info("sync.boards.url_changed", result=moved)

    # Upsert boards into local Postgres (generates UUIDs on first insert)
    await conn.execute(
        _UPSERT_BOARDS_LOCAL,
        company_slugs,
        board_slugs_list,
        board_urls,
        crawler_types,
        metadatas,
        check_intervals,
        scrape_intervals,
        throttle_keys,
        monitor_browser_flags,
        scraper_browser_flags,
    )
    log.info("sync.boards.upserted_local", count=len(board_urls), skipped=skipped)

    # Disable boards no longer in the CSV
    await conn.execute(_DISABLE_REMOVED_BOARDS, board_urls)
    stale = await conn.execute(_DEACTIVATE_DISABLED_BOARD_POSTINGS)
    log.info("sync.postings.deactivated_for_disabled_boards", result=stale)

    # Fetch IDs that Postgres just assigned
    id_rows = await conn.fetch(_FETCH_BOARD_IDS, board_urls)
    url_to_ids: dict[str, tuple] = {r["board_url"]: (r["id"], r["company_id"]) for r in id_rows}

    # Enqueue each board into Redis
    redis_enqueued = 0
    for i, board_url in enumerate(board_urls):
        ids = url_to_ids.get(board_url)
        if not ids:
            log.warning("sync.board.missing_id", board_url=board_url)
            continue

        board_id, company_id = ids
        mon_type = crawler_types[i]
        mon_browser = monitor_browser_flags[i] == "1"

        config = {
            "board_url": board_url,
            "crawler_type": mon_type,
            "company_id": str(company_id),
            "metadata": metadatas[i],
            "check_interval_minutes": check_intervals[i],
            "scrape_interval_hours": scrape_intervals[i],
            "throttle_key": throttle_keys[i],
            "monitor_needs_browser": monitor_browser_flags[i],
            "scraper_needs_browser": scraper_browser_flags[i],
        }
        await enqueue_monitor(
            throttle_keys[i],
            str(board_id),
            time.time(),
            config,
            browser=mon_browser,
            first_time=True,
        )
        redis_enqueued += 1

    # Purge Redis for disabled boards
    orphan_rows = await conn.fetch(_FETCH_DISABLED_BOARDS_FOR_REDIS_CLEANUP)
    for row in orphan_rows:
        domain = row["throttle_key"] or ""
        if domain:
            await remove_monitor(domain, row["board_id"])

    log.info(
        "sync.boards.redis",
        redis_enqueued=redis_enqueued,
        redis_orphans_removed=len(orphan_rows),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_sync(dry_run: bool = False) -> None:
    setup_logging(settings.log_level)

    companies = _load_companies()
    boards = _load_boards()

    if len(companies) == 0 and len(boards) == 0:
        log.info("sync.empty", msg="No data in CSVs, nothing to sync")
        return

    local_pool = await create_local_pool()
    try:
        async with local_pool.acquire() as conn:
            async with conn.transaction():
                await sync_companies(conn, companies, dry_run)
                await sync_boards(conn, boards, dry_run)
    finally:
        await close_all_pools()
        await close_redis()

    log.info(
        "sync.complete",
        companies=len(companies),
        boards=len(boards),
        dry_run=dry_run,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Sync CSV config to local Postgres + Redis")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_sync(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
