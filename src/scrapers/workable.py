from __future__ import annotations

import re
from datetime import datetime, timezone

from src.scrapers.base import BaseScraper, ScraperError

_API_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
_MAX_JOBS = 500
_BASE_BODY: dict = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}


class WorkableScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.5)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        slug = company.get("workable_slug") or company["slug"]
        url = _API_URL.format(slug=slug)
        all_raw: list[dict] = []
        body: dict = dict(_BASE_BODY)

        while len(all_raw) < _MAX_JOBS:
            try:
                resp = await self._post(url, json=body)
            except ScraperError:
                break

            data = resp.json()
            results = data.get("results") or []
            all_raw.extend(results)

            next_cursor = (data.get("paging") or {}).get("next")
            if not next_cursor or not results:
                break
            body = {**_BASE_BODY, "token": next_cursor}

        jobs = []
        for item in all_raw[:_MAX_JOBS]:
            raw_id = item.get("id") or item.get("shortcode") or ""
            external_id = re.sub(r"[^A-Za-z0-9_\-]", "_", str(raw_id))

            city = item.get("city") or ""
            state = item.get("state") or ""
            country = item.get("country") or ""
            if city and state:
                location = f"{city}, {state}"
            elif country:
                location = country
            else:
                location = ""

            remote = 1 if item.get("remote") else 0

            shortcode = item.get("shortcode") or ""
            job_url = item.get("url") or (
                f"https://apply.workable.com/{slug}/j/{shortcode}" if shortcode else ""
            )

            created_at = item.get("created_at") or ""
            posted_date = None
            posted_at = None
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.rstrip("Z")).replace(tzinfo=timezone.utc)
                    posted_date = dt.date().isoformat()
                    posted_at = dt.isoformat()
                except ValueError:
                    pass

            jobs.append({
                "external_id": external_id,
                "company_id":  company_id,
                "title":       item.get("title") or "",
                "description": "",
                "location":    location,
                "remote":      remote,
                "url":         job_url,
                "posted_date": posted_date,
                "posted_at":   posted_at,
                "ats_type":    "workable",
            })

        return jobs
