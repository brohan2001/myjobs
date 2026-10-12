"""User-Agent policy (DECISIONS D14): honest by default, Chrome for allowlisted WAF hosts."""

import httpx
import pytest

from src.shared import http as shared_http
from src.shared.http import (
    CHROME_USER_AGENT,
    HONEST_USER_AGENT,
    ChromeUAForWAFHostsTransport,
    create_http_client,
    wants_chrome_ua,
)


@pytest.mark.parametrize(
    "host,expected",
    [
        ("apply.deloitte.com", True),
        ("APPLY.DELOITTE.COM.", True),
        ("recruitingapp-1619.umantis.com", True),
        ("umantis.com", True),
        ("jobs.talentclue.com", True),
        ("boards-api.greenhouse.io", False),
        ("notumantis.com", False),
        ("deloitte.com", False),
    ],
)
def test_wants_chrome_ua(host, expected):
    assert wants_chrome_ua(host) is expected


def _capturing_transport(seen: list[str]) -> ChromeUAForWAFHostsTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, text="ok")

    return ChromeUAForWAFHostsTransport(httpx.MockTransport(handler))


async def _get(url: str, headers: dict | None = None) -> str:
    seen: list[str] = []
    async with httpx.AsyncClient(
        transport=_capturing_transport(seen), headers={"User-Agent": HONEST_USER_AGENT}
    ) as client:
        await client.get(url, headers=headers)
    return seen[0]


async def test_default_host_gets_honest_ua():
    assert await _get("https://boards-api.greenhouse.io/v1/boards/x/jobs") == HONEST_USER_AGENT


async def test_allowlisted_host_gets_chrome_ua():
    assert await _get("https://careers.bain.com/jobs") == CHROME_USER_AGENT


async def test_explicit_override_wins_on_allowlisted_host():
    assert await _get("https://careers.bain.com/jobs", headers={"User-Agent": "custom/1"}) == "custom/1"


async def test_create_http_client_defaults_to_honest_ua():
    client = create_http_client()
    try:
        assert client.headers["User-Agent"] == HONEST_USER_AGENT
        assert shared_http.DEFAULT_USER_AGENT == HONEST_USER_AGENT
    finally:
        await client.aclose()
