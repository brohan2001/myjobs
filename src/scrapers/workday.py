from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_PAGE_LIMIT = 20
_MAX_JOBS = 300
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CFFI_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": _UA,
}


class WorkdayScraper(BaseScraper):
    """Scrape Workday job boards via TLS-spoofed Chrome requests.

    Strategy (fastest-first):
    1. curl_cffi with impersonate="chrome" — spoofs Chrome TLS fingerprint,
       bypasses Cloudflare Bot Management that blocks plain httpx (422/403).
    2. Playwright fallback — runs the fetch inside the browser JS context.
       Used only if curl_cffi also fails.
    """

    def __init__(self):
        super().__init__(rate_limit_rps=1 / 5)
        self._pw_ctx = None
        self._pw = None
        self._browser = None

    async def __aenter__(self) -> "WorkdayScraper":
        await super().__aenter__()
        try:
            from playwright.async_api import async_playwright
            self._pw_ctx = async_playwright()
            self._pw = await self._pw_ctx.__aenter__()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-position=0,0",
                    "--ignore-certifcate-errors",
                    "--ignore-certifcate-errors-spki-list",
                ],
            )
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
        host = company.get("workday_host", "")
        board = company.get("workday_board", "External")

        if not host:
            return []

        tenant = host.split(".")[0]
        api_url = f"https://{host}/wday/cxs/{tenant}/{board}/jobs"
        board_url = f"https://{host}/en-US/{board}"

        # Primary: curl_cffi with Chrome TLS fingerprint
        raw = await self._fetch_cffi(api_url)
        if raw is not None:
            return self._parse_postings(raw, host, board, company_id)

        # Fallback: Playwright (runs fetch inside browser JS context)
        if self._browser:
            try:
                raw = await self._fetch_via_playwright(board_url, api_url)
                if raw is not None:
                    return self._parse_postings(raw, host, board, company_id)
            except Exception:
                pass

        return []

    # ── private helpers ───────────────────────────────────────────────────────

    async def _fetch_cffi(self, api_url: str) -> list[dict] | None:
        """POST to Workday with Chrome TLS fingerprint via curl_cffi."""
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            return None

        all_postings: list[dict] = []
        offset = 0

        # Rate-limit: honour the same interval as the base scraper
        elapsed = __import__("time").monotonic() - self._last_request
        wait = self._min_interval - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            async with AsyncSession(impersonate="chrome") as session:
                while True:
                    payload = {
                        "appliedFacets": {},
                        "limit": _PAGE_LIMIT,
                        "offset": offset,
                        "searchText": "",
                    }
                    resp = await session.post(
                        api_url,
                        json=payload,
                        headers=_CFFI_HEADERS,
                        timeout=20,
                    )
                    self._last_request = __import__("time").monotonic()

                    if resp.status_code in (403, 422, 429, 503):
                        return None
                    if resp.status_code != 200:
                        return None

                    try:
                        data = resp.json()
                    except Exception:
                        break

                    if data.get("errorCode") == "HTTP_422":
                        return None

                    postings = data.get("jobPostings", [])
                    total = data.get("total", 0)
                    all_postings.extend(postings)
                    offset += len(postings)

                    if not postings or offset >= _MAX_JOBS:
                        break
                    if total > 0 and offset >= total:
                        break

        except Exception:
            return None

        return all_postings if all_postings else None

    # JS to override automation-detection signals before page load
    _STEALTH_JS = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = {runtime: {}};
        const origQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (params) =>
            params.name === 'notifications'
                ? Promise.resolve({state: Notification.permission})
                : origQuery(params);
    """

    async def _fetch_via_playwright(self, board_url: str, api_url: str) -> list[dict] | None:
        """Navigate the Workday board with Playwright and call the API via
        page.evaluate() so the request runs inside the browser JS context."""
        context = await self._browser.new_context(
            user_agent=_UA,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        await context.add_init_script(self._STEALTH_JS)
        page = await context.new_page()
        all_postings: list[dict] = []

        try:
            await page.goto(board_url, wait_until="networkidle", timeout=60_000)
            await asyncio.sleep(5)

            title = await page.title()
            if "unavailable" in title.lower() or "error" in title.lower():
                alt_url = board_url.replace("/en-US/", "/")
                await page.goto(alt_url, wait_until="networkidle", timeout=45_000)
                await asyncio.sleep(3)

            offset = 0
            while offset < _MAX_JOBS:
                body = {"appliedFacets": {}, "limit": _PAGE_LIMIT, "offset": offset, "searchText": ""}
                result = await page.evaluate(
                    """
                    async ([url, body]) => {
                        try {
                            const r = await fetch(url, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json',
                                    'Accept-Language': 'en-US,en;q=0.9'
                                },
                                body: JSON.stringify(body)
                            });
                            if (!r.ok) return null;
                            return await r.json();
                        } catch(e) { return null; }
                    }
                    """,
                    [api_url, body],
                )

                if not result or result.get("errorCode"):
                    break

                postings = result.get("jobPostings", [])
                total = result.get("total", 0)
                all_postings.extend(postings)
                offset += len(postings)

                if not postings:
                    break
                if total > 0 and offset >= total:
                    break

        finally:
            await page.close()
            await context.close()

        return all_postings if all_postings else None

    def _parse_postings(self, postings: list[dict], host: str, board: str, company_id: int) -> list[dict]:
        jobs = []
        for posting in postings:
            title = posting.get("title", "")
            external_path = posting.get("externalPath", "") or ""
            location = posting.get("locationsText", "") or ""
            posted_on = posting.get("postedOn", "") or ""

            job_url = f"https://{host}/en-US/{board}{external_path}"
            external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", external_path)[:80]
            if not external_id:
                continue

            posted_date, posted_at = _parse_workday_date(posted_on)
            remote = 1 if "remote" in location.lower() else 0

            jobs.append({
                "external_id": external_id,
                "company_id":  company_id,
                "title":       title,
                "description": "",
                "location":    location,
                "remote":      remote,
                "url":         job_url,
                "posted_date": posted_date,
                "posted_at":   posted_at,
                "ats_type":    "workday",
            })
        return jobs


async def fetch_workday_description(url: str) -> str:
    """Fetch a single Workday job description page."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "User-Agent": _UA,
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
    except Exception:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    desc_div = (
        soup.find(attrs={"data-automation-id": "jobPostingDescription"})
        or soup.find("div", class_=re.compile(r"job.*description", re.IGNORECASE))
        or soup.find("section", attrs={"data-automation-id": re.compile(r"description", re.IGNORECASE)})
    )
    return desc_div.get_text(separator=" ", strip=True) if desc_div else ""


def _parse_workday_date(posted_on: str) -> tuple[str | None, str | None]:
    if not posted_on:
        return None, None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", posted_on)
    if m:
        mo, d, y = m.groups()
        iso = f"{y}-{int(mo):02d}-{int(d):02d}"
        return iso, iso
    m2 = re.search(r"(\d{4}-\d{2}-\d{2})", posted_on)
    if m2:
        iso = m2.group(1)
        return iso, iso
    return None, None
