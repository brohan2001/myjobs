from __future__ import annotations

import asyncio
import re
from datetime import datetime

import httpx
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


async def fetch_google_description(url: str) -> str:
    """Fetch job description from a Google Careers job detail page."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "User-Agent": _UA,
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(resp.text, "lxml")

    # Try known Google Careers description container classes
    desc_div = (
        soup.find("div", class_="aG5W3")
        or soup.find("div", class_="KwJkGe")
        or soup.find("div", class_="gc-formatted-body")
        or soup.find(attrs={"data-module-name": "jobDetails"})
    )
    if desc_div:
        return desc_div.get_text(separator=" ", strip=True)

    # Fallback: look for sections with qualification/description headings
    text_parts: list[str] = []
    for heading in soup.find_all(re.compile(r"^h[1-4]$")):
        heading_text = heading.get_text(strip=True).lower()
        if any(kw in heading_text for kw in ("qualif", "responsib", "about the job", "preferred")):
            sibling = heading.find_next_sibling()
            while sibling and sibling.name not in ("h1", "h2", "h3", "h4"):
                text_parts.append(sibling.get_text(separator=" ", strip=True))
                sibling = sibling.find_next_sibling()

    if text_parts:
        return " ".join(text_parts)

    # Last resort: largest <div> block in the main content area
    main = soup.find("main") or soup.find("article") or soup.body
    if main:
        divs = main.find_all("div", recursive=True)
        if divs:
            biggest = max(divs, key=lambda d: len(d.get_text()))
            text = biggest.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    return ""
