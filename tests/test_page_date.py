"""The page's own posting date, found the way a person finds it in the page source (D45)."""

import httpx
import pytest

from src.processing import page_date
from src.processing.page_date import fetch_page_date, find_page_date


@pytest.mark.parametrize(
    ("html", "want"),
    [
        # SuccessFactors career sites (EY): microdata, the content attribute holds the date.
        ('<span itemprop="datePosted" content="Fri Oct 23 02:00:00 UTC 2026">23 Oct 2026</span>',
         "Fri Oct 23 02:00:00 UTC 2026"),
        ('<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-10-19"}</script>', "2026-10-19"),
        ('<meta name="job-posteddate" content="2026-09-01">', "2026-09-01"),
        ('<meta content="2026-10-26" property="article:published_time">', "2026-10-26"),
        ("window.__STATE__ = {job: {postedDate: '2026-10-07T00:00:00Z', id: 3}}", "2026-10-07T00:00:00Z"),
        ('{"jobPostedDate":"Oct 8, 2026"}', "Oct 8, 2026"),
    ],
)
def test_finds_the_posting_date(html, want):
    assert find_page_date(html) == want


@pytest.mark.parametrize(
    "html",
    [
        '{"datePublished":"2026-10-01"}',  # a CMS page date, not the job's
        '{"postedDate":"Posted 30+ Days Ago"}',  # no date in it
        '{"datePosted":"2099-01-01"}',  # implausible
        '<span itemprop="title" content="2026-10-01">',
        "",
    ],
)
def test_ignores_what_is_not_a_posting_date(html):
    assert find_page_date(html) is None


async def test_stops_fetching_a_host_whose_pages_carry_no_date(monkeypatch):
    monkeypatch.setattr(page_date, "_hits", page_date.Counter())
    monkeypatch.setattr(page_date, "_misses", page_date.Counter())

    async def no_robots(*a):
        return None

    monkeypatch.setattr(page_date, "ensure_allowed", no_robots)
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, html="<html>no date here</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for i in range(page_date.GIVE_UP_AFTER + 5):
            assert await fetch_page_date(f"https://jobs.example.com/job/{i}", client) is None
    assert len(calls) == page_date.GIVE_UP_AFTER
