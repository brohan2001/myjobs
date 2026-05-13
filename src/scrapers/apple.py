from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlencode

from src.scrapers.base import BaseScraper, ScraperError

_API_BASE = "https://jobs.apple.com/api/role/search"
_JOB_URL = "https://jobs.apple.com/en-us/details/{position_id}"


class AppleScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.5)  # 1 req per 2 seconds

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        all_jobs: list[dict] = []
        page = 1

        while page <= 10:  # max ~200 results
            filters = json.dumps({"teams": [{"key": "SFTWR"}]})
            params = urlencode({
                "filters": filters,
                "page": page,
                "locale": "en-us",
                "sort": "newest",
            })
            url = f"{_API_BASE}?{params}"

            try:
                resp = await self._get(url, headers={"Accept": "application/json"})
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
                position_id = r.get("positionId", "")
                if not position_id:
                    continue

                title = r.get("postingTitle", "") or r.get("title", "")
                description = r.get("jobSummary", "") or ""

                # Location
                loc = r.get("location", {}) or {}
                location = loc.get("name", "") if isinstance(loc, dict) else str(loc)

                posted_raw = r.get("postingDate", "") or r.get("postedDate", "") or ""
                posted_date, posted_at = _parse_apple_date(posted_raw)
                remote = 1 if "remote" in location.lower() else 0

                external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", position_id)[:80]
                job_url = _JOB_URL.format(position_id=position_id)

                all_jobs.append({
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
                })

            total = data.get("totalRecords", 0)
            if len(all_jobs) >= total or len(all_jobs) >= 200:
                break
            page += 1

        return all_jobs


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
    # "May 1, 2026"
    try:
        dt = datetime.strptime(dt_str.strip(), "%B %d, %Y")
        iso = dt.date().isoformat()
        return iso, iso
    except ValueError:
        pass
    return None, None
