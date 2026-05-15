from __future__ import annotations

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_API = "https://boards.greenhouse.io/v1/boards/{slug}/jobs?content=true"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class GreenhouseScraper(BaseScraper):
    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        slug = company["slug"]
        url = _API.format(slug=slug)
        try:
            resp = await self._get(url)
        except ScraperError as e:
            if "403" not in str(e):
                raise
            # Some boards (e.g. Coinbase) have Cloudflare in front of their
            # Greenhouse board. Retry with a Chrome TLS fingerprint.
            resp = await self._get_cffi(url)
            if resp is None:
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
            posted_at = raw_ts or None

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

    async def _get_cffi(self, url: str):
        """GET with Chrome TLS fingerprint via curl_cffi. Returns None on failure."""
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            return None
        try:
            async with AsyncSession(impersonate="chrome") as session:
                resp = await session.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": _UA,
                    },
                    timeout=20,
                )
                if resp.status_code != 200:
                    return None
                # Wrap in a minimal response-like object with .json()
                return _CffiResponse(resp)
        except Exception:
            return None


class _CffiResponse:
    """Minimal wrapper so curl_cffi response looks like httpx response to callers."""
    def __init__(self, resp):
        self._resp = resp

    def json(self):
        return self._resp.json()


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)
