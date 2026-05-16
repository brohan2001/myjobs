"""Oracle Recruiting Cloud (ORC) scraper.

Targets companies using Oracle's HCM recruitment module.
API endpoint: GET /hcmRestApi/resources/latest/recruitingCEJobRequisitions
"""
from __future__ import annotations

import urllib.parse

from src.scrapers.base import BaseScraper, ScraperError

_API_PATH = "/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
_FACETS = "LOCATIONS%3BWORK_LOCATIONS%3BWORKPLACE_TYPES%3BTITLES%3BCATEGORIES"
_PAGE_SIZE = 25
_MAX_JOBS = 300

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class OracleCloudScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.33)  # 1 req/3s

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        host = company["orc_host"]
        site = company["orc_site"]
        careers_url = company.get("orc_careers_url", f"https://{host}/hcmUI/CandidateExperience")
        base_url = f"https://{host}{_API_PATH}"

        jobs: list[dict] = []
        offset = 0

        while True:
            finder = (
                f"findReqs;siteNumber={site},"
                f"facetsList={_FACETS},"
                f"limit={_PAGE_SIZE},"
                f"offset={offset},"
                f"sortBy=POSTING_DATES_DESC"
            )
            params = {
                "onlyData": "true",
                "expand": "requisitionList.workLocation,requisitionList.otherWorkLocations",
                "finder": finder,
            }

            url = base_url + "?" + urllib.parse.urlencode(params)
            try:
                resp = await self._get(url, headers=_HEADERS)
            except ScraperError:
                raise

            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            bucket = items[0]
            total = int(bucket.get("TotalJobsCount", 0))
            page_jobs = bucket.get("requisitionList") or []

            for j in page_jobs:
                job_id = str(j.get("Id", ""))
                title = j.get("Title", "")
                location = j.get("PrimaryLocation", "")
                country = j.get("PrimaryLocationCountry", "")
                workplace = j.get("WorkplaceTypeCode", "")
                posted_raw = j.get("PostedDate", "") or ""
                posted_date = posted_raw[:10] or None
                remote = 1 if workplace in ("REMOTE",) or "remote" in location.lower() else 0
                job_url = f"{careers_url}/en/sites/{site}/job/{job_id}"

                jobs.append({
                    "external_id": job_id,
                    "company_id":  company_id,
                    "title":       title,
                    "description": "",
                    "location":    location,
                    "remote":      remote,
                    "url":         job_url,
                    "posted_date": posted_date,
                    "posted_at":   posted_raw or None,
                    "ats_type":    "oracle_cloud",
                })

            offset += len(page_jobs)
            if offset >= total or offset >= _MAX_JOBS or not page_jobs:
                break

        return jobs
