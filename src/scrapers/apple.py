from __future__ import annotations

import asyncio
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_API_URL = "https://jobs.apple.com/api/role/search"
_JOB_URL = "https://jobs.apple.com/en-us/details/{position_id}"
_PW_SEARCH_URL = "https://jobs.apple.com/en-us/search?sort=newest&page={page}"
_MAX_PAGES = 5


class AppleScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.5)
        self._pw_ctx = None
        self._pw = None
        self._browser = None

    async def __aenter__(self) -> "AppleScraper":
        await super().__aenter__()
        try:
            from playwright.async_api import async_playwright
            self._pw_ctx = async_playwright()
            self._pw = await self._pw_ctx.__aenter__()
            self._browser = await self._pw.chromium.launch(headless=True)
        except Exception:
            self._browser = None
        return self

    async def __aexit__(self, *args) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw_ctx:
            try:
                await self._pw_ctx.__aexit__(*args)
            except Exception:
                pass
        await super().__aexit__(*args)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        # Primary: direct POST API — no Playwright needed
        jobs = await self._fetch_direct(company_id)
        if jobs:
            return jobs

        # Playwright fallback
        if self._browser:
            try:
                return await self._fetch_via_playwright(company_id)
            except Exception:
                pass

        return []

    async def _fetch_direct(self, company_id: int) -> list[dict]:
        # Try curl_cffi with Chrome fingerprint first — Apple's API returns
        # 301→404 for plain httpx but responds to real Chrome TLS.
        jobs = await self._fetch_cffi(company_id)
        if jobs:
            return jobs

        # Fallback: plain httpx (works if Apple relaxes their bot check)
        all_jobs: list[dict] = []
        seen_ids: set[str] = set()

        for page_num in range(1, _MAX_PAGES + 1):
            try:
                resp = await self._post(
                    _API_URL,
                    json={"query": "", "filters": {}, "page": page_num, "sortOrder": "NEWEST"},
                    headers={
                        "Content-Type": "application/json",
                        "Referer": "https://jobs.apple.com/en-us/search",
                        "Origin": "https://jobs.apple.com",
                    },
                )
            except ScraperError:
                break

            try:
                data = resp.json()
            except Exception:
                break

            results = data.get("searchResults", [])
            if not results:
                break

            for r in results:
                job = _parse_api_job(r, company_id, seen_ids)
                if job:
                    all_jobs.append(job)

            if len(results) < 20:
                break

        return all_jobs

    async def _fetch_cffi(self, company_id: int) -> list[dict]:
        """POST to Apple Jobs API with Chrome TLS fingerprint."""
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            return []

        all_jobs: list[dict] = []
        seen_ids: set[str] = set()

        try:
            async with AsyncSession(impersonate="chrome") as session:
                for page_num in range(1, _MAX_PAGES + 1):
                    resp = await session.post(
                        _API_URL,
                        json={"query": "", "filters": {}, "page": page_num, "sortOrder": "NEWEST"},
                        headers={
                            "Content-Type": "application/json",
                            "Referer": "https://jobs.apple.com/en-us/search",
                            "Origin": "https://jobs.apple.com",
                            "User-Agent": (
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0.0.0 Safari/537.36"
                            ),
                        },
                        timeout=20,
                    )
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    results = data.get("searchResults", [])
                    if not results:
                        break
                    for r in results:
                        job = _parse_api_job(r, company_id, seen_ids)
                        if job:
                            all_jobs.append(job)
                    if len(results) < 20:
                        break
        except Exception:
            return []

        return all_jobs

    async def _fetch_via_playwright(self, company_id: int) -> list[dict]:
        all_jobs: list[dict] = []
        seen_ids: set[str] = set()

        for page_num in range(1, _MAX_PAGES + 1):
            url = _PW_SEARCH_URL.format(page=page_num)
            page_jobs = await self._scrape_page(url, company_id, seen_ids)
            if not page_jobs:
                break
            all_jobs.extend(page_jobs)
            if len(all_jobs) >= 100:
                break

        return all_jobs

    async def _scrape_page(self, url: str, company_id: int, seen_ids: set) -> list[dict]:
        page = await self._browser.new_page()
        api_data: list[dict] = []

        async def on_response(resp):
            ct = resp.headers.get("content-type", "")
            if "json" in ct and "jobs.apple.com" in resp.url:
                try:
                    data = await resp.json()
                    if isinstance(data, dict) and data.get("searchResults"):
                        api_data.extend(data["searchResults"])
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(2)
        except Exception:
            await page.close()
            return []

        captured: list[dict] = []
        if api_data:
            for r in api_data:
                job = _parse_api_job(r, company_id, seen_ids)
                if job:
                    captured.append(job)
        else:
            html = await page.content()
            captured = _parse_dom_jobs(html, company_id, seen_ids)

        await page.close()
        return captured


def _parse_api_job(r: dict, company_id: int, seen_ids: set) -> dict | None:
    position_id = r.get("positionId", "")
    if not position_id or position_id in seen_ids:
        return None
    seen_ids.add(position_id)

    title = r.get("postingTitle", "") or r.get("title", "")
    description = r.get("jobSummary", "") or ""

    loc = r.get("location", {}) or {}
    location = loc.get("name", "") if isinstance(loc, dict) else str(loc)

    is_remote = r.get("isRemote", False)
    remote = 1 if is_remote or "remote" in location.lower() else 0

    posted_raw = r.get("postingDate", "") or r.get("postedDate", "") or ""
    posted_date, posted_at = _parse_apple_date(posted_raw)

    external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", position_id)[:80]
    job_url = _JOB_URL.format(position_id=position_id)

    return {
        "external_id": external_id,
        "company_id":  company_id,
        "title":       title,
        "description": description,
        "location":    location,
        "remote":      remote,
        "url":         job_url,
        "posted_date": posted_date,
        "posted_at":   posted_at,
        "ats_type":    "apple",
    }


def _parse_dom_jobs(html: str, company_id: int, seen_ids: set) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[dict] = []

    for a_tag in soup.find_all("a", href=re.compile(r"/en-us/details/\d+")):
        href = a_tag.get("href", "")
        m = re.search(r"/en-us/details/(\d+)", href)
        if not m:
            continue
        position_id = m.group(1)
        if position_id in seen_ids:
            continue
        seen_ids.add(position_id)

        title = ""
        for tag in ["h2", "h3", "strong", "span"]:
            el = a_tag.find(tag)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = a_tag.get_text(strip=True)[:100]

        location = ""
        parent = a_tag.parent
        if parent:
            spans = parent.find_all("span")
            if len(spans) >= 2:
                location = spans[-1].get_text(strip=True)

        url = f"https://jobs.apple.com{href}" if href.startswith("/") else href
        external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", position_id)[:80]
        remote = 1 if "remote" in location.lower() else 0

        jobs.append({
            "external_id": external_id,
            "company_id":  company_id,
            "title":       title,
            "description": "",
            "location":    location,
            "remote":      remote,
            "url":         url,
            "posted_date": None,
            "posted_at":   None,
            "ats_type":    "apple",
        })

    return jobs


def _parse_apple_date(dt_str: str) -> tuple[str | None, str | None]:
    if not dt_str:
        return None, None
    try:
        dt = datetime.fromisoformat(dt_str.rstrip("Z"))
        iso = dt.date().isoformat()
        return iso, iso
    except ValueError:
        pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", dt_str)
    if m:
        return m.group(1), m.group(1)
    try:
        dt = datetime.strptime(dt_str.strip(), "%B %d, %Y")
        iso = dt.date().isoformat()
        return iso, iso
    except ValueError:
        pass
    return None, None
