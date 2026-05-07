from __future__ import annotations

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_API = "https://boards.greenhouse.io/v1/boards/{slug}/jobs?content=true"


class GreenhouseScraper(BaseScraper):
    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        slug = company["slug"]
        url = _API.format(slug=slug)
        try:
            resp = await self._get(url)
        except ScraperError:
            raise

        data = resp.json()
        raw_jobs = data.get("jobs", [])
        jobs = []
        for j in raw_jobs:
            description = _strip_html(j.get("content", ""))
            location = (j.get("location") or {}).get("name", "")
            remote = 1 if "remote" in location.lower() else 0
            raw_ts = j.get("updated_at") or ""
            posted_date = raw_ts[:10] or None
            posted_at = raw_ts or None  # full ISO datetime, e.g. "2026-05-06T14:23:00.000Z"

            jobs.append({
                "external_id": str(j["id"]),
                "company_id":  company_id,
                "title":       j.get("title", ""),
                "description": description,
                "location":    location,
                "remote":      remote,
                "url":         j.get("absolute_url", ""),
                "posted_date": posted_date,
                "posted_at":   posted_at,
                "ats_type":    "greenhouse",
            })
        return jobs


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)
