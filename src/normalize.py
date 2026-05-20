"""Convert raw jobseek payloads (DiscoveredJob / JobContent dicts) into the
existing ``jobs`` table row shape so downstream (ranker, renderer, generator)
sees no schema change.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import structlog

log = structlog.get_logger(__name__)

_REMOTE_LOCATION_TYPES = {"REMOTE", "remote", "Remote"}

# Annualisation factors for salary normalisation
_PERIOD_ANNUAL: dict[str, float] = {
    "year":  1.0,
    "month": 12.0,
    "hour":  2080.0,  # 52 weeks × 40 hours
}


def _external_id_from_url(url: str) -> str:
    """Derive a stable external_id from the job posting URL.

    Strategy: take the last non-empty path segment.  This gives consistent
    IDs across re-discovery (e.g. 'jobs/4567' → '4567').
    """
    try:
        path = urlparse(url).path.rstrip("/")
        return path.rsplit("/", 1)[-1] or url
    except Exception:
        return url


def _pick_locale(payload: dict) -> dict:
    """Return the English localisation of a payload, or the top-level fields.

    jobseek monitors may return a ``localizations`` dict keyed by ISO 639-1
    code.  We prefer 'en'; if that's absent we fall back to the top-level
    fields (the monitor's best-guess language).
    """
    localizations = payload.get("localizations") or {}
    en = localizations.get("en") or {}
    if en:
        # Merge: English overrides top-level where present
        return {**payload, **en}
    return payload


def _join_locations(locations: list[str] | None) -> str:
    """Join a list of location strings into a semicolon-separated string."""
    if not locations:
        return ""
    return "; ".join(loc.strip() for loc in locations if loc and loc.strip())


def _is_remote(payload: dict) -> int:
    """Return 1 when the posting is remote, 0 otherwise."""
    jlt = payload.get("job_location_type") or ""
    if jlt in _REMOTE_LOCATION_TYPES:
        return 1
    locs = payload.get("locations") or []
    for loc in locs:
        if loc and "remote" in loc.lower():
            return 1
    return 0


def normalize_to_jobs_row(payload: dict, board: Any) -> dict:
    """Convert a raw monitor/scraper payload dict into a ``jobs`` table row dict.

    Parameters
    ----------
    payload:
        JSON-decoded content from ``raw_jobs.payload``.  Matches the shape of
        jobseek's ``DiscoveredJob`` (from a monitor) or a merged
        DiscoveredJob+JobContent (after the scrape step).
    board:
        A ``sqlite3.Row`` (or dict-like) from the ``boards`` table with at
        least ``company_id``, ``monitor_type``, and ``board_slug`` fields.
        Also accepts a ``src.companies.Board`` dataclass — any object with
        ``company_id`` / ``monitor_type`` attributes.
    """
    data = _pick_locale(payload)

    url = data.get("url") or payload.get("url") or ""
    title = (data.get("title") or "").strip()
    if not title or not url:
        raise ValueError(f"Missing title or url in payload: url={url!r} title={title!r}")

    locations: list[str] | None = data.get("locations")
    description: str | None = data.get("description")
    date_posted: str | None = data.get("date_posted")
    employment_type: str | None = data.get("employment_type")

    # Board info — support both sqlite3.Row and dataclass-style objects
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        try:
            return obj[key] if obj[key] is not None else default
        except (KeyError, TypeError):
            return getattr(obj, key, default)

    company_id: int = _get(board, "company_id")
    monitor_type: str = _get(board, "monitor_type", "")
    board_slug: str = _get(board, "board_slug", "")

    location_str = _join_locations(locations)
    remote = _is_remote(data)

    external_id = _external_id_from_url(url)

    salary_min_usd, salary_max_usd = _extract_salary_usd(data)
    exp_years_max = _extract_exp_years(description)

    row: dict = {
        "external_id":   external_id,
        "company_id":    company_id,
        "title":         title,
        "description":   description,
        "location":      location_str or None,
        "remote":        remote,
        "url":           url,
        "posted_date":   _coerce_date(date_posted),
        "posted_at":     _coerce_date(date_posted),
        "ats_type":      monitor_type,
        "salary_min_usd": salary_min_usd,
        "salary_max_usd": salary_max_usd,
        "exp_years_max":  exp_years_max,
    }

    return row


_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _coerce_date(raw: str | None) -> str | None:
    """Extract a YYYY-MM-DD date from various date string formats."""
    if not raw:
        return None
    m = _DATE_RE.search(str(raw))
    return m.group(1) if m else None


def _extract_salary_usd(payload: dict) -> tuple[int | None, int | None]:
    """Return (salary_min_usd, salary_max_usd) as annual USD integers, or (None, None).

    Accepts:
    - ``payload["base_salary"]`` dict from rich monitors:
        ``{"currency": "USD", "min": 136800, "max": 273600, "unit": "year"}``
    - Falls back to ``parse_salary_text(description)`` for URL-only scrapers.
    """
    sal = payload.get("base_salary")

    if sal is None and payload.get("description"):
        from src.core.salary_extract import parse_salary_text
        sal = parse_salary_text(payload["description"])

    if not isinstance(sal, dict):
        return None, None

    currency = sal.get("currency", "USD")
    if currency != "USD":
        return None, None

    unit = sal.get("unit", "year")
    factor = _PERIOD_ANNUAL.get(unit, 1.0)
    sal_min = sal.get("min")
    sal_max = sal.get("max")

    try:
        min_usd = int(sal_min * factor) if sal_min is not None else None
        max_usd = int(sal_max * factor) if sal_max is not None else None
    except (TypeError, ValueError):
        return None, None

    # Sanity bounds: $10k–$2M annual; hourly rates × 2080 can hit low end
    if min_usd is not None and not (10_000 <= min_usd <= 2_000_000):
        return None, None
    if max_usd is not None and not (10_000 <= max_usd <= 2_000_000):
        max_usd = None

    return min_usd, max_usd


def _extract_exp_years(description: str | None) -> int | None:
    """Return the minimum years of experience required, using jobseek's extractor."""
    if not description:
        return None
    try:
        from src.core.experience_extract import extract_experience
        req = extract_experience(description)
        return req.min_years if req else None
    except Exception:
        return None
