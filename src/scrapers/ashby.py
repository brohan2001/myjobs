from __future__ import annotations

import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

from src.scrapers.base import BaseScraper, ScraperError

_API = "https://jobs.ashbyhq.com/api/non-user-graphql"

_QUERY = """
query ApiJobBoard($slug: String!) {
  jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $slug) {
    jobPostings {
      id
      title
      teamName
      locationName
      isRemote
      employmentType
      descriptionHtml
      publishedAt
      applicationLink
    }
  }
}
"""


class AshbyScraper(BaseScraper):
    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        slug = company.get("ashby_slug") or company["slug"]
        try:
            resp = await self._post(
                _API,
                json={"operationName": "ApiJobBoard", "variables": {"slug": slug}, "query": _QUERY},
                headers={"Content-Type": "application/json"},
            )
        except ScraperError:
            raise

        try:
            data = resp.json()
        except Exception:
            return []

        board = (data.get("data") or {}).get("jobBoard") or {}
        postings = board.get("jobPostings") or []

        jobs = []
        for p in postings:
            job_id = p.get("id", "")
            if not job_id:
                continue

            title = p.get("title", "")
            location = p.get("locationName") or ""
            is_remote = p.get("isRemote", False)
            remote = 1 if is_remote or "remote" in location.lower() else 0

            desc_html = p.get("descriptionHtml") or ""
            description = BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True) if desc_html else ""

            published = p.get("publishedAt") or ""
            posted_date, posted_at = _parse_ashby_date(published)

            url = p.get("applicationLink") or f"https://jobs.ashbyhq.com/{slug}/{job_id}"

            jobs.append({
                "external_id":  job_id,
                "company_id":   company_id,
                "title":        title,
                "description":  description,
                "location":     location,
                "remote":       remote,
                "url":          url,
                "posted_date":  posted_date,
                "posted_at":    posted_at,
                "ats_type":     "ashby",
            })

        return jobs


def _parse_ashby_date(dt_str: str) -> tuple[str | None, str | None]:
    if not dt_str:
        return None, None
    try:
        dt = datetime.fromisoformat(dt_str.rstrip("Z").replace("Z", "+00:00"))
        iso = dt.date().isoformat()
        return iso, dt.isoformat()
    except ValueError:
        pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", dt_str)
    if m:
        return m.group(1), m.group(1)
    return None, None
