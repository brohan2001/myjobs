from __future__ import annotations

import httpx
import pytest

from src.shared import robots


@pytest.fixture(autouse=True)
def _clear_cache():
    robots._cache.clear()


def _client(robots_txt: str | None, status: int = 200) -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/robots.txt"
        return httpx.Response(status, text=robots_txt or "")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_api_monitors_are_exempt():
    async with _client("User-agent: *\nDisallow: /") as c:
        await robots.ensure_allowed(c, "https://job-boards.greenhouse.io/acme", "greenhouse")


async def test_disallowed_site_raises():
    async with _client("User-agent: *\nDisallow: /careers") as c:
        with pytest.raises(robots.RobotsDisallowedError):
            await robots.ensure_allowed(c, "https://acme.com/careers/jobs", "sitemap")


async def test_allowed_path_passes_and_missing_robots_allows():
    async with _client("User-agent: *\nDisallow: /admin") as c:
        await robots.ensure_allowed(c, "https://acme.com/careers", "dom")
    robots._cache.clear()
    async with _client(None, status=404) as c:
        await robots.ensure_allowed(c, "https://acme.com/careers", "dom")


async def test_server_error_allows_and_is_cached_briefly():
    async with _client(None, status=503) as c:
        await robots.ensure_allowed(c, "https://acme.com/careers", "dom")
    ts, parser = robots._cache["https://acme.com"]
    assert parser is None
