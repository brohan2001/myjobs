"""greytHR Hire career page monitor.

Public API:
  List: POST https://{tenant}.greythr.com/hire/api/career/published_jobs/
  Body: {}

Returns full job data in a single unpaginated request.
The response is a JSON object with a ``data`` array containing job objects
including HTML descriptions, location codes, and metadata.
Canonical job URL: https://{tenant}.greythr.com/hire/jobs/{slug}
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from urllib.parse import urlparse

import httpx
import structlog

from src.core.enum_normalize import normalize_employment_type, normalize_job_location_type
from src.core.monitors import DiscoveredJob, register
from src.shared.http_retry import PaginationFetchError, fetch_with_retry, is_retryable_status
from src.shared.truncation import truncated_rich_result

log = structlog.get_logger()

MAX_JOBS = 50_000

_DOMAIN_RE = re.compile(r"^([\w-]+)\.greythr\.com$")

_IGNORE_TENANTS = frozenset({"api", "www", "app", "docs", "help", "support", "status", "cdn", "assets", "static", "mail", "admin"})


def _tenant_from_url(board_url: str) -> str | None:
    """Extract greytHR tenant subdomain from a *.greythr.com URL."""
    parsed = urlparse(board_url)
    host = (parsed.hostname or "").lower()
    if not host and "/" in board_url:
        host = board_url.split("/")[0].lower()
    elif not host:
        host = board_url.lower()

    match = _DOMAIN_RE.match(host)
    if match:
        tenant = match.group(1)
        if tenant not in _IGNORE_TENANTS:
            return tenant
    return None


def _api_url(tenant: str) -> str:
    return f"https://{tenant}.greythr.com/hire/api/career/published_jobs/"


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = 3,
    base_delay: float = 0.5,
    timeout: float | None = None,
) -> str | None:
    """POST request with exponential backoff retry matching fetch_with_retry semantics."""
    last_exc: BaseException | None = None
    last_status: int | None = None

    for attempt in range(retries):
        try:
            resp = await client.post(
                url,
                json={},
                headers={"Content-Type": "application/json"},
                follow_redirects=True,
                timeout=timeout,
            )
            last_status = resp.status_code
            if resp.status_code == 200:
                text = resp.text
                if text:
                    return text
                last_exc = None
            elif resp.status_code in (404, 410):
                return None
            elif is_retryable_status(resp.status_code):
                last_exc = None
            else:
                return None
        except Exception as exc:
            last_exc = exc
            last_status = None

        if attempt < retries - 1:
            delay = base_delay * (2**attempt) * (0.5 + random.random())
            await asyncio.sleep(delay)

    raise PaginationFetchError(
        url,
        attempts=retries,
        last_status=last_status,
        last_error=type(last_exc).__name__ if last_exc else None,
    )


def _parse_location(posting: dict) -> list[str] | None:
    """Extract locations from greytHR posting."""
    raw_locs = posting.get("locations")
    if not raw_locs:
        return None

    if isinstance(raw_locs, list):
        locations: list[str] = []
        for loc in raw_locs:
            if isinstance(loc, dict):
                city = loc.get("city")
                state = loc.get("state")
                country = loc.get("country")
                parts = [p for p in (city, state, country) if p]
                loc_str = ", ".join(parts) if parts else loc.get("name")
            else:
                loc_str = str(loc).strip() if str(loc).strip() else None
            if loc_str and loc_str not in locations:
                locations.append(loc_str)
        return locations or None

    return [str(raw_locs)]


def _parse_job(posting: dict, tenant: str) -> DiscoveredJob | None:
    """Map a greytHR posting to a DiscoveredJob."""
    slug = posting.get("slug")
    if not slug:
        return None

    url = f"https://{tenant}.greythr.com/hire/jobs/{slug}"
    title = posting.get("title")
    description = posting.get("description")
    locations = _parse_location(posting)
    employment_type = posting.get("job_type")
    date_posted = posting.get("created_at") or posting.get("published_on_career_page")
    job_location_type = "remote" if posting.get("is_remote") else None

    metadata: dict = {}
    if posting.get("req_id"):
        metadata["req_id"] = str(posting["req_id"])
    if posting.get("id"):
        metadata["id"] = str(posting["id"])

    extras: dict = {}
    if posting.get("min_exp") is not None or posting.get("max_exp") is not None:
        extras["min_exp"] = posting.get("min_exp")
        extras["max_exp"] = posting.get("max_exp")
    if posting.get("experience_units"):
        extras["experience_units"] = posting.get("experience_units")

    return DiscoveredJob(
        url=url,
        title=title,
        description=description,
        locations=locations,
        employment_type=employment_type,
        job_location_type=job_location_type,
        date_posted=date_posted,
        extras=extras or None,
        metadata=metadata or None,
    )


async def discover(board: dict, client: httpx.AsyncClient, pw=None) -> list[DiscoveredJob]:
    """Fetch job listings from the greytHR public published_jobs API."""
    metadata = board.get("metadata") or {}
    board_url = board.get("board_url", "")

    tenant = metadata.get("tenant") or _tenant_from_url(board_url)
    if not tenant:
        raise ValueError(
            f"Cannot derive greytHR tenant from board URL {board_url!r} and no tenant in metadata"
        )

    api_url = _api_url(tenant)
    text = await _post_with_retry(client, api_url)
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    raw_postings = data.get("data")
    if not isinstance(raw_postings, list):
        return []

    jobs: list[DiscoveredJob] = []
    for raw in raw_postings:
        if isinstance(raw, dict):
            job = _parse_job(raw, tenant)
            if job:
                jobs.append(job)

    if len(jobs) > MAX_JOBS:
        log.warning("greythr.truncated", url=api_url, total=len(jobs), cap=MAX_JOBS)
        return truncated_rich_result(jobs)

    return jobs


async def can_handle(url: str, client: httpx.AsyncClient | None = None, pw=None) -> dict | None:
    """Detect greytHR: subdomain match -> API probe."""
    tenant = _tenant_from_url(url)
    if not tenant:
        return None

    if client is None:
        return {"tenant": tenant}

    try:
        resp = await client.post(
            _api_url(tenant),
            json={},
            headers={"Content-Type": "application/json"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return {"tenant": tenant}
        return None
    except Exception:
        return None


register("greythr", discover, cost=10, can_handle=can_handle, rich=True)
