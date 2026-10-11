"""Company discovery: candidate → careers board → ATS → validated → registry rows.

Wraps the jobseek discovery code (``career_discover.discover_career_pages``,
``monitors.detect_monitor_type``, ``monitor.monitor_one``) and adds the checks
the public feed needs before a board goes to production:

1. dedupe against the existing registry (by website domain and slug)
2. robots.txt must allow the board URL for a generic crawler
3. the board must parse to at least ``min_jobs`` real job URLs
4. HTTP-only (boards that need a browser go to the review queue for now)

Verified boards become ``companies.csv`` / ``boards.csv`` rows. Everything else
goes to the review queue with a reason, never straight into production.
"""
from __future__ import annotations

import asyncio
import csv
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from src.logger import get_logger

log = get_logger(__name__)

# Third-party portals whose ToS forbid scraping: never accept these as boards.
BLOCKED_HOSTS = (
    "naukri.com", "linkedin.com", "indeed.com", "indeed.co.in", "glassdoor.com", "glassdoor.co.in",
    "foundit.in", "monsterindia.com", "instahyre.com", "cutshort.io", "wellfound.com", "angel.co",
    "shine.com", "timesjobs.com", "iimjobs.com", "hirist.tech", "apna.co",
)
ROBOTS_AGENT = "*"

from src.shared.robots import API_MONITORS as TRUSTED_MONITORS  # noqa: E402  (shared list)


@dataclass
class Candidate:
    name: str
    website: str
    careers_url: str = ""
    hq_city: str = ""
    category: str = ""
    source: str = ""
    country: str = "IN"
    slug: str = ""  # set when re-discovering a board for a company already in the registry


@dataclass
class Outcome:
    candidate: Candidate
    status: str  # "accepted" | "review" | "duplicate" | "rejected"
    reason: str = ""
    board_url: str = ""
    monitor_type: str = ""
    monitor_config: dict = field(default_factory=dict)
    jobs_found: int = 0
    scraper_type: str = ""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def domain_of(url: str) -> str:
    """Registrable-ish host: lowercase, no scheme, no leading www."""
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "company"


def is_blocked_host(url: str) -> bool:
    host = domain_of(url)
    return any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)


def robots_allows(robots_txt: str | None, url: str, agent: str = ROBOTS_AGENT) -> bool:
    """True when robots.txt permits ``agent`` to fetch ``url``. Missing robots.txt allows everything."""
    if not robots_txt:
        return True
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(agent, url)


_JOBPOSTING_RE = re.compile(r'"@type"\s*:\s*\[?\s*"JobPosting"', re.IGNORECASE)
GENERIC_MONITORS = frozenset({"sitemap", "dom", "nextdata", "inline"})


def has_jobposting_jsonld(html: str) -> bool:
    """True when the page embeds schema.org JobPosting structured data."""
    return bool(_JOBPOSTING_RE.search(html or ""))


def load_candidates(path: Path) -> list[Candidate]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if not (r.get("name") and r.get("website")):
            continue
        out.append(Candidate(
            name=r["name"].strip(),
            website=r["website"].strip(),
            careers_url=(r.get("careers_url") or "").strip(),
            hq_city=(r.get("hq_city") or "").strip(),
            category=(r.get("category") or "").strip(),
            source=(r.get("source") or "").strip(),
            country=(r.get("country") or "IN").strip() or "IN",
            slug=(r.get("slug") or "").strip(),
        ))
    return out


def existing_index(companies: list[dict], boards: list[dict]) -> tuple[set[str], set[str], set[str]]:
    """(domains, slugs, board_urls) already in the registry."""
    domains = {domain_of(c.get("website", "")) for c in companies if c.get("website")}
    slugs = {c["slug"] for c in companies if c.get("slug")}
    board_urls = {b["board_url"].rstrip("/") for b in boards if b.get("board_url")}
    return domains, slugs, board_urls


def unique_slug(name: str, taken: set[str]) -> str:
    base = slugify(name)
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def registry_rows(outcome: Outcome, slug: str) -> tuple[dict, dict]:
    """companies.csv row + boards.csv row for an accepted outcome."""
    c = outcome.candidate
    company = {
        "slug": slug, "name": c.name, "website": c.website, "industry": "", "tier": "2", "enabled": "true",
        "country": c.country, "hq_city": c.hq_city, "company_type": c.category,
    }
    board = {
        "company_slug": slug,
        "board_slug": f"{slug}-{outcome.monitor_type}",
        "board_url": outcome.board_url,
        "monitor_type": outcome.monitor_type,
        "monitor_config": json.dumps(outcome.monitor_config) if outcome.monitor_config else "",
        "scraper_type": outcome.scraper_type,
        "scraper_config": "",
    }
    return company, board


# ---------------------------------------------------------------------------
# Network steps
# ---------------------------------------------------------------------------


async def _fetch_robots(client: httpx.AsyncClient, url: str, cache: dict[str, str | None]) -> str | None:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin in cache:
        return cache[origin]
    text: str | None = None
    try:
        resp = await client.get(f"{origin}/robots.txt", timeout=15)
        if resp.status_code == 200 and "text" in resp.headers.get("content-type", "text"):
            text = resp.text
    except httpx.HTTPError:
        text = None
    cache[origin] = text
    return text


async def _find_board(c: Candidate, client: httpx.AsyncClient) -> tuple[str, str, dict] | None:
    """(board_url, monitor_type, config) via the explicit careers URL, else homepage discovery."""
    from src.core.monitors import detect_monitor_type

    if c.careers_url and not is_blocked_host(c.careers_url):
        detected = await detect_monitor_type(c.careers_url, client)
        if detected:
            return c.careers_url, detected[0], detected[1] or {}

    from src.workspace.career_discover import discover_career_pages

    homepage = c.website if "://" in c.website else f"https://{c.website}"
    resp = await client.get(homepage, timeout=20)
    resp.raise_for_status()
    candidates = await discover_career_pages(str(resp.url), resp.text, client)
    candidates = [x for x in candidates if x.monitor_type and not is_blocked_host(x.url)]
    if not candidates:
        return None
    best = max(candidates, key=lambda x: x.score)
    return best.url, best.monitor_type, best.monitor_config or {}


async def _sample_is_jobs(client: httpx.AsyncClient, urls: list[str], sample: int = 3) -> bool:
    """At least 2 of ``sample`` evenly spread URLs (or all, if fewer) carry JobPosting JSON-LD."""
    urls = [u for u in urls if u.startswith(("http://", "https://"))]
    if not urls:
        return False
    step = max(1, len(urls) // sample)
    picks = urls[::step][:sample]
    hits = 0
    for url in picks:
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code == 200 and has_jobposting_jsonld(resp.text):
                hits += 1
        except (httpx.HTTPError, ValueError):
            continue
    return hits >= min(2, len(picks))


async def evaluate(
    c: Candidate,
    client: httpx.AsyncClient,
    *,
    min_jobs: int = 1,
    robots_cache: dict[str, str | None] | None = None,
) -> Outcome:
    from src.core.monitor import monitor_one
    from src.core.monitors import monitor_needs_browser

    robots_cache = robots_cache if robots_cache is not None else {}
    try:
        found = await _find_board(c, client)
    except Exception as exc:  # noqa: BLE001 - one bad site must not stop the batch
        return Outcome(c, "review", f"discovery error: {type(exc).__name__}: {str(exc)[:120]}")
    if not found:
        return Outcome(c, "review", "no careers board detected")
    board_url, monitor_type, config = found
    out = Outcome(c, "review", board_url=board_url, monitor_type=monitor_type, monitor_config=config)

    if monitor_needs_browser(monitor_type, config):
        out.reason = "needs browser rendering"
        return out
    if not robots_allows(await _fetch_robots(client, board_url, robots_cache), board_url):
        out.status, out.reason = "rejected", "robots.txt disallows board"
        return out
    try:
        result = await monitor_one(board_url, monitor_type, config, client)
    except Exception as exc:  # noqa: BLE001
        out.reason = f"monitor error: {type(exc).__name__}: {str(exc)[:120]}"
        return out
    out.jobs_found = len(result.urls)
    if out.jobs_found < min_jobs:
        out.reason = f"only {out.jobs_found} jobs parsed"
        return out
    if monitor_type not in TRUSTED_MONITORS:
        # Generic detectors can count ordinary pages as jobs. Accept only when sampled
        # URLs really are job postings (schema.org JobPosting), scraped via json-ld.
        if monitor_type in GENERIC_MONITORS and await _sample_is_jobs(client, sorted(result.urls)):
            out.status, out.reason, out.scraper_type = "accepted", "verified via JobPosting JSON-LD", "json-ld"
            return out
        out.reason = f"generic monitor ({monitor_type}) found {out.jobs_found} URLs; needs a human check"
        return out
    out.status, out.reason = "accepted", "verified"
    return out


async def run(
    candidates: list[Candidate],
    companies: list[dict],
    boards: list[dict],
    *,
    concurrency: int = 8,
    per_company_timeout: float = 150.0,
    min_jobs: int = 1,
    rediscover: bool = False,
    on_outcome=None,
) -> list[Outcome]:
    """Evaluate candidates concurrently. ``on_outcome(outcome)`` is called as each one finishes,
    so callers can persist progress (a stuck batch must not lose finished work)."""
    from src.shared.http import create_http_client

    domains, _slugs, board_urls = existing_index(companies, boards)
    outcomes: list[Outcome] = []
    todo: list[Candidate] = []
    seen_domains: set[str] = set()
    for c in candidates:
        d = domain_of(c.website)
        if is_blocked_host(c.website):
            outcomes.append(Outcome(c, "rejected", "job portal, not an employer site"))
        elif (d in domains and not rediscover) or d in seen_domains:
            outcomes.append(Outcome(c, "duplicate", "already in registry"))
        else:
            seen_domains.add(d)
            todo.append(c)

    sem = asyncio.Semaphore(concurrency)
    robots_cache: dict[str, str | None] = {}

    # Each company probes many ATS endpoints in parallel; size the pool for it.
    async with create_http_client(max_connections=max(50, concurrency * 12)) as client:
        async def _one(c: Candidate) -> Outcome:
            async with sem:
                try:
                    o = await asyncio.wait_for(
                        evaluate(c, client, min_jobs=min_jobs, robots_cache=robots_cache),
                        timeout=per_company_timeout,
                    )
                except TimeoutError:
                    o = Outcome(c, "review", f"timed out after {per_company_timeout:.0f}s")
                except Exception as exc:  # noqa: BLE001 - one bad site must not stop the batch
                    o = Outcome(c, "review", f"evaluation error: {type(exc).__name__}: {str(exc)[:120]}")
                if o.status == "accepted" and o.board_url.rstrip("/") in board_urls:
                    o.status, o.reason = "duplicate", "board already in registry"
                log.info("discovery.outcome", extra={"company": c.name, "status": o.status, "reason": o.reason,
                                                      "monitor_type": o.monitor_type, "jobs": o.jobs_found})
                if on_outcome is not None:
                    on_outcome(o)
                return o

        outcomes.extend(await asyncio.gather(*[_one(c) for c in todo]))
    return outcomes


def outcome_dict(o: Outcome) -> dict:
    d = asdict(o)
    d.update(d.pop("candidate"))
    d["monitor_config"] = json.dumps(o.monitor_config) if o.monitor_config else ""
    return d
