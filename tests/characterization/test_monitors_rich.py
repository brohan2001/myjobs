"""Characterization of rich API monitors: greenhouse, lever, ashby.

Each test drives the real ``discover`` through ``httpx.MockTransport`` and pins
today's output. Do not "fix" expectations here; change them only with a
deliberate behavior change.
"""

from __future__ import annotations

import copy

import httpx
import pytest

from src.core.monitors import BoardGoneError, DiscoveredJob, ashby, greenhouse, lever
from src.shared.http_retry import PaginationFetchError

# --------------------------------------------------------------------- greenhouse


async def test_greenhouse_recorded_fixture(fixture_json, make_client):
    payload = fixture_json("greenhouse_anthropic_trimmed.json")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await greenhouse.discover({"board_url": "https://boards.greenhouse.io/anthropic"}, client)

    assert len(seen) == 1
    assert str(seen[0].url) == "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"
    assert all(isinstance(j, DiscoveredJob) for j in jobs)
    assert len(jobs) == 5
    assert [j.url for j in jobs] == [
        "https://job-boards.greenhouse.io/anthropic/jobs/5165641008",
        "https://job-boards.greenhouse.io/anthropic/jobs/5161980008",
        "https://job-boards.greenhouse.io/anthropic/jobs/5161988008",
        "https://job-boards.greenhouse.io/anthropic/jobs/5165651008",
        "https://job-boards.greenhouse.io/anthropic/jobs/5165670008",
    ]
    first = jobs[0]
    assert first.title == "Account Executive, Beneficial Deployments (French Speaking)"
    # primary location first, then offices, de-duplicated
    assert first.locations == ["Dublin, IE", "London, UK"]
    assert jobs[1].locations == ["London, UK", "Dublin, IE"]
    assert first.date_posted == "2026-03-26T06:01:22-04:00"
    assert first.language == "en"
    assert first.metadata == {"departments": ["Sales"], "requisition_id": "PIP-261459"}
    assert first.description and first.description.lstrip().startswith(("&lt;", "<"))
    assert first.employment_type is None and first.base_salary is None


async def test_greenhouse_token_from_metadata_and_skips_urlless(make_client):
    def handler(req):
        assert "/boards/tok-1/jobs" in req.url.path
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {"title": "No url"},
                    {"absolute_url": "https://x/1", "title": "T", "location": {"name": "A"},
                     "offices": [{"name": "A"}, {"name": None}, {"name": "B"}],
                     "content": 'Hi <a>Read more</a> <a href="/x">Read more</a>'},
                ]
            },
        )

    async with make_client(handler) as client:
        jobs = await greenhouse.discover({"board_url": "x", "metadata": {"token": "tok-1"}}, client)
    assert len(jobs) == 1
    assert jobs[0].locations == ["A", "B"]
    # stray href-less toggle removed, real link kept
    assert jobs[0].description == 'Hi  <a href="/x">Read more</a>'
    assert jobs[0].metadata is None


async def test_greenhouse_404_is_board_gone(make_client):
    async with make_client(lambda r: httpx.Response(404)) as client:
        with pytest.raises(BoardGoneError):
            await greenhouse.discover({"board_url": "https://boards.greenhouse.io/gone"}, client)


async def test_greenhouse_500_raises_http_status_error_no_retry(make_client):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500)

    async with make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await greenhouse.discover({"board_url": "https://boards.greenhouse.io/x"}, client)
    assert len(calls) == 1


def test_greenhouse_token_parsing():
    f = greenhouse._token_from_url
    assert f("https://boards.greenhouse.io/acme") == "acme"
    assert f("https://boards.greenhouse.io/embed/job_board?for=acme") == "acme"
    assert f("https://job-boards.greenhouse.io/acme/jobs/1") == "acme"
    assert f("https://boards-api.greenhouse.io/v1/boards/acme/jobs") == "acme"
    assert f("https://example.com/acme") is None


# --------------------------------------------------------------------------- lever


async def test_lever_recorded_fixture(fixture_json, make_client):
    payload = fixture_json("lever_wealthfront_trimmed.json")
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await lever.discover({"board_url": "https://jobs.lever.co/wealthfront"}, client)

    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.lever.co/v0/postings/wealthfront?limit=100&skip=0"
    assert seen[0].headers["accept"] == "application/json"
    assert [j.title for j in jobs] == [
        "Android Engineer", "Backend Engineer", "Capital Markets Paralegal", "Corporate Counsel",
    ]
    assert jobs[0].url == "https://jobs.lever.co/wealthfront/78d6f6d5-1f08-4d5d-87be-c4250567bfb5"
    assert jobs[0].locations == [
        "Palo Alto, CA", "Seattle, WA", "San Francisco, CA", "New York City, NY",
    ]
    assert jobs[0].employment_type == "Full-time"
    assert jobs[0].job_location_type == "hybrid"
    assert jobs[2].job_location_type == "remote"
    assert jobs[0].metadata == {
        "team": "Engineering - Android",
        "department": "Engineering",
        "id": "78d6f6d5-1f08-4d5d-87be-c4250567bfb5",
    }
    # description = description + one <h3>/<ul> block per list + additional
    assert jobs[0].description.count("<h3>") == 3
    assert jobs[0].base_salary is None


async def test_lever_salary_and_single_location(make_client):
    def handler(req):
        return httpx.Response(
            200,
            json=[{
                "hostedUrl": "https://jobs.lever.co/a/1", "text": "T", "id": "1",
                "categories": {"location": "Remote"},
                "salaryRange": {"currency": "USD", "min": 100, "max": 200, "interval": "per-year-salary"},
            }, {"text": "no url"}],
        )

    async with make_client(handler) as client:
        jobs = await lever.discover({"board_url": "https://jobs.lever.co/a"}, client)
    assert len(jobs) == 1
    assert jobs[0].locations == ["Remote"]
    assert jobs[0].base_salary == {"currency": "USD", "min": 100, "max": 200, "unit": "year"}


def _lever_pages(fixture_json, n_total: int):
    template = fixture_json("lever_wealthfront_trimmed.json")[0]
    out = []
    for i in range(n_total):
        p = copy.deepcopy(template)
        p["id"] = f"id-{i}"
        p["hostedUrl"] = f"https://jobs.lever.co/wealthfront/{i}"
        p["text"] = f"Job {i}"
        out.append(p)
    return out


async def test_lever_pagination_two_pages_then_stop(fixture_json, make_client, sleeps):
    postings = _lever_pages(fixture_json, 103)
    skips: list[int] = []

    def handler(req):
        skip = int(req.url.params["skip"])
        assert req.url.params["limit"] == "100"
        skips.append(skip)
        return httpx.Response(200, json=postings[skip : skip + 100])

    async with make_client(handler) as client:
        jobs = await lever.discover({"board_url": "https://jobs.lever.co/wealthfront"}, client)

    assert skips == [0, 100]  # short second page ends pagination
    assert len(jobs) == 103
    assert jobs[0].title == "Job 0" and jobs[-1].title == "Job 102"
    assert sleeps == [0.5]  # one inter-page pause


async def test_lever_exact_multiple_of_page_size_fetches_extra_empty_page(
    fixture_json, make_client, sleeps
):
    postings = _lever_pages(fixture_json, 100)
    skips = []

    def handler(req):
        skip = int(req.url.params["skip"])
        skips.append(skip)
        return httpx.Response(200, json=postings[skip : skip + 100])

    async with make_client(handler) as client:
        jobs = await lever.discover({"board_url": "https://jobs.lever.co/w"}, client)
    assert skips == [0, 100]
    assert len(jobs) == 100


async def test_lever_first_page_404_is_board_gone(make_client, sleeps):
    async with make_client(lambda r: httpx.Response(404)) as client:
        with pytest.raises(BoardGoneError):
            await lever.discover({"board_url": "https://jobs.lever.co/gone"}, client)


async def test_lever_second_page_failure_raises_not_truncates(fixture_json, make_client, sleeps):
    postings = _lever_pages(fixture_json, 150)
    calls = []

    def handler(req):
        skip = int(req.url.params["skip"])
        calls.append(skip)
        if skip == 0:
            return httpx.Response(200, json=postings[:100])
        return httpx.Response(503)

    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await lever.discover({"board_url": "https://jobs.lever.co/w"}, client)
    assert ei.value.last_status == 503
    assert calls == [0, 100, 100, 100]


async def test_lever_non_list_body_is_retried_then_raises(make_client, sleeps):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={})

    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await lever.discover({"board_url": "https://jobs.lever.co/w"}, client)
    assert len(calls) == 3
    assert ei.value.last_error == "ValueError"


async def test_lever_eu_region_uses_eu_api(make_client):
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(200, json=[])

    async with make_client(handler) as client:
        assert await lever.discover({"board_url": "https://jobs.eu.lever.co/acme"}, client) == []
    assert hosts == ["api.eu.lever.co"]


# --------------------------------------------------------------------------- ashby


async def test_ashby_synthetic_fixture(fixture_json, make_client):
    payload = fixture_json("ashby_posting_api_synthetic.json")
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await ashby.discover({"board_url": "https://jobs.ashbyhq.com/acme"}, client)

    assert str(seen[0].url) == (
        "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true"
    )
    # unlisted and URL-less postings are dropped
    assert [j.url for j in jobs] == [
        "https://jobs.ashbyhq.com/acme/aaaa0001",
        "https://jobs.ashbyhq.com/acme/aaaa0002",
    ]
    be, pd = jobs
    assert be.title == "Backend Engineer"
    # primary + secondary (dict or str), de-duplicated
    assert be.locations == ["San Francisco, CA", "Remote - US", "New York, NY"]
    assert be.employment_type == "FullTime"
    assert be.job_location_type == "hybrid"
    assert be.date_posted == "2026-05-01T00:00:00.000+00:00"
    assert be.description == "<p>Build backend systems.</p>"
    assert be.base_salary == {"currency": "USD", "min": 150000, "max": 200000, "unit": "year"}
    assert be.metadata == {"department": "Engineering", "team": "Platform", "id": "aaaa0001"}
    # no explicit location: falls back to address parts; plain description fallback
    assert pd.locations == ["Berlin, Germany"]
    assert pd.description == "Design things."
    assert pd.job_location_type == "remote"
    assert pd.employment_type == "Contract"
    assert pd.base_salary is None


async def test_ashby_404_is_board_gone(make_client):
    async with make_client(lambda r: httpx.Response(404)) as client:
        with pytest.raises(BoardGoneError):
            await ashby.discover({"board_url": "https://jobs.ashbyhq.com/gone"}, client)


@pytest.mark.xfail(
    reason="Ashby has no pagination: the posting API returns every job in one response "
    "(see ashby.discover), so there is no multi-page behavior to characterize.",
    strict=True,
)
async def test_ashby_pagination():
    raise AssertionError("ashby does not paginate")


async def test_orphaned_ashby_fixture_does_not_match_current_monitor(make_client):
    """tests/fixtures/ashby_synthetic.json uses a GraphQL ``jobBoard.jobPostings`` shape.

    The current monitor reads ``jobs[].jobUrl`` from the posting API, so the
    orphaned fixture yields zero jobs. Pinned so the mismatch is explicit.
    """
    import json
    from pathlib import Path

    old = json.loads((Path(__file__).parents[1] / "fixtures" / "ashby_synthetic.json").read_text())
    async with make_client(lambda r: httpx.Response(200, json=old)) as client:
        assert await ashby.discover({"board_url": "https://jobs.ashbyhq.com/ramp"}, client) == []
