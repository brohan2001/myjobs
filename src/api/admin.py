"""Admin API for the /admin pages (D31): crawl freshness per board, errors, health, resource usage, and
recrawl/enable/disable. Every route needs ``Authorization: Bearer $ADMIN_TOKEN``; without a token configured they 404.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src import health, sysstats
from src.api import queries
from src.config import settings
from src.logger import get_logger

log = get_logger(__name__)

PAGE_SIZE = 100
BACKUP_DIR = Path.home() / "backups"


def require_admin(request: Request) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=404)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), settings.admin_token.encode()):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)], include_in_schema=False)


def _jsonable(row) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, UUID) else v)
            for k, v in dict(row).items()}


async def _queues() -> dict | None:
    from src.redis_queue import get_deadletter_depth, get_inflight_depth, get_queue_depths

    try:
        depths = await get_queue_depths()
        return {
            wtype: {
                "ready_now": sum(v for k, v in depths.items() if k.startswith(f"ready:{wtype}:") and k.endswith(":ready")),
                "inflight": await get_inflight_depth(browser=wtype == "browser"),
                "deadletter": await get_deadletter_depth(browser=wtype == "browser"),
            }
            for wtype in ("simple", "browser")
        }
    except Exception:  # noqa: BLE001 - Redis down is itself worth showing, not a 500
        log.warning("admin.queues.unavailable", exc_info=True)
        return None


def _latest_backup() -> dict | None:
    dumps = sorted(BACKUP_DIR.glob("myjobs-*.dump"), key=lambda p: p.stat().st_mtime)
    if not dumps:
        return None
    st = dumps[-1].stat()
    return {"file": dumps[-1].name, "bytes": st.st_size, "at": datetime.fromtimestamp(st.st_mtime, UTC).isoformat()}


@router.get("/overview")
async def overview(request: Request):
    pool = request.app.state.pool
    stats = await queries.fetch_stats(pool)
    snap = await health.fetch_snapshot(pool)
    return {
        "stats": _jsonable(stats),
        "health": {
            "feed_age_minutes": snap.feed_age_minutes,
            "active_boards": snap.active_boards,
            "overdue_boards": snap.overdue_boards,
            "gone_last_day": snap.gone_last_day,
            "alerts": [{"check": a.check, "message": a.message} for a in health.evaluate(snap)],
        },
        "queues": await _queues(),
        "backup": _latest_backup(),
    }


@router.get("/boards")
async def boards(
    request: Request,
    q: str | None = Query(None, max_length=100),
    ats: str | None = Query(None, max_length=50),
    status: str = Query("all"),
    sort: str = Query("stale"),
    page: int = Query(1, ge=1, le=1000),
):
    if status not in health.BOARD_STATUSES or sort not in health.BOARD_SORTS:
        raise HTTPException(status_code=400, detail="unknown status or sort")
    rows = await health.fetch_boards(request.app.state.pool, q.strip() if q and q.strip() else None, PAGE_SIZE + 1,
                                     ats=ats or None, status=status, sort=sort, offset=(page - 1) * PAGE_SIZE)
    return {"boards": [_jsonable(r) for r in rows[:PAGE_SIZE]], "has_more": len(rows) > PAGE_SIZE}


@router.get("/errors")
async def errors(request: Request):
    return {"errors": [dict(r) for r in await health.fetch_errors(request.app.state.pool)]}


@router.get("/system")
async def system():
    return await sysstats.snapshot()


# --- Board actions -----------------------------------------------------------------------------------------------

_BOARD_CONFIG_COLS = """id, board_url, crawler_type, company_id, metadata, check_interval_minutes, scrape_interval_hours,
                        throttle_key, monitor_needs_browser, scraper_needs_browser"""
_RECRAWL = f"UPDATE job_board SET next_check_at = now(), updated_at = now() WHERE id = $1 AND is_enabled " \
           f"RETURNING {_BOARD_CONFIG_COLS}"
_ENABLE = f"""
UPDATE job_board SET is_enabled = true, board_status = 'active', consecutive_failures = 0, empty_check_count = 0,
                     gone_at = NULL, next_check_at = now(), updated_at = now()
WHERE id = $1 RETURNING {_BOARD_CONFIG_COLS}
"""
_DISABLE = """
UPDATE job_board SET is_enabled = false, board_status = 'disabled', updated_at = now()
WHERE id = $1 RETURNING id, throttle_key
"""
_DEACTIVATE_POSTINGS = "UPDATE job_posting SET is_active = false, updated_at = now() WHERE board_id = $1 AND is_active"


async def _enqueue_now(row) -> None:
    """Put the board at the front of the worker's queue, with the same config `myjobs sync` stores."""
    from src.redis_queue import enqueue_monitor

    metadata = row["metadata"]
    config = {
        "board_url": row["board_url"],
        "crawler_type": row["crawler_type"],
        "company_id": str(row["company_id"]),
        "metadata": metadata if isinstance(metadata, str) else json.dumps(metadata or {}),
        "check_interval_minutes": str(row["check_interval_minutes"]),
        "scrape_interval_hours": str(row["scrape_interval_hours"]),
        "throttle_key": row["throttle_key"],
        "monitor_needs_browser": "1" if row["monitor_needs_browser"] else "0",
        "scraper_needs_browser": "1" if row["scraper_needs_browser"] else "0",
    }
    await enqueue_monitor(row["throttle_key"], str(row["id"]), time.time(), config,
                          browser=row["monitor_needs_browser"], first_time=True)


async def _update(request: Request, sql: str, board_id: UUID, *, deactivate_postings: bool = False):
    async with request.app.state.pool.acquire() as conn:
        row = await conn.fetchrow(sql, board_id)
        if row is not None and deactivate_postings:
            await conn.execute(_DEACTIVATE_POSTINGS, board_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Board not found (or disabled)")
    return row


@router.post("/boards/{board_id}/recrawl")
async def recrawl(request: Request, board_id: UUID):
    await _enqueue_now(await _update(request, _RECRAWL, board_id))
    log.info("admin.board.recrawl", extra={"board_id": str(board_id)})
    return {"ok": True}


@router.post("/boards/{board_id}/enable")
async def enable(request: Request, board_id: UUID):
    await _enqueue_now(await _update(request, _ENABLE, board_id))
    log.info("admin.board.enable", extra={"board_id": str(board_id)})
    return {"ok": True}


@router.post("/boards/{board_id}/disable")
async def disable(request: Request, board_id: UUID):
    from src.redis_queue import remove_monitor

    row = await _update(request, _DISABLE, board_id, deactivate_postings=True)
    if row["throttle_key"]:
        await remove_monitor(row["throttle_key"], str(board_id))
    log.info("admin.board.disable", extra={"board_id": str(board_id)})
    return {"ok": True}
