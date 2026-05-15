from __future__ import annotations

import asyncio
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

_SEARCH_URL = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "?q=software+engineer&employment_type=FULL_TIME&location=United+States&page={page}"
)
_JOB_URL_BASE = "https://www.google.com/about/careers/applications/jobs/results/{job_id}"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_MAX_PAGES = 5  # 20 jobs/page × 5 pages = 100 max


class GoogleScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.25)
        self._pw_ctx = None
        self._pw = None
        self._browser = None

    async def __aenter__(self) -> "GoogleScraper":
        await super().__aenter__()
        try:
            from playwright.async_api import async_playwright
            self._pw_ctx = async_playwright()
            self._pw = await self._pw_ctx.__aenter__()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
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
        if not self._browser:
            return []

        all_jobs: list[dict] = []
        seen_ids: set[str] = set()

        ctx = await self._browser.new_context(
            user_agent=_UA,
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()

        try:
            for page_num in range(1, _MAX_PAGES + 1):
                url = _SEARCH_URL.format(page=page_num)
                try:
                    await page.goto(url, wait_until="networkidle", timeout=35_000)
                    await asyncio.sleep(1)
                except Exception:
                    break

                html = await page.content()
                jobs = _parse_dom_jobs(html, company_id, seen_ids)
                if not jobs:
                    break
                all_jobs.extend(jobs)
        finally:
            await page.close()
            await ctx.close()

        return all_jobs


def _parse_dom_jobs(html: str, company_id: int, seen_ids: set[str]) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    ul = soup.find("ul", class_="spHGqe")
    if not ul:
        return []

    jobs: list[dict] = []
    for li in ul.find_all("li", class_="lLd3Je"):
        jsdata_el = li.find(attrs={"jsdata": True})
        if not jsdata_el:
            continue
        parts = jsdata_el.get("jsdata", "").split(";")
        if len(parts) < 2:
            continue
        job_id = parts[1].strip()
        if not job_id or job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        title_el = li.find("h3", class_="QJPWVe")
        title = title_el.get_text(strip=True) if title_el else ""

        loc_el = li.find("span", class_="r0wTof")
        location = loc_el.get_text(strip=True) if loc_el else ""

        remote = 1 if "remote" in location.lower() else 0
        external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", job_id)[:80]

        jobs.append({
            "external_id": external_id,
            "company_id":  company_id,
            "title":       title,
            "description": "",
            "location":    location,
            "remote":      remote,
            "url":         _JOB_URL_BASE.format(job_id=job_id),
            "posted_date": None,
            "posted_at":   None,
            "ats_type":    "google",
        })
    return jobs
