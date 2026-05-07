from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_GUEST_API = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords=software+engineer+new+grad&company={company_id}"
    "&f_TPR=r604800&start={start}"  # last 7 days
)
_LI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.linkedin.com/jobs/search/",
}


class LinkedInScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.2)  # 1 req per 5 seconds

    async def __aenter__(self) -> "LinkedInScraper":
        import httpx
        self.client = httpx.AsyncClient(
            headers=_LI_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        return self

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        li_company_id = company.get("linkedin_company_id", "")
        if not li_company_id:
            return []

        jobs = []
        start = 0

        while start < 50:
            url = _GUEST_API.format(company_id=li_company_id, start=start)
            try:
                resp = await self._get(url)
            except ScraperError:
                break

            # Response is HTML — if empty or login redirect, stop
            text = resp.text
            if not text.strip() or "login" in resp.url.path.lower():
                break

            parsed = _parse_li_html(text, company_id)
            if not parsed:
                break

            jobs.extend(parsed)
            start += 10
            if len(parsed) < 10:
                break

        return jobs


def _parse_li_html(html: str, company_id: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_="base-card")
    jobs = []

    for card in cards:
        link_tag = card.find("a", class_="base-card__full-link")
        title_tag = card.find("h3", class_=re.compile("base-search-card__title"))
        location_tag = card.find("span", class_=re.compile("job-search-card__location"))
        time_tag = card.find("time")

        if not link_tag or not title_tag:
            continue

        url = link_tag.get("href", "").split("?")[0]  # strip tracking params
        # LinkedIn job URLs: .../jobs/view/1234567890/...
        id_match = re.search(r"/view/(\d+)", url)
        if not id_match:
            continue
        external_id = id_match.group(1)

        title = title_tag.get_text(strip=True)
        location = location_tag.get_text(strip=True) if location_tag else ""
        remote = 1 if "remote" in location.lower() else 0

        posted_date = None
        posted_at = None
        if time_tag:
            dt_attr = time_tag.get("datetime", "")
            if dt_attr:
                posted_date = dt_attr[:10]
                posted_at = dt_attr if "T" in dt_attr else dt_attr
            else:
                # Parse relative time text: "2 hours ago", "1 day ago", "3 weeks ago"
                rel = time_tag.get_text(strip=True).lower()
                posted_at_dt = _parse_relative_time(rel)
                if posted_at_dt:
                    posted_date = posted_at_dt[:10]
                    posted_at = posted_at_dt

        jobs.append({
            "external_id": external_id,
            "company_id":  company_id,
            "title":       title,
            "description": "",
            "location":    location,
            "remote":      remote,
            "url":         url,
            "posted_date": posted_date,
            "posted_at":   posted_at,
            "ats_type":    "linkedin",
        })

    return jobs


def _parse_relative_time(text: str) -> str | None:
    now = datetime.now(timezone.utc)
    m = re.search(r"(\d+)\s+(second|minute|hour|day|week|month)", text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta_map = {
        "second": timedelta(seconds=n),
        "minute": timedelta(minutes=n),
        "hour": timedelta(hours=n),
        "day": timedelta(days=n),
        "week": timedelta(weeks=n),
        "month": timedelta(days=n * 30),
    }
    dt = now - delta_map.get(unit, timedelta())
    return dt.isoformat()
