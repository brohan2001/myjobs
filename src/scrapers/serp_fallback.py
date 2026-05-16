from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from src.scrapers.base import BaseScraper

# Pages to skip — not individual job listings
_SKIP_TITLES = frozenset([
    "careers at", "jobs at", "work at", "life at", "about us",
    "our culture", "company overview", "meet the team",
    "get personalized", "job recommendations",
])
_SKIP_PATH_SEGMENTS = frozenset([
    "teams", "careerprograms", "students", "culture", "belonging",
    "life", "about", "blog", "community", "jobsearch",
])


class SerpFallbackScraper(BaseScraper):
    """Scrape job listings via DuckDuckGo text search (ddgs package).

    Used for companies whose primary careers pages require auth or have
    no clean public API (Meta, Retool/Gem, Coinbase).

    ddgs bypasses HTML-level rate limiting by hitting DDG's backend API
    directly — no CAPTCHA, no session management.
    """

    def __init__(self):
        super().__init__(rate_limit_rps=0.1)  # 1 req / 10s — be polite

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        query = company.get("serp_query", "")
        if not query:
            return []

        try:
            from ddgs import DDGS
        except ImportError:
            return []

        # Rate limit
        elapsed = __import__("time").monotonic() - self._last_request
        wait = self._min_interval - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

        # ddgs is sync — run in thread pool to avoid blocking the event loop
        try:
            raw_results: list[dict] = await asyncio.to_thread(
                _ddgs_search, query, max_results=20
            )
        except Exception:
            return []
        finally:
            self._last_request = __import__("time").monotonic()

        return _parse_results(raw_results, company_id)


def _ddgs_search(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS
    with DDGS() as ddgs:
        return ddgs.text(query, max_results=max_results) or []


def _is_generic_page(url: str, title: str) -> bool:
    lower = title.lower()
    if any(skip in lower for skip in _SKIP_TITLES):
        return True
    path_parts = set(urlparse(url).path.strip("/").split("/"))
    if path_parts & _SKIP_PATH_SEGMENTS:
        return True
    return False


def _parse_results(results: list[dict], company_id: int) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    for r in results:
        url = r.get("href", "")
        title = r.get("title", "")
        snippet = r.get("body", "")

        if not url or not title:
            continue
        if url in seen:
            continue
        seen.add(url)

        if _is_generic_page(url, title):
            continue

        path = urlparse(url).path
        external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", path.strip("/"))[:80]
        if not external_id:
            external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", url)[:80]

        jobs.append({
            "external_id": external_id,
            "company_id":  company_id,
            "title":       title,
            "description": snippet,
            "location":    "",
            "remote":      0,
            "url":         url,
            "posted_date": None,
            "posted_at":   None,
            "ats_type":    "serp",
        })

    return jobs
