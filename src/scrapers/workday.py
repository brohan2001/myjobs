from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_PAGE_LIMIT = 20
_MAX_JOBS = 300


class WorkdayScraper(BaseScraper):
    """Scrape Workday job boards.

    Direct POST to /wday/cxs/.../jobs now returns 422 due to Cloudflare bot
    protection. We navigate the page with Playwright so the JS challenge is
    solved, then call the same endpoint via page.evaluate() (fetch inside the
    browser's own JS context), which inherits the valid session cookies.
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
        host = company.get("workday_host", "")
        slug = company.get("workday_slug", "")
        board = company.get("workday_board", "External")

        if not host or not slug:
            return []

        api_url = f"https://{host}/wday/cxs/{slug}/{board}/jobs"
        board_url = f"https://{host}/en-US/{board}"

        # Try direct httpx first (fast path — works when Workday isn't blocking)
        try:
            raw = await self._fetch_direct(api_url)
            if raw is not None:
                return self._parse_postings(raw, host, board, company_id)
        except Exception:
            pass

        # Playwright fallback — runs the fetch inside the browser's JS context
        if self._browser:
            try:
                raw = await self._fetch_via_playwright(board_url, api_url)
                if raw is not None:
                    return self._parse_postings(raw, host, board, company_id)
            except Exception:
                pass

        return []

    # ── private helpers ───────────────────────────────────────────────────────

    async def _fetch_direct(self, api_url: str) -> list[dict] | None:
        """Try the Workday cxs API directly with httpx. Returns None on 422."""
        all_postings: list[dict] = []
        offset = 0

        while True:
            try:
                resp = await self._post(
                    api_url,
                    json={"appliedFacets": {}, "limit": _PAGE_LIMIT, "offset": offset, "searchText": ""},
                    headers={"Content-Type": "application/json"},
                )
            except ScraperError as e:
                if "422" in str(e):
                    return None  # signal: try Playwright
                break

            try:
                data = resp.json()
            except Exception:
                break

            # 422 can also arrive as a 200 with an errorCode field
            if data.get("errorCode") == "HTTP_422":
                return None

            postings = data.get("jobPostings", [])
            total = data.get("total", 0)
            all_postings.extend(postings)
            offset += len(postings)

            if not postings or offset >= total or offset >= _MAX_JOBS:
                break

        return all_postings if all_postings else None

    async def _fetch_via_playwright(self, board_url: str, api_url: str) -> list[dict] | None:
        """Navigate the Workday board with Playwright and call the API via
        page.evaluate() so the request runs inside the browser JS context."""
        page = await self._browser.new_page()
        all_postings: list[dict] = []

        try:
            # Navigate so Cloudflare/Workday sets valid session cookies
            await page.goto(board_url, wait_until="load", timeout=30_000)
            await asyncio.sleep(2)

            offset = 0
            while offset < _MAX_JOBS:
                body = {"appliedFacets": {}, "limit": _PAGE_LIMIT, "offset": offset, "searchText": ""}
                result = await page.evaluate(
                    """
                    async ([url, body]) => {
                        try {
                            const r = await fetch(url, {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
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

                if not postings or offset >= total:
                    break

        finally:
            await page.close()

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
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
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
