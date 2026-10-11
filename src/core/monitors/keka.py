"""Keka Hire career page monitor.

Public API:
  List: GET https://{tenant}.keka.com/careers/api/jobs/default/active

Returns full job data in a single unpaginated request.
The response is a JSON list containing job objects with HTML descriptions,
location objects, salary ranges, and metadata.
Canonical job URL: https://{tenant}.keka.com/careers/jobdetails/{id}
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import httpx
import structlog

from src.core.enum_normalize import normalize_employment_type, normalize_salary_unit
from src.core.monitors import DiscoveredJob, register
from src.shared.http_retry import fetch_with_retry
from src.shared.truncation import truncated_rich_result

log = structlog.get_logger()

MAX_JOBS = 50_000

_DOMAIN_RE = re.compile(r"^([\w-]+)\.keka\.com$")

_IGNORE_TENANTS = frozenset({"api", "www", "app", "docs", "help", "support", "status", "cdn", "assets", "static", "mail", "admin"})

_SALARY_PERIOD_MAP: dict[int, str] = {
    1: "hour",
    2: "day",
    3: "month",
    4: "year",
}

_KEKA_JOB_TYPE_MAP: dict[int, str] = {
    1: "part_time",
    2: "full_time",
}


def _tenant_from_url(board_url: str) -> str | None:
    """Extract Keka tenant subdomain from a *.keka.com URL."""
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
    return f"https://{tenant}.keka.com/careers/api/jobs/default/active"


def _parse_location(posting: dict) -> list[str] | None:
    """Extract locations from jobLocations list."""
    job_locs = posting.get("jobLocations")
    if not job_locs or not isinstance(job_locs, list):
        return None

    locations: list[str] = []
    for loc in job_locs:
        if not isinstance(loc, dict):
            continue
        city = loc.get("city")
        state = loc.get("state")
        country = loc.get("countryCode") or loc.get("countryName")
        parts = [p for p in (city, state, country) if p]
        if parts:
            loc_str = ", ".join(parts)
        else:
            loc_str = loc.get("name")
        if loc_str and loc_str not in locations:
            locations.append(loc_str)

    return locations or None


def _parse_salary(posting: dict) -> dict | None:
    """Extract salary from salaryRange."""
    sal = posting.get("salaryRange")
    if not sal or not isinstance(sal, dict):
        return None

    sal_min = sal.get("minimum")
    sal_max = sal.get("maximum")
    if sal_min is None and sal_max is None:
        return None

    currency = sal.get("currency")
    period = sal.get("salaryPeriod")
    unit = None
    if isinstance(period, int):
        unit = _SALARY_PERIOD_MAP.get(period)
    if not unit and period is not None:
        unit = normalize_salary_unit(str(period))
    unit = unit or "year"

    return {"currency": currency, "min": sal_min, "max": sal_max, "unit": unit}


def _parse_employment_type(posting: dict) -> str | None:
    """Extract employment type from jobType."""
    raw_type = posting.get("jobType")
    if raw_type is None:
        return None
    if isinstance(raw_type, int) and raw_type in _KEKA_JOB_TYPE_MAP:
        return _KEKA_JOB_TYPE_MAP[raw_type]
    mapped = normalize_employment_type(str(raw_type))
    return mapped or str(raw_type)


def _parse_job(posting: dict, tenant: str) -> DiscoveredJob | None:
    """Map a Keka posting to a DiscoveredJob."""
    job_id = posting.get("id")
    if not job_id:
        return None

    url = f"https://{tenant}.keka.com/careers/jobdetails/{job_id}"
    title = posting.get("title")
    description = posting.get("description")
    locations = _parse_location(posting)
    employment_type = _parse_employment_type(posting)
    date_posted = posting.get("publishedOn")
    base_salary = _parse_salary(posting)

    metadata: dict = {}
    if posting.get("jobNumber"):
        metadata["req_id"] = posting["jobNumber"]
    if posting.get("departmentName"):
        metadata["department"] = posting["departmentName"]

    extras: dict = {}
    if posting.get("experience"):
        extras["experience"] = posting["experience"]
    if posting.get("skillNames"):
        extras["skills"] = posting["skillNames"]

    return DiscoveredJob(
        url=url,
        title=title,
        description=description,
        locations=locations,
        employment_type=employment_type,
        date_posted=date_posted,
        base_salary=base_salary,
        extras=extras or None,
        metadata=metadata or None,
    )


async def discover(board: dict, client: httpx.AsyncClient, pw=None) -> list[DiscoveredJob]:
    """Fetch job listings from the Keka public active jobs API."""
    metadata = board.get("metadata") or {}
    board_url = board.get("board_url", "")

    tenant = metadata.get("tenant") or _tenant_from_url(board_url)
    if not tenant:
        raise ValueError(
            f"Cannot derive Keka tenant from board URL {board_url!r} and no tenant in metadata"
        )

    api_url = _api_url(tenant)
    text = await fetch_with_retry(client, api_url)
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    jobs: list[DiscoveredJob] = []
    for raw in data:
        if isinstance(raw, dict):
            job = _parse_job(raw, tenant)
            if job:
                jobs.append(job)

    if len(jobs) > MAX_JOBS:
        log.warning("keka.truncated", url=api_url, total=len(jobs), cap=MAX_JOBS)
        return truncated_rich_result(jobs)

    return jobs


async def can_handle(url: str, client: httpx.AsyncClient | None = None, pw=None) -> dict | None:
    """Detect Keka: subdomain match -> API probe."""
    tenant = _tenant_from_url(url)
    if not tenant:
        return None

    if client is None:
        return {"tenant": tenant}

    try:
        resp = await client.get(_api_url(tenant), follow_redirects=True)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, list):
            return {"tenant": tenant}
        return None
    except Exception:
        return None


register("keka", discover, cost=10, can_handle=can_handle, rich=True)
