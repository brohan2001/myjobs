from __future__ import annotations

import asyncio
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

# Page URL — the v3 JSON API is gone; we scrape the rendered page with Playwright
_SEARCH_URL = (
    "https://careers.google.com/jobs/results/"
    "?q=software+engineer&employment_type=FULL_TIME"
    "&location=United+States&sort_by=date&page={page}"
)
_JOB_URL_BASE = "https://careers.google.com/jobs/results/{job_id}"


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
        if not self._browser:
            return []

        all_jobs: list[dict] = []

        for page_num in range(1, 6):  # up to 5 pages (~100 jobs)
            url = _SEARCH_URL.format(page=page_num)
            page_jobs = await self._scrape_page(url, company_id)
            if not page_jobs:
                break
            all_jobs.extend(page_jobs)
            if len(all_jobs) >= 100:
                break

        return all_jobs

    async def _scrape_page(self, url: str, company_id: int) -> list[dict]:
        page = await self._browser.new_page()
        captured_jobs: list[dict] = []

        # Intercept any JSON API responses
        api_data: list[dict] = []
        async def on_response(resp):
            ct = resp.headers.get("content-type", "")
            if "json" in ct and ("search" in resp.url or "career" in resp.url):
                try:
                    data = await resp.json()
                    if isinstance(data, dict) and data.get("jobs"):
                        api_data.extend(data["jobs"])
                except Exception:
                    pass
        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(2)
        except Exception:
            await page.close()
            return []

        if api_data:
            # Parse the intercepted JSON API response
            for j in api_data:
                job = _parse_api_job(j, company_id)
                if job:
                    captured_jobs.append(job)
        else:
            # DOM fallback: extract job cards from the rendered HTML
            html = await page.content()
            captured_jobs = _parse_dom_jobs(html, company_id)

        await page.close()
        return captured_jobs


def _parse_api_job(j: dict, company_id: int) -> dict | None:
    job_id = j.get("job_id", "")
    if not job_id:
        return None
    title = j.get("title", "")
    locations = j.get("locations", []) or []
    location = ", ".join(
        loc.get("display", "") for loc in locations if loc.get("display")
    )
    desc_html = j.get("description", "") or ""
    description = BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True) if desc_html else ""
    published = j.get("published", "") or ""
    posted_date, posted_at = _parse_google_date(published)
    remote = 1 if "remote" in location.lower() else 0
    external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", job_id)[:80]
    apply_url = j.get("apply_url", "") or _JOB_URL_BASE.format(job_id=job_id)
    return {
        "external_id": external_id,
        "company_id":  company_id,
        "title":       title,
        "description": description,
        "location":    location,
        "remote":      remote,
        "url":         apply_url,
        "posted_date": posted_date,
        "posted_at":   posted_at,
        "ats_type":    "google",
    }


def _parse_dom_jobs(html: str, company_id: int) -> list[dict]:
    """Extract job listings from Google Careers rendered HTML."""
    soup = BeautifulSoup(html, "lxml")
    jobs: list[dict] = []

    # Google careers uses various class patterns; look for job result links
    # Links to individual job pages: /jobs/results/{id}
    seen_ids: set[str] = set()
    for a_tag in soup.find_all("a", href=re.compile(r"/jobs/results/\d+")):
        href = a_tag.get("href", "")
        m = re.search(r"/jobs/results/(\d+)", href)
        if not m:
            continue
        job_id = m.group(1)
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        # Title: find closest heading or strong text
        title = ""
        for tag in ["h3", "h2", "strong", "span"]:
            el = a_tag.find(tag)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = a_tag.get_text(strip=True)[:100]

        # Location: look for sibling/child elements after the title
        location = ""
        parent = a_tag.parent
        if parent:
            spans = parent.find_all("span")
            if len(spans) >= 2:
                location = spans[-1].get_text(strip=True)

        url = f"https://careers.google.com{href}" if href.startswith("/") else href
        external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", job_id)[:80]
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
            "ats_type":    "google",
        })

    return jobs


def _parse_google_date(dt_str: str) -> tuple[str | None, str | None]:
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
    return None, None
