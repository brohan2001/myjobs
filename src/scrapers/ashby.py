from __future__ import annotations

import re
from bs4 import BeautifulSoup
from datetime import datetime

from src.scrapers.base import BaseScraper, ScraperError

_API = "https://jobs.ashbyhq.com/api/non-user-graphql"

# Updated query — Ashby removed several fields from JobPostingBriefsWithIdsAndTeamId;
# we fetch the list first, then optionally enrich with a per-job detail call.
_LIST_QUERY = """
query ApiJobBoard($slug: String!) {
  jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $slug) {
    jobPostings {
      id
      title
      locationName
      locationId
      teamId
      employmentType
    }
  }
}
"""

# Per-job detail query to get description and publishedDate
_DETAIL_QUERY = """
query JobPosting($slug: String!, $jobPostingId: String!) {
  jobPosting(organizationHostedJobsPageName: $slug, jobPostingId: $jobPostingId) {
    id
    title
    locationName
    descriptionHtml
    publishedDate
  }
}
"""

_MAX_DETAIL_FETCHES = 5  # cap per-job detail requests per company


class AshbyScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=2.0)  # 0.5s between requests

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        slug = company.get("ashby_slug") or company["slug"]

        # 1. Fetch the full job list (id, title, locationName only)
        try:
            resp = await self._post(
                _API,
                json={"operationName": "ApiJobBoard", "variables": {"slug": slug}, "query": _LIST_QUERY},
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

        if not postings:
            return []

        jobs = []
        for p in postings:
            job_id = p.get("id", "")
            if not job_id:
                continue

            title = p.get("title", "")
            location = p.get("locationName") or ""
            remote = 1 if "remote" in location.lower() else 0
            url = f"https://jobs.ashbyhq.com/{slug}/{job_id}"

            jobs.append({
                "external_id":  job_id,
                "company_id":   company_id,
                "title":        title,
                "description":  "",
                "location":     location,
                "remote":       remote,
                "url":          url,
                "posted_date":  None,
                "posted_at":    None,
                "ats_type":     "ashby",
                "_slug":        slug,   # temp field for enrichment
            })

        # 2. Enrich the first N jobs with description + date via detail query
        enriched = 0
        for job in jobs:
            if enriched >= _MAX_DETAIL_FETCHES:
                break
            detail = await self._fetch_detail(slug, job["external_id"])
            if detail:
                job["description"] = detail.get("description", "")
                job["posted_date"] = detail.get("posted_date")
                job["posted_at"] = detail.get("posted_at")
            enriched += 1

        # Strip temp field before returning
        for job in jobs:
            job.pop("_slug", None)

        return jobs

    async def _fetch_detail(self, slug: str, job_id: str) -> dict | None:
        try:
            resp = await self._post(
                _API,
                json={
                    "variables": {"slug": slug, "jobPostingId": job_id},
                    "query": _DETAIL_QUERY,
                },
                headers={"Content-Type": "application/json"},
            )
        except ScraperError:
            return None

        try:
            data = resp.json()
        except Exception:
            return None

        jp = (data.get("data") or {}).get("jobPosting") or {}
        if not jp:
            return None

        desc_html = jp.get("descriptionHtml") or ""
        description = BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True) if desc_html else ""

        published = jp.get("publishedDate") or ""
        posted_date, posted_at = _parse_ashby_date(published)

        return {"description": description, "posted_date": posted_date, "posted_at": posted_at}


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
