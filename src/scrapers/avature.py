"""Avature ATS scraper — uses the public RSS feed endpoint."""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from src.scrapers.base import BaseScraper, ScraperError

_FEED_URL = "https://{host}/careers/SearchJobs/feed/?jobRecordsPerPage=20&offset={offset}"
_MAX_JOBS = 300
_PAGE_SIZE = 20


class AvatureScraper(BaseScraper):
    def __init__(self):
        super().__init__(rate_limit_rps=0.5)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        host = company.get("avature_host", "")
        if not host:
            return []

        jobs: list[dict] = []
        offset = 0

        while offset < _MAX_JOBS:
            url = _FEED_URL.format(host=host, offset=offset)
            try:
                resp = await self._get(url)
            except ScraperError:
                break

            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                break

            items = root.findall(".//item")
            if not items:
                break

            for item in items:
                title_raw = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or item.findtext("guid") or "").strip()
                pub_date_raw = item.findtext("pubDate") or ""

                # Titles often have "- Location" appended at the end
                location = ""
                title = title_raw
                m = re.search(r"\s+-\s+([^-]+)$", title_raw)
                if m:
                    location = m.group(1).strip()
                    title = title_raw[: m.start()].strip()

                posted_date = None
                if pub_date_raw:
                    try:
                        dt = parsedate_to_datetime(pub_date_raw)
                        posted_date = dt.date().isoformat()
                    except Exception:
                        pass

                # Derive external_id from URL path
                path = re.sub(r"https?://[^/]+", "", link).strip("/")
                external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", path)[:80]
                if not external_id:
                    external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", link)[:80]

                remote = 1 if "remote" in (title + location).lower() else 0

                jobs.append({
                    "external_id": external_id,
                    "company_id":  company_id,
                    "title":       title,
                    "description": "",
                    "location":    location,
                    "remote":      remote,
                    "url":         link,
                    "posted_date": posted_date,
                    "posted_at":   None,
                    "ats_type":    "avature",
                })

            offset += _PAGE_SIZE
            if len(items) < _PAGE_SIZE:
                break

        return jobs
