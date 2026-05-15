from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper, ScraperError

_GUEST_API = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords=software+engineer&company={company_id}"
    "&f_TPR=r2592000&start={start}"  # last 30 days (was 7 days)
)
_BROAD_API = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords={keywords}&location=United+States&f_TPR=r86400&start={start}"
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

_META_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


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


class LinkedInBroadScraper(BaseScraper):
    """Keyword-based LinkedIn search across all companies. Best-effort — may be rate-limited."""

    def __init__(self):
        super().__init__(rate_limit_rps=0.2)  # 1 req per 5 seconds

    async def __aenter__(self) -> "LinkedInBroadScraper":
        import httpx
        self.client = httpx.AsyncClient(
            headers=_LI_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        return self

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        return []  # not used in per-company pipeline; call search() directly

    async def search(
        self,
        keywords: str,
        max_results: int = 100,
        company_name_to_id: dict[str, int] | None = None,
    ) -> list[dict]:
        """Fetch broad LinkedIn results. Returns raw job dicts; company_id=-1 if unknown."""
        name_to_id = {k.lower(): v for k, v in (company_name_to_id or {}).items()}
        url_keywords = keywords.replace(" ", "+")
        all_jobs: list[dict] = []
        start = 0

        while start < max_results:
            url = _BROAD_API.format(keywords=url_keywords, start=start)
            try:
                resp = await self._get(url)
            except ScraperError:
                break

            text = resp.text
            if not text.strip() or "login" in resp.url.path.lower():
                break

            parsed = _parse_li_html_broad(text, name_to_id)
            if not parsed:
                break

            all_jobs.extend(parsed)
            start += 10
            if len(parsed) < 10:
                break

        return all_jobs


class MetaScraper(BaseScraper):
    """Scrape Meta Careers via Playwright — intercepts the internal GraphQL API."""

    def __init__(self):
        super().__init__(rate_limit_rps=0.25)
        self._pw_ctx = None
        self._pw = None
        self._browser = None

    async def __aenter__(self) -> "MetaScraper":
        await super().__aenter__()
        try:
            from playwright.async_api import async_playwright
            self._pw_ctx = async_playwright()
            self._pw = await self._pw_ctx.__aenter__()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            self._browser = None
        return self

    async def __aexit__(self, *args) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw_ctx:
            try:
                await self._pw_ctx.__aexit__(*args)
            except Exception:
                pass
        await super().__aexit__(*args)

    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        if not self._browser:
            return []

        context = await self._browser.new_context(
            user_agent=_META_UA,
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        intercepted: list[dict] = []

        async def on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if "graphql" in url and "json" in ct:
                try:
                    data = await resp.json()
                    if isinstance(data, dict):
                        intercepted.append(data)
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            await page.goto("https://www.metacareers.com/jobs", wait_until="networkidle", timeout=45_000)
            await asyncio.sleep(3)
        except Exception:
            await page.close()
            await context.close()
            return []

        await page.close()
        await context.close()

        return _parse_meta_graphql(intercepted, company_id)


def _parse_meta_graphql(responses: list[dict], company_id: int) -> list[dict]:
    """Parse intercepted GraphQL responses from metacareers.com."""
    jobs: list[dict] = []
    seen_ids: set[str] = set()

    for resp in responses:
        job_nodes = _extract_meta_jobs(resp)
        for node in job_nodes:
            job = _parse_meta_job_node(node, company_id, seen_ids)
            if job:
                jobs.append(job)

    return jobs


def _extract_meta_jobs(data: dict) -> list[dict]:
    """Walk GraphQL response to find job listing nodes — handles multiple response shapes."""
    # Shape 1: data.job_search.results[].item
    try:
        results = data["data"]["job_search"]["results"]
        nodes = [r.get("item", r) for r in results if isinstance(r, dict)]
        if nodes:
            return nodes
    except (KeyError, TypeError):
        pass

    # Shape 2: data.jobs_search.jobs[]
    try:
        jobs = data["data"]["jobs_search"]["jobs"]
        if jobs:
            return jobs
    except (KeyError, TypeError):
        pass

    # Shape 3: data.jobSearch.edges[].node
    try:
        edges = data["data"]["jobSearch"]["edges"]
        nodes = [e.get("node", e) for e in edges if isinstance(e, dict)]
        if nodes:
            return nodes
    except (KeyError, TypeError):
        pass

    # Shape 4: direct jobs array
    try:
        jobs = data["data"]["jobs"]
        if isinstance(jobs, list) and jobs:
            return jobs
    except (KeyError, TypeError):
        pass

    return []


def _parse_meta_job_node(node: dict, company_id: int, seen_ids: set) -> dict | None:
    job_id = str(node.get("id", "") or node.get("jobId", "") or "")
    if not job_id or job_id in seen_ids:
        return None
    seen_ids.add(job_id)

    title = node.get("title", "") or node.get("name", "")
    if not title:
        return None

    loc = node.get("location", {}) or {}
    if isinstance(loc, dict):
        location = loc.get("name", "") or loc.get("city", "") or loc.get("displayName", "")
    elif isinstance(loc, str):
        location = loc
    else:
        location = node.get("sub_title", "") or ""

    remote_type = node.get("remote_type", "") or node.get("remoteType", "") or ""
    remote = 1 if remote_type in ("REMOTE", "FLEXIBLE") or "remote" in location.lower() else 0

    url = (
        node.get("careersite_job_url", "")
        or node.get("url", "")
        or f"https://www.metacareers.com/jobs/{job_id}"
    )

    description = node.get("description", "") or node.get("summary", "") or ""

    posted_raw = (
        node.get("posted_date", "")
        or node.get("postedDate", "")
        or node.get("publishedAt", "")
        or ""
    )
    posted_date = posted_raw[:10] if posted_raw else None
    posted_at = posted_raw if posted_raw else None

    external_id = re.sub(r"[^a-zA-Z0-9_-]", "_", job_id)[:80]

    return {
        "external_id": external_id,
        "company_id":  company_id,
        "title":       title,
        "description": description,
        "location":    location,
        "remote":      remote,
        "url":         url,
        "posted_date": posted_date,
        "posted_at":   posted_at,
        "ats_type":    "meta",
    }


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

        url = link_tag.get("href", "").split("?")[0]
        id_match = re.search(r"/view/(\d+)", url)
        if not id_match:
            continue
        external_id = id_match.group(1)

        title = title_tag.get_text(strip=True)
        location = location_tag.get_text(strip=True) if location_tag else ""
        remote = 1 if "remote" in location.lower() else 0

        posted_date, posted_at = _parse_li_time(time_tag)

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


def _parse_li_html_broad(html: str, name_to_id: dict[str, int]) -> list[dict]:
    """Parse broad LinkedIn search HTML. Extracts company name and resolves to known company_id."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_="base-card")
    jobs = []

    for card in cards:
        link_tag = card.find("a", class_="base-card__full-link")
        title_tag = card.find("h3", class_=re.compile("base-search-card__title"))
        company_tag = card.find("h4", class_=re.compile("base-search-card__subtitle"))
        location_tag = card.find("span", class_=re.compile("job-search-card__location"))
        time_tag = card.find("time")

        if not link_tag or not title_tag:
            continue

        url = link_tag.get("href", "").split("?")[0]
        id_match = re.search(r"/view/(\d+)", url)
        if not id_match:
            continue
        external_id = id_match.group(1)

        title = title_tag.get_text(strip=True)
        company_name = company_tag.get_text(strip=True) if company_tag else ""
        location = location_tag.get_text(strip=True) if location_tag else ""
        remote = 1 if "remote" in location.lower() else 0

        posted_date, posted_at = _parse_li_time(time_tag)

        company_id: int | None = None
        if company_name:
            key = company_name.lower().strip()
            company_id = name_to_id.get(key)
            if company_id is None:
                for known, cid in name_to_id.items():
                    if known in key or key in known:
                        company_id = cid
                        break

        jobs.append({
            "external_id":    external_id,
            "company_id":     company_id,
            "_company_name":  company_name,
            "title":          title,
            "description":    "",
            "location":       location,
            "remote":         remote,
            "url":            url,
            "posted_date":    posted_date,
            "posted_at":      posted_at,
            "ats_type":       "linkedin",
        })

    return jobs


def _parse_li_time(time_tag) -> tuple[str | None, str | None]:
    if not time_tag:
        return None, None
    dt_attr = time_tag.get("datetime", "")
    if dt_attr:
        posted_date = dt_attr[:10]
        posted_at = dt_attr if "T" in dt_attr else dt_attr
        return posted_date, posted_at
    rel = time_tag.get_text(strip=True).lower()
    posted_at_dt = _parse_relative_time(rel)
    if posted_at_dt:
        return posted_at_dt[:10], posted_at_dt
    return None, None


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
