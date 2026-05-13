from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_BASE_API = "https://api.lever.co/v0/postings/{slug}?mode=json&limit=50"
_MAX_JOBS = 500


class LeverScraper(BaseScraper):
    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        slug = company["slug"]
        base_url = _BASE_API.format(slug=slug)
        all_raw: list[dict] = []

        next_url: str | None = base_url
        while next_url and len(all_raw) < _MAX_JOBS:
            try:
                resp = await self._get(next_url)
            except ScraperError:
                break

            page = resp.json()
            if not isinstance(page, list) or not page:
                break

            all_raw.extend(page)
            if len(page) < 50:
                break
            last_id = page[-1].get("id", "")
            if not last_id:
                break
            next_url = f"{base_url}&offset={last_id}"

        jobs = []
        for j in all_raw:
            categories = j.get("categories") or {}
            location = categories.get("location", "")
            remote = 1 if "remote" in location.lower() else 0

            created_ms = j.get("createdAt", 0)
            posted_date = None
            posted_at = None
            if created_ms:
                try:
                    dt = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
                    posted_date = dt.date().isoformat()
                    posted_at = dt.isoformat()
                except (OSError, OverflowError):
                    pass

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
                "posted_at":   posted_at,
                "ats_type":    "lever",
            })
        return jobs


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)
