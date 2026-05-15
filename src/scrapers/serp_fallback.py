from __future__ import annotations

import asyncio
import re
from urllib.parse import urlencode, urlparse, parse_qs

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

_SEARCH_URL = "https://www.google.com/search"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}
# Max result pages to fetch per company (10 results/page)
_MAX_PAGES = 3


class SerpFallbackScraper(BaseScraper):
    """Scrape job listings via Google Search site: queries.

    Used for companies whose primary careers pages require auth or have
    no public API (Google Careers, Meta, Arista, Juniper via LinkedIn).
    Returns fewer results than a direct ATS scraper but beats returning 0.
    """

    def __init__(self):
        super().__init__(rate_limit_rps=0.1)  # 1 req / 10s — be polite

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        query = company.get("serp_query", "")
        if not query:
            return []

        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            return []

        all_jobs: list[dict] = []
        seen_urls: set[str] = set()

        try:
            async with AsyncSession(impersonate="chrome") as session:
                for page in range(_MAX_PAGES):
                    start = page * 10
                    params = {"q": query, "num": 10, "start": start, "hl": "en", "gl": "us"}
                    url = f"{_SEARCH_URL}?{urlencode(params)}"

                    # Rate limit
                    elapsed = __import__("time").monotonic() - self._last_request
                    wait = self._min_interval - elapsed
                    if wait > 0:
                        await asyncio.sleep(wait)

                    resp = await session.get(url, headers=_HEADERS, timeout=20)
                    self._last_request = __import__("time").monotonic()

                    if resp.status_code != 200:
                        break

                    page_jobs = _parse_serp_html(resp.text, company_id, seen_urls)
                    if not page_jobs:
                        break
                    all_jobs.extend(page_jobs)

                    # Short pause between pages
                    if page < _MAX_PAGES - 1:
                        await asyncio.sleep(3)

        except Exception:
            return []

        return all_jobs


def _parse_serp_html(html: str, company_id: int, seen_urls: set) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    # Google Search result containers: div with data-hveid or class="g"
    result_blocks = soup.find_all("div", class_=re.compile(r"^(g|tF2Cxc|MjjYud)$"))
    if not result_blocks:
        # Fallback: any <a> with an href that looks like a job URL
        result_blocks = soup.find_all("div", attrs={"data-hveid": True})

    for block in result_blocks:
        a_tag = block.find("a", href=True)
        if not a_tag:
            continue

        raw_url = a_tag["href"]
        # Google wraps URLs in /url?q=... — unwrap
        if raw_url.startswith("/url?"):
            qs = parse_qs(urlparse(raw_url).query)
            raw_url = qs.get("q", [raw_url])[0]

        # Skip non-http, tracking, and cached links
        if not raw_url.startswith("http") or "google.com" in raw_url:
            continue
        if raw_url in seen_urls:
            continue
        seen_urls.add(raw_url)

        # Title: h3 inside the block
        title_el = block.find("h3")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            title = a_tag.get_text(strip=True)[:100]

        # Snippet: the descriptive paragraph under the title
        snippet = ""
        for span in block.find_all(["span", "div"]):
            text = span.get_text(strip=True)
            if len(text) > 60 and text != title:
                snippet = text[:500]
                break

        # Derive a stable external_id from the URL path
        path = urlparse(raw_url).path
        external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", path.strip("/"))[:80]
        if not external_id:
            external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_url)[:80]

        # Skip obviously non-job pages
        lower_title = title.lower()
        if any(skip in lower_title for skip in ["careers at", "jobs at", "work at", "life at", "about us"]):
            continue

        jobs.append({
            "external_id": external_id,
            "company_id":  company_id,
            "title":       title,
            "description": snippet,
            "location":    "",
            "remote":      0,
            "url":         raw_url,
            "posted_date": None,
            "posted_at":   None,
            "ats_type":    "serp",
        })

    return jobs
