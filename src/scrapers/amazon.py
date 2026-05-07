from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_SEARCH_URL = (
    "https://www.amazon.jobs/en/search.json"
    "?base_query=software+engineer&category_id=software-development"
    "&job_count=10&offset={offset}&result_limit=10"
    "&country=&city=&zip=&location=&latitude=&longitude="
)
_JOB_BASE = "https://www.amazon.jobs"


class AmazonScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.5)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        all_hits: list[dict] = []
        offset = 0

        while offset < 100:
            try:
                resp = await self._get(_SEARCH_URL.format(offset=offset))
            except ScraperError:
                break

            try:
                data = resp.json()
            except Exception:
                break

            hits = data.get("hits", [])
            if not hits:
                break
            all_hits.extend(hits)
            offset += len(hits)
            if offset >= data.get("totalHits", 0):
                break

        jobs = []
        for hit in all_hits:
            job_path = hit.get("job_path", "")
            if not job_path:
                continue

            # Extract numeric ID from path for deduplication
            id_match = re.search(r"/jobs/(\d+)", job_path)
            external_id = id_match.group(1) if id_match else re.sub(r"[^a-z0-9]", "_", job_path)[-60:]

            location_parts = []
            if hit.get("city"):
                location_parts.append(hit["city"])
            if hit.get("state_province"):
                location_parts.append(hit["state_province"])
            if hit.get("country_code"):
                location_parts.append(hit["country_code"])
            location = ", ".join(location_parts) or hit.get("location", "")

            remote = 1 if "remote" in location.lower() else 0

            posted_date, posted_at = _parse_amazon_date(hit.get("posted_date", ""))

            description = hit.get("description_short", "") or ""

            jobs.append({
                "external_id": external_id,
                "company_id":  company_id,
                "title":       hit.get("title", ""),
                "description": description,
                "location":    location,
                "remote":      remote,
                "url":         _JOB_BASE + job_path,
                "posted_date": posted_date,
                "posted_at":   posted_at,
                "ats_type":    "amazon",
            })

        return jobs


def _parse_amazon_date(date_str: str) -> tuple[str | None, str | None]:
    """Parse Amazon's date formats: 'January 15, 2026' or 'January 2026'."""
    if not date_str:
        return None, None
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        iso = dt.date().isoformat()
        return iso, iso
    except ValueError:
        pass
    try:
        dt = datetime.strptime(date_str.strip(), "%B %Y")
        iso = dt.date().isoformat()
        return iso, iso
    except ValueError:
        pass
    return None, None
