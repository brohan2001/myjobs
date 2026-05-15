from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_LIST_URL = "https://api.smartrecruiters.com/v1/companies/{sr_id}/postings?limit=100&offset={offset}"
_DETAIL_URL = "https://api.smartrecruiters.com/v1/companies/{sr_id}/postings/{job_id}"
_PAGE_SIZE = 100
_MAX_JOBS = 500
_MAX_DESCRIPTION_FETCHES = 100


class SmartRecruitersScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=2.0)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        sr_id = company.get("sr_id") or company["slug"]
        all_raw: list[dict] = []
        offset = 0

        while len(all_raw) < _MAX_JOBS:
            url = _LIST_URL.format(sr_id=sr_id, offset=offset)
            try:
                resp = await self._get(url)
            except ScraperError:
                break

            data = resp.json()
            content = data.get("content", [])
            if not content:
                break
            all_raw.extend(content)
            if len(all_raw) >= data.get("totalFound", 0) or len(content) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE

        jobs = []
        for j in all_raw[:_MAX_JOBS]:
            location_obj = j.get("location") or {}
            location = location_obj.get("fullLocation", "")
            remote = 1 if location_obj.get("remote") else 0

            released = j.get("releasedDate", "")
            posted_date = None
            posted_at = None
            if released:
                try:
                    dt = datetime.fromisoformat(released.replace("Z", "+00:00"))
                    posted_date = dt.date().isoformat()
                    posted_at = dt.isoformat()
                except ValueError:
                    pass

            job_id = str(j["id"])
            posting_url = f"https://jobs.smartrecruiters.com/{sr_id}/{job_id}"

            jobs.append({
                "external_id": job_id,
                "company_id":  company_id,
                "title":       j.get("name", ""),
                "description": "",
                "location":    location,
                "remote":      remote,
                "url":         posting_url,
                "posted_date": posted_date,
                "posted_at":   posted_at,
                "ats_type":    "smartrecruiters",
                "_sr_id":      sr_id,
            })
        return jobs


async def fetch_smartrecruiters_description(sr_id: str, job_id: str) -> str:
    """Fetch full job description HTML from SmartRecruiters detail endpoint."""
    import httpx
    url = _DETAIL_URL.format(sr_id=sr_id, job_id=job_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                return ""
            data = resp.json()
            sections = data.get("jobAd", {}).get("sections", {})
            html = sections.get("jobDescription", {}).get("text", "")
            if not html:
                additional = sections.get("additionalInformation", {}).get("text", "")
                quals = sections.get("qualifications", {}).get("text", "")
                html = " ".join(filter(None, [html, quals, additional]))
            return _strip_html(html)
        except Exception:
            return ""


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
