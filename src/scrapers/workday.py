from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError


class WorkdayScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=1 / 3)  # 1 req per 3 seconds

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        host = company.get("workday_host", "")
        slug = company.get("workday_slug", "")
        board = company.get("workday_board", "External")

        if not host or not slug:
            return []

        listings_url = f"https://{host}/wday/cxs/{slug}/{board}/jobs"
        all_postings = []
        offset = 0
        limit = 20

        while True:
            try:
                resp = await self._post(
                    listings_url,
                    json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                    headers={"Content-Type": "application/json"},
                )
            except ScraperError:
                break

            try:
                data = resp.json()
            except Exception:
                break

            postings = data.get("jobPostings", [])
            total = data.get("total", 0)
            all_postings.extend(postings)
            offset += len(postings)

            if not postings or offset >= total or offset >= 300:
                break

        jobs = []
        for posting in all_postings:
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
    """Fetch a single Workday job description page. Uses its own client — called from pipeline."""
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
