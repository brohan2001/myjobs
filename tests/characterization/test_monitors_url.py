"""Characterization of URL-only monitors: workday, smartrecruiters, sitemap."""

from __future__ import annotations

import json

import httpx
import pytest

from src.core.monitors import sitemap, smartrecruiters, workday
from src.shared.http_retry import PaginationFetchError

WD_BOARD = {
    "board_url": "https://acme.wd5.myworkdayjobs.com/Careers",
    "metadata": {"all_sites": False},
}
WD_PREFIX = "https://acme.wd5.myworkdayjobs.com/Careers"


# -------------------------------------------------------------------------- workday


def test_workday_components_and_urls():
    assert workday._parse_components("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite") == (
        "nvidia", "wd5", "NVIDIAExternalCareerSite",
    )
    assert workday._api_list_url("acme", "wd5", "Careers") == (
        "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
    )
    assert workday._parse_components("https://example.com/x") is None


async def test_workday_synthetic_fixture(fixture_json, make_client):
    payload = fixture_json("workday_synthetic.json")
    bodies = []

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert str(req.url) == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        urls = await workday.discover(WD_BOARD, client)

    assert bodies == [{"limit": 20, "offset": 0}]
    assert urls == {
        f"{WD_PREFIX}/job/WD-001234_Software-Engineer-New-Grad",
        f"{WD_PREFIX}/job/WD-005678_Cloud-Infrastructure-Engineer",
        f"{WD_PREFIX}/job/WD-009012_Senior-Software-Engineer",
    }


def _wd_postings(start: int, n: int):
    return [{"title": f"J{i}", "externalPath": f"/job/R{i}"} for i in range(start, start + n)]


async def test_workday_pagination_two_pages_then_stop(make_client):
    offsets = []

    def handler(req):
        body = json.loads(req.content)
        offsets.append(body["offset"])
        assert body["limit"] == 20
        if body["offset"] == 0:
            return httpx.Response(200, json={"total": 25, "jobPostings": _wd_postings(0, 20)})
        return httpx.Response(200, json={"total": 25, "jobPostings": _wd_postings(20, 5)})

    async with make_client(handler) as client:
        urls = await workday.discover(WD_BOARD, client)

    assert offsets == [0, 20]  # offset 25 >= total 25 -> stop
    assert len(urls) == 25
    assert f"{WD_PREFIX}/job/R24" in urls


async def test_workday_short_pagination_fails_the_check(make_client):
    """Fewer jobs than advertised fails the check (upstream, re-sync 2026-10-15), so a partial list
    can never delist the jobs it missed."""

    def handler(req):
        body = json.loads(req.content)
        postings = _wd_postings(0, 20) if body["offset"] == 0 else []
        return httpx.Response(200, json={"total": 100, "jobPostings": postings})

    async with make_client(handler) as client:
        with pytest.raises(RuntimeError, match="20 of 100"):
            await workday.discover(WD_BOARD, client)


async def test_workday_retry_then_success(make_client, sleeps):
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        if n["c"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"total": 1, "jobPostings": _wd_postings(0, 1)})

    async with make_client(handler) as client:
        urls = await workday.discover(WD_BOARD, client)
    assert urls == {f"{WD_PREFIX}/job/R0"}
    assert len(sleeps) == 1


async def test_workday_single_site_persistent_503_raises(make_client, sleeps):
    async with make_client(lambda r: httpx.Response(503)) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await workday.discover(WD_BOARD, client)
    assert ei.value.attempts == 3 and ei.value.last_status == 503


async def test_workday_400_fails_fast(make_client, sleeps):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(400)

    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await workday.discover(WD_BOARD, client)
    assert calls == [1] and ei.value.last_status == 400


async def test_workday_multi_site_all_sites_failing_raises(make_client, sleeps):
    """Changed deliberately (was: returned an empty set). When every site's list
    endpoint fails, ``discover`` raises so the board takes a failure strike
    instead of reporting a clean "0 jobs" run.
    """
    robots = (
        "User-agent: *\n"
        "Sitemap: https://acme.wd5.myworkdayjobs.com/Careers/siteMap.xml\n"
    )

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(503)

    board = {"board_url": "https://acme.wd5.myworkdayjobs.com/Careers"}
    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError):
            await workday.discover(board, client)


async def test_workday_multi_site_partial_failure_fails_the_check(make_client, sleeps):
    """One site fails: the whole check fails (upstream, re-sync 2026-10-15), so the failed site's
    postings are not delisted as gone."""
    robots = (
        "Sitemap: https://acme.wd5.myworkdayjobs.com/SiteA/siteMap.xml\n"
        "Sitemap: https://acme.wd5.myworkdayjobs.com/SiteB/siteMap.xml\n"
    )

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if "/SiteB/" in req.url.path:
            return httpx.Response(503)
        return httpx.Response(200, json={"total": 1, "jobPostings": _wd_postings(0, 1)})

    board = {"board_url": "https://acme.wd5.myworkdayjobs.com/SiteA"}
    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError):
            await workday.discover(board, client)


async def test_workday_multi_site_discovers_sites_from_robots(make_client):
    robots = (
        "Sitemap: https://acme.wd5.myworkdayjobs.com/SiteA/siteMap.xml\n"
        "Sitemap: https://acme.wd5.myworkdayjobs.com/SiteB/siteMap.xml\n"
    )

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        site = req.url.path.split("/")[-2]
        return httpx.Response(200, json={"total": 1, "jobPostings": [{"externalPath": f"/job/{site}-1"}]})

    board = {"board_url": "https://acme.wd5.myworkdayjobs.com/Careers"}
    async with make_client(handler) as client:
        urls = await workday.discover(board, client)
    assert urls == {
        "https://acme.wd5.myworkdayjobs.com/SiteA/job/SiteA-1",
        "https://acme.wd5.myworkdayjobs.com/SiteB/job/SiteB-1",
    }


# --------------------------------------------------------------- smartrecruiters


async def test_smartrecruiters_synthetic_fixture(fixture_json, make_client):
    payload = fixture_json("smartrecruiters_list_synthetic.json")
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        urls = await smartrecruiters.discover({"board_url": "https://jobs.smartrecruiters.com/Acme"}, client)

    assert str(seen[0].url) == "https://api.smartrecruiters.com/v1/companies/Acme/postings?limit=100&offset=0"
    assert len(seen) == 1  # offset 100 >= totalFound 3
    assert urls == {
        "https://jobs.smartrecruiters.com/Acme/743999000001",
        "https://jobs.smartrecruiters.com/Acme/743999000002",
        "https://jobs.smartrecruiters.com/Acme/743999000003",
    }


async def test_smartrecruiters_posting_without_id_fails_the_check(make_client):
    payload = {"totalFound": 1, "content": [{"name": "Missing id"}]}
    async with make_client(lambda r: httpx.Response(200, json=payload)) as client:
        with pytest.raises(ValueError, match="valid id"):
            await smartrecruiters.discover({"board_url": "https://jobs.smartrecruiters.com/Acme"}, client)


async def test_smartrecruiters_pagination_two_pages(make_client):
    offsets = []

    def handler(req):
        off = int(req.url.params["offset"])
        offsets.append(off)
        n = 100 if off == 0 else 7
        return httpx.Response(
            200, json={"totalFound": 107, "content": [{"id": f"p{off + i}"} for i in range(n)]}
        )

    async with make_client(handler) as client:
        urls = await smartrecruiters.discover(
            {"board_url": "x", "metadata": {"token": "Acme"}}, client
        )
    assert offsets == [0, 100]
    assert len(urls) == 107


async def test_smartrecruiters_retry_and_failures(make_client, sleeps):
    n = {"c": 0}

    def flaky(req):
        n["c"] += 1
        if n["c"] < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={"totalFound": 1, "content": [{"id": "a"}]})

    async with make_client(flaky) as client:
        urls = await smartrecruiters.discover({"board_url": "x", "metadata": {"token": "T"}}, client)
    assert urls == {"https://jobs.smartrecruiters.com/T/a"}

    async with make_client(lambda r: httpx.Response(404)) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await smartrecruiters.discover({"board_url": "x", "metadata": {"token": "T"}}, client)
    assert ei.value.last_status == 404 and ei.value.attempts == 1

    async with make_client(lambda r: httpx.Response(200, json=[])) as client:
        with pytest.raises(PaginationFetchError):
            await smartrecruiters.discover({"board_url": "x", "metadata": {"token": "T"}}, client)


# -------------------------------------------------------------------------- sitemap

SM_BOARD = {"board_url": "https://careers.example.com/jobs"}


def _xml(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=text, headers={"content-type": "application/xml"})


async def test_sitemap_urlset_walk_up_discovery(fixture_text, make_client):
    xml = fixture_text("sitemap_urlset_synthetic.xml")
    requested = []

    def handler(req):
        requested.append(str(req.url))
        if str(req.url) == "https://careers.example.com/sitemap.xml":
            return _xml(xml)
        return httpx.Response(404)

    async with make_client(handler) as client:
        urls, new_sitemap = await sitemap.discover(SM_BOARD, client)

    # robots.txt is always fetched first (candidate list is built eagerly), then
    # candidates are walked from most specific to root
    assert requested == [
        "https://careers.example.com/robots.txt",
        "https://careers.example.com/jobs/sitemap.xml",
        "https://careers.example.com/sitemap.xml",
    ]
    assert new_sitemap == "https://careers.example.com/sitemap.xml"
    # utm_* stripped, other params kept, whitespace trimmed
    assert urls == {
        "https://careers.example.com/jobs/101",
        "https://careers.example.com/jobs/102?gh_src=abc",
        "https://careers.example.com/jobs/103",
    }


async def test_sitemap_cached_url_returns_no_new_sitemap(fixture_text, make_client):
    xml = fixture_text("sitemap_urlset_synthetic.xml")
    async with make_client(lambda r: _xml(xml)) as client:
        urls, new = await sitemap.discover(
            {"board_url": "https://careers.example.com/", "metadata": {"sitemap_url": "https://careers.example.com/s.xml"}},
            client,
        )
    assert len(urls) == 3
    assert new is None


async def test_sitemap_index_prefers_job_children(fixture_text, make_client):
    index = fixture_text("sitemap_index_synthetic.xml")
    shard = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://careers.example.com/jobs/{n}</loc></url></urlset>'
    )
    requested = []

    def handler(req):
        u = str(req.url)
        requested.append(u)
        if u.endswith("/sitemap.xml") and "jobs-" not in u:
            return _xml(index)
        if u.endswith("sitemap-jobs-1.xml"):
            return _xml(shard.format(n=1))
        if u.endswith("sitemap-jobs-2.xml"):
            return _xml(shard.format(n=2))
        return httpx.Response(404)

    async with make_client(handler) as client:
        urls, _ = await sitemap.discover(SM_BOARD, client)
    assert urls == {"https://careers.example.com/jobs/1", "https://careers.example.com/jobs/2"}
    assert not any("sitemap-blog" in u for u in requested)  # non-job child skipped


async def test_sitemap_child_shard_503_raises_instead_of_truncating(fixture_text, make_client, sleeps):
    index = fixture_text("sitemap_index_synthetic.xml")

    def handler(req):
        u = str(req.url)
        if u.endswith("careers.example.com/sitemap.xml"):
            return _xml(index)
        if u.endswith("sitemap-jobs-1.xml"):
            return _xml('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://c/1</loc></url></urlset>')
        return httpx.Response(503)

    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await sitemap.discover(SM_BOARD, client)
    assert ei.value.last_status == 503


async def test_sitemap_nothing_found_raises(make_client):
    async with make_client(lambda r: httpx.Response(404)) as client:
        with pytest.raises(sitemap.SitemapDiscoveryError):
            await sitemap.discover(SM_BOARD, client)


async def test_sitemap_robots_txt_fallback(fixture_text, make_client):
    xml = fixture_text("sitemap_urlset_synthetic.xml")

    def handler(req):
        u = str(req.url)
        if u.endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nSitemap: https://careers.example.com/custom-map.xml\n", headers={"content-type": "text/plain"})
        if u == "https://careers.example.com/custom-map.xml":
            return _xml(xml)
        return httpx.Response(404)

    async with make_client(handler) as client:
        urls, new = await sitemap.discover(SM_BOARD, client)
    assert new == "https://careers.example.com/custom-map.xml"
    assert len(urls) == 3


async def test_sitemap_monitor_sends_crawler_user_agent(fixture_text, make_client):
    seen = []

    def handler(req):
        seen.append(req.headers["user-agent"])
        return _xml(fixture_text("sitemap_urlset_synthetic.xml"))

    async with make_client(handler) as client:
        await sitemap.discover(SM_BOARD, client)
    assert seen[0] == "jobseek-crawler (+https://jseek.co/)"
