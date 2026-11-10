"""A job page's own posting date: the last resort for a job no feed or scraper dated (D45).

The same lookup a person does by viewing the page source and searching for "datePosted": JSON-LD and other embedded
JSON keys, ``itemprop="datePosted"`` microdata, and job-date meta tags. It runs only after a scrape came back undated,
fetches the page once, honours robots.txt, and stops trying a host whose pages turn out to carry no date.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

import httpx

from src.core.scrape import scrape_one as _scrape_one
from src.core.scrapers import JobContent, register
from src.logger import get_logger
from src.processing.cpu import _coerce_datetime
from src.shared.robots import RobotsDisallowedError, ensure_allowed

log = get_logger(__name__)

# Keys that mean "when this job was posted". Generic page dates (datePublished, createdAt) are left out: on a careers
# site they are often the CMS page's date, not the job's.
_KEYS = r"datePosted|postedDate|posted_date|postedOn|posted_on|postingDate|posting_date|publishDate|publish_date|jobPostedDate"
_JSON_KEY_RE = re.compile(rf"""["']?(?:{_KEYS})["']?\s*:\s*["']([^"'<>]{{6,40}})["']""", re.I)
_TAG_RE = re.compile(r"<(?:meta|span|time|div|p)\b[^>]*>", re.I)
_TAG_NAME_RE = re.compile(
    rf"""(?:itemprop|property|name)\s*=\s*["'](?:{_KEYS}|job-posteddate|article:published_time)["']""", re.I
)
_CONTENT_RE = re.compile(r"""(?:content|datetime)\s*=\s*["']([^"'<>]{6,40})["']""", re.I)

MAX_BYTES = 3_000_000
GIVE_UP_AFTER = 20  # undated pages from one host, with no dated page, before we stop fetching that host's pages

_hits: Counter[str] = Counter()
_misses: Counter[str] = Counter()


def find_page_date(html: str) -> str | None:
    """The posting date a job page's source carries, as found in it, or None."""
    for tag in _TAG_RE.findall(html):
        if _TAG_NAME_RE.search(tag) and (m := _CONTENT_RE.search(tag)) and _coerce_datetime(m.group(1)):
            return m.group(1)
    for m in _JSON_KEY_RE.finditer(html):
        if _coerce_datetime(m.group(1)):
            return m.group(1)
    return None


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def worth_trying(url: str) -> bool:
    host = _host(url)
    return bool(host) and (_hits[host] > 0 or _misses[host] < GIVE_UP_AFTER)


async def fetch_page_date(url: str, http: httpx.AsyncClient) -> str | None:
    """Fetch *url* once and return the posting date in its source, or None."""
    if not worth_trying(url):
        return None
    host = _host(url)
    try:
        await ensure_allowed(http, url, "dom")  # the job page is the company's site: honour its robots.txt
        resp = await http.get(url, follow_redirects=True, timeout=20)
    except (RobotsDisallowedError, httpx.HTTPError):
        return None
    if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "html"):
        return None
    found = find_page_date(resp.text[:MAX_BYTES])
    (_hits if found else _misses)[host] += 1
    if not found and _misses[host] == GIVE_UP_AFTER and not _hits[host]:
        log.info("page_date.host_has_no_dates", extra={"host": host})
    return found


async def _scrape_page_date(url: str, config: dict, client: httpx.AsyncClient, pw=None, artifact_dir=None) -> JobContent:
    """The ``page-date`` scraper: a rich board's enrich pass that only reads the page's date (D45)."""
    del pw, artifact_dir
    return JobContent(date_posted=await fetch_page_date(url, client))


register("page-date", _scrape_page_date)


async def scrape_one(url: str, scraper_type: str, scraper_config: dict | None, http: httpx.AsyncClient,
                     artifact_dir=None, job_id=None, pw=None) -> JobContent:
    """:func:`src.core.scrape.scrape_one`, then the page's own date when the scraper found none (D45)."""
    content = await _scrape_one(url, scraper_type, scraper_config, http, artifact_dir=artifact_dir, job_id=job_id,
                                pw=pw)
    if scraper_type != "page-date" and _coerce_datetime(content.date_posted) is None:
        from src.shared.http import client_for

        async with client_for(http, scraper_config or {}) as client:
            content.date_posted = await fetch_page_date(url, client) or content.date_posted
    return content
