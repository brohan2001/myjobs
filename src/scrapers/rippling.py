from __future__ import annotations

import json
import re

import httpx

from src.scrapers.base import BaseScraper

_CAREERS_URL = "https://www.rippling.com/careers/open-roles?pageSize=1000&page=0"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class RipplingScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.2)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                timeout=30.0,
            ) as client:
                resp = await client.get(_CAREERS_URL)
                resp.raise_for_status()
                html = resp.text
        except Exception:
            return []

        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        if not match:
            return []

        try:
            data = json.loads(match.group(1))
            items = data["props"]["pageProps"]["jobs"]["items"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

        jobs: list[dict] = []
        for item in items:
            try:
                locations = item.get("locations") or []
                location = locations[0]["name"] if locations else ""
                remote = 1 if "remote" in location.lower() else 0
                raw_id = str(item.get("id", ""))
                external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_id)[:80]
                jobs.append(
                    {
                        "external_id": external_id,
                        "company_id": company_id,
                        "title": item.get("name", ""),
                        "description": "",
                        "location": location,
                        "remote": remote,
                        "url": item.get("url", ""),
                        "posted_date": None,
                        "posted_at": None,
                        "ats_type": "rippling",
                    }
                )
            except (KeyError, TypeError, IndexError):
                continue

        return jobs
