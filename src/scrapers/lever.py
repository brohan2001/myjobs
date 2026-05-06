from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_API = "https://api.lever.co/v0/postings/{slug}?mode=json&limit=50"


class LeverScraper(BaseScraper):
    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        slug = company["slug"]
        url = _API.format(slug=slug)
        try:
            resp = await self._get(url)
        except ScraperError:
            raise

        raw_jobs = resp.json()
        if not isinstance(raw_jobs, list):
            return []

        jobs = []
        for j in raw_jobs:
            categories = j.get("categories") or {}
            location = categories.get("location", "")
            remote = 1 if "remote" in location.lower() else 0

            created_ms = j.get("createdAt", 0)
            posted_date = None
            if created_ms:
                try:
                    posted_date = datetime.fromtimestamp(
                        created_ms / 1000, tz=timezone.utc
                    ).date().isoformat()
                except (OSError, OverflowError):
                    posted_date = None

            description = j.get("descriptionPlain", "") or _strip_html(
                j.get("description", "")
            )

            jobs.append({
                "external_id": str(j["id"]),
                "company_id":  company_id,
                "title":       j.get("text", ""),
                "description": description,
                "location":    location,
                "remote":      remote,
                "url":         j.get("hostedUrl", ""),
                "posted_date": posted_date,
                "ats_type":    "lever",
            })
        return jobs


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)
