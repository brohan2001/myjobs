"""robots.txt permission checks for the crawler.

The generic monitors in ``SITE_READING_MONITORS`` read a company's own site (sitemaps, HTML,
embedded data, sniffed XHR), so they honour that site's robots.txt for the generic ``*`` agent.
Every other monitor targets an ATS or portal endpoint built for listing jobs, whose robots
file isn't written for it; those are exempt (portal monitors by the user's decision, D25).
Results are cached per origin.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from src.logger import get_logger

log = get_logger(__name__)

# Generic monitors that read a company's own site. Everything else is an ATS/portal adapter.
SITE_READING_MONITORS = frozenset({"sitemap", "dom", "nextdata", "inline", "api_sniffer"})

_TTL_S = 24 * 3600
_cache: dict[str, tuple[float, RobotFileParser | None]] = {}


class RobotsDisallowedError(Exception):
    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"robots.txt disallows {url}")


def parse_robots(text: str | None) -> RobotFileParser | None:
    if not text:
        return None
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser


def allowed(parser: RobotFileParser | None, url: str) -> bool:
    return True if parser is None else parser.can_fetch("*", url)


async def _load(client: httpx.AsyncClient, origin: str, now: float) -> RobotFileParser | None:
    cached = _cache.get(origin)
    if cached and now - cached[0] < _TTL_S:
        return cached[1]
    parser = None
    try:
        resp = await client.get(f"{origin}/robots.txt", timeout=15)
        # 4xx: no robots file → everything allowed. 5xx/network: allow and retry later (not cached long).
        if resp.status_code == 200:
            parser = parse_robots(resp.text)
        elif resp.status_code >= 500:
            _cache[origin] = (now - _TTL_S + 600, None)
            return None
    except httpx.HTTPError:
        _cache[origin] = (now - _TTL_S + 600, None)
        return None
    _cache[origin] = (now, parser)
    return parser


async def ensure_allowed(client: httpx.AsyncClient, url: str, monitor_type: str) -> None:
    """Raise RobotsDisallowedError when the site's robots.txt forbids crawling ``url``."""
    if monitor_type not in SITE_READING_MONITORS:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return
    parser = await _load(client, f"{parsed.scheme}://{parsed.netloc}", time.time())
    if not allowed(parser, url):
        raise RobotsDisallowedError(url)
