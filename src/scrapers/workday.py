from __future__ import annotations

import re

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
            # Stable external_id derived from the path (unique per company+board)
            external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", external_path)[:80]
            if not external_id:
                continue

            posted_date, posted_at = _parse_workday_date(posted_on)
            remote = 1 if "remote" in location.lower() else 0

            jobs.append({
                "external_id": external_id,
                "company_id":  company_id,
                "title":       title,
                "description": "",  # Workday requires a second request per job
                "location":    location,
                "remote":      remote,
                "url":         job_url,
                "posted_date": posted_date,
                "posted_at":   posted_at,
                "ats_type":    "workday",
            })

        return jobs


def _parse_workday_date(posted_on: str) -> tuple[str | None, str | None]:
    if not posted_on:
        return None, None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", posted_on)
    if m:
        mo, d, y = m.groups()
        iso = f"{y}-{int(mo):02d}-{int(d):02d}"
        return iso, iso
    # Try ISO format in case Workday changes
    m2 = re.search(r"(\d{4}-\d{2}-\d{2})", posted_on)
    if m2:
        iso = m2.group(1)
        return iso, iso
    return None, None
