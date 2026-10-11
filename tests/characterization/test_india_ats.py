"""Characterization tests for Indian ATS monitors: Keka, greytHR, and Zoho Recruit.

Tests run offline with no network access via httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from src.core.monitors import DiscoveredJob, greythr, keka, zoho_recruit


# ── Keka Hire ─────────────────────────────────────────────────────────────


async def test_keka_discover_fixture(fixture_json, make_client):
    payload = fixture_json("keka_gokwik.json")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await keka.discover(
            {"board_url": "https://gokwik.keka.com/careers"}, client
        )

    assert len(seen) == 1
    assert (
        str(seen[0].url)
        == "https://gokwik.keka.com/careers/api/jobs/default/active"
    )
    assert len(jobs) == 5
    assert all(isinstance(j, DiscoveredJob) for j in jobs)

    # Job URLs
    assert [j.url for j in jobs] == [
        "https://gokwik.keka.com/careers/jobdetails/164856",
        "https://gokwik.keka.com/careers/jobdetails/164629",
        "https://gokwik.keka.com/careers/jobdetails/164622",
        "https://gokwik.keka.com/careers/jobdetails/164620",
        "https://gokwik.keka.com/careers/jobdetails/164260",
    ]

    # Titles
    assert [j.title for j in jobs] == [
        "Customer Success Manager",
        "Senior Associate - Business Operations",
        "Associate Customer Success Manager",
        "Customer Success Manager",
        "Assistant Manager - Partnerships",
    ]

    # Locations
    assert jobs[0].locations == ["Gurugram, HR, IN"]
    assert jobs[1].locations == ["Gurugram, HR, IN"]
    assert jobs[2].locations == ["Mumbai, MH, IN"]
    assert jobs[3].locations == ["Bangalore, KA, IN"]

    # Salary (first job)
    assert jobs[0].base_salary == {
        "currency": "INR",
        "min": 1200000.0,
        "max": 1500000.0,
        "unit": "year",
    }
    # Salary (second job)
    assert jobs[1].base_salary == {
        "currency": "INR",
        "min": 300000.0,
        "max": 500000.0,
        "unit": "year",
    }

    # Description and fields
    assert jobs[0].description and jobs[0].description.startswith(("<p>", "<h2>", "<"))
    assert jobs[0].employment_type == "full_time"
    assert jobs[0].date_posted == "2026-10-09T10:08:48.583Z"
    assert jobs[0].metadata == {
        "req_id": "GK-REQ-00648",
        "department": "Merchant Success",
    }
    assert jobs[0].extras and jobs[0].extras.get("experience") == "3 - 6 Years"


async def test_keka_discover_empty(make_client):
    async with make_client(lambda r: httpx.Response(200, json=[])) as client:
        jobs = await keka.discover(
            {"board_url": "https://gokwik.keka.com/careers"}, client
        )
    assert jobs == []


async def test_keka_tenant_from_metadata(fixture_json, make_client):
    payload = fixture_json("keka_gokwik.json")

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "custom-tenant.keka.com"
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await keka.discover(
            {
                "board_url": "https://careers.example.com",
                "metadata": {"tenant": "custom-tenant"},
            },
            client,
        )
    assert len(jobs) == 5
    assert jobs[0].url == "https://custom-tenant.keka.com/careers/jobdetails/164856"


def test_keka_invalid_url_raises(make_client):
    with pytest.raises(ValueError, match="Cannot derive Keka tenant"):
        import asyncio
        asyncio.run(keka.discover({"board_url": "https://notkeka.com"}, None))


async def test_keka_can_handle(make_client):
    # Positive without client
    assert await keka.can_handle("https://gokwik.keka.com/careers") == {"tenant": "gokwik"}
    assert await keka.can_handle("gokwik.keka.com") == {"tenant": "gokwik"}

    # Positive with client
    async with make_client(lambda r: httpx.Response(200, json=[{"id": 1}])) as client:
        assert await keka.can_handle("https://gokwik.keka.com/careers", client) == {"tenant": "gokwik"}

    # Negative without client
    assert await keka.can_handle("https://example.com/careers") is None
    assert await keka.can_handle("https://www.keka.com/careers") is None

    # Negative with client (404)
    async with make_client(lambda r: httpx.Response(404)) as client:
        assert await keka.can_handle("https://gokwik.keka.com/careers", client) is None

    # Negative with client (invalid data shape)
    async with make_client(lambda r: httpx.Response(200, json={"error": "not found"})) as client:
        assert await keka.can_handle("https://gokwik.keka.com/careers", client) is None


async def test_keka_retry_503_then_200(fixture_json, make_client, sleeps):
    calls = []
    payload = fixture_json("keka_gokwik.json")

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await keka.discover(
            {"board_url": "https://gokwik.keka.com/careers"}, client
        )

    assert len(calls) == 2
    assert len(jobs) == 5
    assert len(sleeps) == 1


# ── greytHR Hire ──────────────────────────────────────────────────────────


async def test_greythr_discover_fixture(fixture_json, make_client):
    payload = fixture_json("greythr_greytip.json")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await greythr.discover(
            {"board_url": "https://greytip.greythr.com/hire/jobs"}, client
        )

    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert (
        str(seen[0].url)
        == "https://greytip.greythr.com/hire/api/career/published_jobs/"
    )
    assert len(jobs) == 5
    assert all(isinstance(j, DiscoveredJob) for j in jobs)

    # Job URLs
    assert [j.url for j in jobs] == [
        "https://greytip.greythr.com/hire/jobs/associate-product-manager-817",
        "https://greytip.greythr.com/hire/jobs/program-manager-gtm",
        "https://greytip.greythr.com/hire/jobs/managerassociate-manager-channel-sales",
        "https://greytip.greythr.com/hire/jobs/executive-inside-sales-094",
        "https://greytip.greythr.com/hire/jobs/associate-product-manager-896",
    ]

    # Titles
    assert [j.title for j in jobs] == [
        "Associate Product Manager",
        "Program Manager - GTM",
        "Manager/Associate Manager-Channel Sales",
        "Executive-Inside Sales",
        "Associate Product Manager - Payroll domain",
    ]

    # Locations
    assert jobs[0].locations is None  # internal location ids ("4") are dropped
    assert jobs[2].locations == ["1"]

    # Descriptions and fields
    assert jobs[0].description and jobs[0].description.startswith(("<p>", "<h3>", "<"))
    assert jobs[0].employment_type == "Full-time"
    assert jobs[0].date_posted == "2026-10-06T07:36:48.332873Z"
    assert jobs[0].metadata == {
        "req_id": "1393",
        "id": "7d208252-08e6-485f-aeb8-8dc149cce3be",
    }
    assert jobs[0].extras == {
        "min_exp": 36,
        "max_exp": 60,
        "experience_units": "years",
    }


async def test_greythr_discover_empty(make_client):
    async with make_client(lambda r: httpx.Response(200, json={"data": []})) as client:
        jobs = await greythr.discover(
            {"board_url": "https://greytip.greythr.com/hire/jobs"}, client
        )
    assert jobs == []


async def test_greythr_tenant_from_metadata(fixture_json, make_client):
    payload = fixture_json("greythr_greytip.json")

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "custom-tenant.greythr.com"
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await greythr.discover(
            {
                "board_url": "https://careers.example.com",
                "metadata": {"tenant": "custom-tenant"},
            },
            client,
        )
    assert len(jobs) == 5
    assert jobs[0].url == "https://custom-tenant.greythr.com/hire/jobs/associate-product-manager-817"


def test_greythr_invalid_url_raises(make_client):
    with pytest.raises(ValueError, match="Cannot derive greytHR tenant"):
        import asyncio
        asyncio.run(greythr.discover({"board_url": "https://notgreythr.com"}, None))


async def test_greythr_can_handle(make_client):
    # Positive without client
    assert await greythr.can_handle("https://greytip.greythr.com/hire/jobs") == {"tenant": "greytip"}
    assert await greythr.can_handle("greytip.greythr.com") == {"tenant": "greytip"}

    # Positive with client
    async with make_client(lambda r: httpx.Response(200, json={"data": []})) as client:
        assert await greythr.can_handle("https://greytip.greythr.com/hire/jobs", client) == {"tenant": "greytip"}

    # Negative without client
    assert await greythr.can_handle("https://example.com/jobs") is None
    assert await greythr.can_handle("https://www.greythr.com/jobs") is None

    # Negative with client (404)
    async with make_client(lambda r: httpx.Response(404)) as client:
        assert await greythr.can_handle("https://greytip.greythr.com/hire/jobs", client) is None

    # Negative with client (invalid response)
    async with make_client(lambda r: httpx.Response(200, json={"data": "invalid"})) as client:
        assert await greythr.can_handle("https://greytip.greythr.com/hire/jobs", client) is None


async def test_greythr_retry_503_then_200(fixture_json, make_client, sleeps):
    calls = []
    payload = fixture_json("greythr_greytip.json")

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        jobs = await greythr.discover(
            {"board_url": "https://greytip.greythr.com/hire/jobs"}, client
        )

    assert len(calls) == 2
    assert len(jobs) == 5
    assert len(sleeps) == 1


# ── Zoho Recruit ──────────────────────────────────────────────────────────


async def test_zoho_recruit_discover_fixture(fixture_text, make_client):
    html_content = fixture_text("zoho_increff.html")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, text=html_content)

    async with make_client(handler) as client:
        jobs = await zoho_recruit.discover(
            {"board_url": "https://increff.zohorecruit.com/jobs/Careers"},
            client,
        )

    assert len(seen) == 1
    assert str(seen[0].url) == "https://increff.zohorecruit.com/jobs/Careers"
    assert len(jobs) == 5
    assert all(isinstance(j, DiscoveredJob) for j in jobs)

    # Job URLs
    assert [j.url for j in jobs] == [
        "https://increff.zohorecruit.com/jobs/Careers/603317000010913079/Executive-Finance",
        "https://increff.zohorecruit.com/jobs/Careers/603317000013907393/Software-Development-Engineer-II-SDE-II",
        "https://increff.zohorecruit.com/jobs/Careers/603317000012032180/SeniorExecutive-Operations",
        "https://increff.zohorecruit.com/jobs/Careers/603317000008736435/Technical-Product-Manager",
        "https://increff.zohorecruit.com/jobs/Careers/603317000009394150/Senior-Integration-Support-Engineer",
    ]

    # Titles
    assert [j.title for j in jobs] == [
        "Executive - Finance",
        "Software Development Engineer II (SDE-II)",
        "Senior/Executive - Operations",
        "Technical Product Manager",
        "Senior Integration Support Engineer",
    ]

    # Locations
    assert jobs[0].locations == ["Bangalore South, India"]
    assert jobs[1].locations == ["Bangalore South, IN"]
    assert jobs[2].locations == ["India"]  # NA is filtered out
    assert jobs[3].locations == ["Bangalore, India"]

    # Other fields
    assert jobs[0].employment_type == "Full time"
    assert jobs[0].metadata == {"id": "603317000010913079"}
    assert jobs[0].extras == {"experience": "1-3 year"}


async def test_zoho_recruit_discover_empty(make_client):
    # Empty HTML without input tag
    async with make_client(lambda r: httpx.Response(200, text="<html><body></body></html>")) as client:
        jobs = await zoho_recruit.discover(
            {"board_url": "https://increff.zohorecruit.com/jobs/Careers"}, client
        )
    assert jobs == []

    # HTML with empty input value
    empty_input_html = '<html><body><input type="hidden" id="jobs" value="[]"></body></html>'
    async with make_client(lambda r: httpx.Response(200, text=empty_input_html)) as client:
        jobs = await zoho_recruit.discover(
            {"board_url": "https://increff.zohorecruit.com/jobs/Careers"}, client
        )
    assert jobs == []


async def test_zoho_recruit_tenant_from_metadata(fixture_text, make_client):
    html_content = fixture_text("zoho_increff.html")

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "custom-tenant.zohorecruit.com"
        return httpx.Response(200, text=html_content)

    async with make_client(handler) as client:
        jobs = await zoho_recruit.discover(
            {
                "board_url": "https://careers.example.com",
                "metadata": {"tenant": "custom-tenant"},
            },
            client,
        )
    assert len(jobs) == 5
    assert jobs[0].url == "https://custom-tenant.zohorecruit.com/jobs/Careers/603317000010913079/Executive-Finance"


async def test_zoho_recruit_in_domain(fixture_text, make_client):
    html_content = fixture_text("zoho_increff.html")

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "increff.zohorecruit.in"
        return httpx.Response(200, text=html_content)

    async with make_client(handler) as client:
        jobs = await zoho_recruit.discover(
            {"board_url": "https://increff.zohorecruit.in/jobs/Careers"}, client
        )
    assert len(jobs) == 5
    assert jobs[0].url.startswith("https://increff.zohorecruit.in/jobs/Careers/603317000010913079/")


def test_zoho_recruit_invalid_url_raises(make_client):
    with pytest.raises(ValueError, match="Cannot derive Zoho Recruit tenant"):
        import asyncio
        asyncio.run(zoho_recruit.discover({"board_url": "https://notzoho.com"}, None))


async def test_zoho_recruit_can_handle(make_client):
    # Positive without client
    assert await zoho_recruit.can_handle("https://increff.zohorecruit.com/jobs/Careers") == {"tenant": "increff"}
    assert await zoho_recruit.can_handle("https://increff.zohorecruit.in/jobs/Careers") == {"tenant": "increff"}
    assert await zoho_recruit.can_handle("increff.zohorecruit.com") == {"tenant": "increff"}

    # Positive with client
    async with make_client(lambda r: httpx.Response(200, text='<input id="jobs" value="[]">')) as client:
        assert await zoho_recruit.can_handle("https://increff.zohorecruit.com/jobs/Careers", client) == {"tenant": "increff"}

    # Negative without client
    assert await zoho_recruit.can_handle("https://example.com/Careers") is None
    assert await zoho_recruit.can_handle("https://www.zohorecruit.com/jobs/Careers") is None

    # Negative with client (404)
    async with make_client(lambda r: httpx.Response(404)) as client:
        assert await zoho_recruit.can_handle("https://increff.zohorecruit.com/jobs/Careers", client) is None

    # Negative with client (no jobs input)
    async with make_client(lambda r: httpx.Response(200, text="<html><body>no jobs here</body></html>")) as client:
        assert await zoho_recruit.can_handle("https://increff.zohorecruit.com/jobs/Careers", client) is None


async def test_zoho_recruit_retry_503_then_200(fixture_text, make_client, sleeps):
    calls = []
    html_content = fixture_text("zoho_increff.html")

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, text=html_content)

    async with make_client(handler) as client:
        jobs = await zoho_recruit.discover(
            {"board_url": "https://increff.zohorecruit.com/jobs/Careers"},
            client,
        )

    assert len(calls) == 2
    assert len(jobs) == 5
    assert len(sleeps) == 1
