from __future__ import annotations

import re
from datetime import datetime, timezone

from src.scrapers.base import BaseScraper, ScraperError

_SEARCH_URL = (
    "https://apply.careers.microsoft.com/api/pcsx/search"
    "?domain=microsoft.com&query=software+engineer&location=&start={start}&"
)
_JOB_URL = "https://jobs.careers.microsoft.com/global/en/job/{job_id}"
_PAGE_SIZE = 10
_MAX_RESULTS = 100

_MS_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://jobs.careers.microsoft.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class MicrosoftScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.5)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        all_jobs: list[dict] = []
        seen_ids: set[str] = set()
        start = 0

        while start < _MAX_RESULTS:
            url = _SEARCH_URL.format(start=start)
            try:
                resp = await self._get(url, headers=_MS_HEADERS)
            except ScraperError:
                break

            try:
                data = resp.json()
            except Exception:
                break

            positions = (data.get("data") or {}).get("positions") or []
            if not positions:
                break

            for p in positions:
                job = _parse_position(p, company_id, seen_ids)
                if job:
                    all_jobs.append(job)

            start += len(positions)
            if len(positions) < _PAGE_SIZE:
                break

        return all_jobs


def _parse_position(p: dict, company_id: int, seen_ids: set) -> dict | None:
    job_id = str(p.get("id", "") or p.get("atsJobId", "") or "")
    if not job_id or job_id in seen_ids:
        return None
    seen_ids.add(job_id)

    title = p.get("name", "")

    locs = p.get("standardizedLocations") or p.get("locations") or []
    location = locs[0] if locs else ""

    work_opt = p.get("workLocationOption", "") or ""
    remote = 1 if work_opt == "remote" or "remote" in location.lower() else 0

    posted_ts = p.get("postedTs")
    posted_date, posted_at = _parse_ms_ts(posted_ts)

    position_url = p.get("positionUrl", "")
    ats_job_id = p.get("atsJobId", "") or job_id
    url = (
        f"https://jobs.careers.microsoft.com{position_url}"
        if position_url
        else _JOB_URL.format(job_id=ats_job_id)
    )

    external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(job_id))[:80]

    return {
        "external_id": external_id,
        "company_id":  company_id,
        "title":       title,
        "description": "",
        "location":    location,
        "remote":      remote,
        "url":         url,
        "posted_date": posted_date,
        "posted_at":   posted_at,
        "ats_type":    "microsoft",
    }


def _parse_ms_ts(ts) -> tuple[str | None, str | None]:
    if not ts:
        return None, None
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        iso = dt.date().isoformat()
        return iso, dt.isoformat()
    except Exception:
        pass
    return None, None
