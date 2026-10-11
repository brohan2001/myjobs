"""Zoho Recruit career page monitor.

Public careers page:
  GET https://{tenant}.zohorecruit.com/jobs/Careers (also .in domains)

Returns job listings embedded as HTML-escaped JSON inside:
  <input type="hidden" id="jobs" value="[...]">

Canonical job URL: https://{tenant}.zohorecruit.{tld}/jobs/Careers/{id}/{slug}
"""

from __future__ import annotations

import html as html_mod
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx
import structlog

from src.core.monitors import DiscoveredJob, register
from src.shared.http_retry import fetch_with_retry
from src.shared.truncation import truncated_rich_result

log = structlog.get_logger()

MAX_JOBS = 50_000

_DOMAIN_RE = re.compile(r"^([\w-]+)\.zohorecruit\.(com|in)$")

_IGNORE_TENANTS = frozenset({"api", "www", "app", "docs", "help", "support", "status", "cdn", "assets", "static", "mail", "admin"})


def _tenant_and_tld_from_url(board_url: str) -> tuple[str | None, str | None]:
    """Extract Zoho Recruit tenant subdomain and TLD (.com or .in)."""
    parsed = urlparse(board_url)
    host = (parsed.hostname or "").lower()
    if not host and "/" in board_url:
        host = board_url.split("/")[0].lower()
    elif not host:
        host = board_url.lower()

    match = _DOMAIN_RE.match(host)
    if match:
        tenant = match.group(1)
        tld = match.group(2)
        if tenant not in _IGNORE_TENANTS:
            return tenant, tld
    return None, None


def _slugify(title: str | None, job_id: str | int) -> str:
    """Derive URL slug from job title."""
    if not title:
        return str(job_id)
    slug = re.sub(r"[^\w\s-]", "", title).strip()
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or str(job_id)


def _parse_location(posting: dict) -> list[str] | None:
    """Extract location from City, State, Country fields."""
    city = posting.get("City")
    state = posting.get("State")
    country = posting.get("Country")

    parts = [str(p).strip() for p in (city, state, country) if p and str(p).strip() and str(p).strip() != "NA"]
    if parts:
        return [", ".join(parts)]
    return None


def _extract_jobs_json(html: str) -> list[dict]:
    """Extract embedded jobs JSON from HTML input element."""
    soup = BeautifulSoup(html, "html.parser")
    inp = soup.find("input", id="jobs")
    val = inp.get("value") if inp else None

    if not val:
        # Regex fallback in case of abnormal markup
        m = re.search(r'<input[^>]+id=[\"\']jobs[\"\'][^>]*value=([\"\'])(.*?)\1', html, re.DOTALL)
        if not m:
            m = re.search(r'<input[^>]+value=([\"\'])(.*?)\1[^>]*id=[\"\']jobs[\"\']', html, re.DOTALL)
        if m:
            val = html_mod.unescape(m.group(2))

    if not val:
        return []

    try:
        data = json.loads(val)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _parse_job(posting: dict, tenant: str, tld: str) -> DiscoveredJob | None:
    """Map a Zoho Recruit posting to a DiscoveredJob."""
    job_id = posting.get("id")
    if not job_id:
        return None

    title = posting.get("Posting_Title") or posting.get("Job_Opening_Name")
    slug = _slugify(title, job_id)
    url = f"https://{tenant}.zohorecruit.{tld}/jobs/Careers/{job_id}/{slug}"
    description = posting.get("Job_Description")
    locations = _parse_location(posting)
    employment_type = posting.get("Job_Type")

    metadata: dict = {"id": str(job_id)}
    extras: dict = {}
    if posting.get("Work_Experience"):
        extras["experience"] = posting["Work_Experience"]

    return DiscoveredJob(
        url=url,
        title=title,
        description=description,
        locations=locations,
        employment_type=employment_type,
        extras=extras or None,
        metadata=metadata,
    )


async def discover(board: dict, client: httpx.AsyncClient, pw=None) -> list[DiscoveredJob]:
    """Fetch job listings from the Zoho Recruit public Careers page."""
    metadata = board.get("metadata") or {}
    board_url = board.get("board_url", "")

    tenant, tld = _tenant_and_tld_from_url(board_url)
    tenant = metadata.get("tenant") or tenant
    tld = metadata.get("tld") or tld or "com"

    if not tenant:
        raise ValueError(
            f"Cannot derive Zoho Recruit tenant from board URL {board_url!r} and no tenant in metadata"
        )

    careers_url = f"https://{tenant}.zohorecruit.{tld}/jobs/Careers"
    html = await fetch_with_retry(client, careers_url, max_chars=2_000_000)
    if not html:
        return []

    raw_jobs = _extract_jobs_json(html)
    jobs: list[DiscoveredJob] = []
    for raw in raw_jobs:
        if isinstance(raw, dict):
            job = _parse_job(raw, tenant, tld)
            if job:
                jobs.append(job)

    if len(jobs) > MAX_JOBS:
        log.warning("zoho_recruit.truncated", url=careers_url, total=len(jobs), cap=MAX_JOBS)
        return truncated_rich_result(jobs)

    return jobs


async def can_handle(url: str, client: httpx.AsyncClient | None = None, pw=None) -> dict | None:
    """Detect Zoho Recruit: domain match -> careers page probe."""
    tenant, tld = _tenant_and_tld_from_url(url)
    if not tenant:
        return None

    if client is None:
        return {"tenant": tenant}

    tld = tld or "com"
    try:
        careers_url = f"https://{tenant}.zohorecruit.{tld}/jobs/Careers"
        resp = await client.get(careers_url, follow_redirects=True)
        if resp.status_code != 200:
            return None
        text = resp.text
        if "jobs" in text and ('id="jobs"' in text or "id='jobs'" in text):
            return {"tenant": tenant}
        return None
    except Exception:
        return None


register("zoho_recruit", discover, cost=10, can_handle=can_handle, rich=True)
