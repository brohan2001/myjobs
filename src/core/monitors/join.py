"""JOIN (join.com) monitor — pre-configured nextdata monitor.

JOIN career pages are Next.js apps with job data embedded in
``__NEXT_DATA__`` at ``props.pageProps.initialState.jobs`` (``pageData.jobs`` on pages
migrated since 2026-10, so ``_JOBS`` accepts both).  Server-side
pagination is fixed at 5 jobs per page (``?page=N``).

Board config only needs a slug::

    {"slug": "acme"}

The slug is auto-derived from the board URL when omitted.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog

from src.core.monitors import fetch_page_text, register
from src.core.monitors.nextdata import discover as nextdata_discover
from src.shared.nextdata import extract_next_data, resolve_path

if TYPE_CHECKING:
    import httpx

log = structlog.get_logger()

# myjobs delta: join moved initialState to pageData board by board (2026-10); accept either.
_JOBS = "(props.pageProps.pageData || props.pageProps.initialState).jobs"

_SLUG_RE = re.compile(r"^/companies/([\w-]+)")


def _slug_from_url(url: str) -> str | None:
    """Extract the company slug from a join.com URL."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ("join.com", "www.join.com"):
        return None
    match = _SLUG_RE.match(parsed.path)
    return match.group(1) if match else None


def _build_metadata(slug: str) -> dict:
    """Build the full nextdata metadata dict for a JOIN company."""
    return {
        "path": f"{_JOBS}.items",
        "url_template": f"https://join.com/companies/{slug}/{{idParam}}",
        "board_gone_statuses": [404, 410],
        "pagination": {
            "path": f"{_JOBS}.pagination",
            "page_count": "pageCount",
            "page_param": "page",
        },
    }


async def discover(board: dict, client: httpx.AsyncClient, pw=None) -> set[str]:
    """Discover jobs from a JOIN career page via nextdata."""
    metadata = board.get("metadata") or {}
    board_url = board["board_url"]

    slug = metadata.get("slug") or _slug_from_url(board_url)
    if not slug:
        log.error("join.missing_slug", board_url=board_url)
        return set()

    nextdata_board = {
        "board_url": board_url,
        "metadata": _build_metadata(slug),
    }
    return await nextdata_discover(nextdata_board, client, pw=pw)


async def can_handle(url: str, client: httpx.AsyncClient | None = None, pw=None) -> dict | None:
    """Detect a join.com career page."""
    slug = _slug_from_url(url)
    if not slug:
        return None

    if client is None:
        return {"slug": slug}

    # Verify the page has job data
    html = await fetch_page_text(url, client)
    if not html:
        return None
    data = extract_next_data(html)
    if not data:
        return None

    items = resolve_path(data, f"{_JOBS}.items")
    if not isinstance(items, list):
        return None

    pagination = resolve_path(data, f"{_JOBS}.pagination")
    total = pagination.get("total") if isinstance(pagination, dict) else len(items)

    log.info("join.detected", url=url, slug=slug, jobs=total)
    return {"slug": slug, "jobs": total}


register("join", discover, cost=9, can_handle=can_handle, rich=False)
