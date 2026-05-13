from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_API = (
    "https://careers.google.com/api/v3/search/"
    "?q=software+engineer&page_size=20&location.region=2840&page={page}"
)
_JOB_URL_BASE = "https://careers.google.com/jobs/results/{job_id}"


class GoogleScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.5)  # 1 req per 2 seconds

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        all_jobs: list[dict] = []
        page = 1

        while page <= 10:  # max 200 results
            try:
                resp = await self._get(_API.format(page=page))
            except ScraperError:
                break

            try:
                data = resp.json()
            except Exception:
                break

            jobs_raw = data.get("jobs", [])
            if not jobs_raw:
                break

            for j in jobs_raw:
                job_id = j.get("job_id", "")
                if not job_id:
                    continue

                title = j.get("title", "")

                # Location: prefer US locations
                locations = j.get("locations", []) or []
                location = ", ".join(
                    loc.get("display", "") for loc in locations if loc.get("display")
                ) or ""

                # Description: strip HTML
                desc_html = j.get("description", "") or ""
                description = BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True) if desc_html else ""

                # Published date
                published = j.get("published", "") or ""
                posted_date, posted_at = _parse_google_date(published)

                remote = 1 if "remote" in location.lower() else 0

                # External ID: use numeric part of job_id
                external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", job_id)[:80]
                apply_url = j.get("apply_url", "") or _JOB_URL_BASE.format(job_id=job_id)

                all_jobs.append({
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
                })

            if not data.get("nextPageToken"):
                break
            page += 1

        return all_jobs


def _parse_google_date(dt_str: str) -> tuple[str | None, str | None]:
    if not dt_str:
        return None, None
    # ISO 8601: "2026-05-01T00:00:00Z" or "2026-05-01"
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
