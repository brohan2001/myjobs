"""Characterization of the json-ld and nextdata scrapers (page -> JobContent)."""

from __future__ import annotations

import httpx
import pytest

from src.core import scrapers
from src.core.scrapers import JobContent, jsonld, nextdata

JOB_URL = "https://careers.example.com/jobs/1"


# -------------------------------------------------------------------------- json-ld


async def test_jsonld_scrape_synthetic_fixture(fixture_text, make_client):
    html = fixture_text("jsonld_jobposting_synthetic.html")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(200, text=html)

    async with make_client(handler) as client:
        content = await jsonld.scrape(JOB_URL, {}, client)

    assert seen == [JOB_URL]
    assert isinstance(content, JobContent)
    assert content.title == "Senior Data Engineer"
    assert content.description == "<p>Build pipelines.</p>"
    assert content.locations == ["Raleigh, NC, US", "Remote (US)"]
    assert content.employment_type == "FULL_TIME"
    assert content.job_location_type == "TELECOMMUTE"
    assert content.date_posted == "2026-05-02"
    assert content.base_salary == {"currency": "USD", "min": 140000, "max": 180000, "unit": "year"}
    assert content.extras == {
        "skills": ["Python, SQL"],
        "qualifications": ["BS in CS"],
        "valid_through": "2026-07-01",
    }
    assert content.language is None and content.metadata is None


def test_jsonld_graph_pascalcase_and_scalar_salary():
    html = (
        '<script type="application/ld+json">{"@graph":[{"@type":"WebSite"},'
        '{"@type":["Thing","JobPosting"],"Title":"Dev","Description":"d",'
        '"jobLocation":{"name":"Paris"},'
        '"baseSalary":{"currency":"EUR","value":50000,"unitText":"YEAR"}}]}</script>'
    )
    content = jsonld.parse_html(html)
    assert content.title == "Dev"
    assert content.locations == ["Paris"]
    assert content.base_salary == {"currency": "EUR", "min": 50000, "max": 50000, "unit": "year"}


def test_jsonld_control_chars_in_strings_are_tolerated():
    html = (
        '<script type="application/ld+json">{"@type":"JobPosting","title":"A\nB"}</script>'
    )
    assert jsonld.parse_html(html).title == "A B"  # whitespace normalised (upstream re-sync 2026-10-15)


def test_jsonld_no_posting_gives_empty_content():
    assert jsonld.parse_html("<html></html>") == JobContent()


def test_jsonld_can_handle_needs_half_of_pages(fixture_text):
    good = fixture_text("jsonld_jobposting_synthetic.html")
    assert jsonld.can_handle([good, "<html/>"]) == {}
    assert jsonld.can_handle([good, "<html/>", "<html/>"]) is None
    assert jsonld.can_handle([]) is None


async def test_jsonld_403_retried_once_then_succeeds(fixture_text, make_client, sleeps):
    html = fixture_text("jsonld_jobposting_synthetic.html")
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(403) if len(calls) == 1 else httpx.Response(200, text=html)

    async with make_client(handler) as client:
        content = await jsonld.scrape(JOB_URL, {}, client)
    assert content.title == "Senior Data Engineer"
    assert len(calls) == 2


async def test_jsonld_persistent_403_raises(make_client, sleeps):
    async with make_client(lambda r: httpx.Response(403)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await jsonld.scrape(JOB_URL, {}, client)


async def test_jsonld_404_raises(make_client):
    async with make_client(lambda r: httpx.Response(404)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await jsonld.scrape(JOB_URL, {}, client)


# ------------------------------------------------------------------------- nextdata

NEXT_CONFIG = {
    "path": "props.pageProps.job",
    "fields": {
        "title": "title",
        "description": "descriptionHtml",
        "locations": "locations[].name",
        "employment_type": "type",
        "metadata.team": "department.name",
    },
}


async def test_nextdata_scrape_synthetic_fixture(fixture_text, make_client):
    html = fixture_text("nextdata_job_synthetic.html")
    async with make_client(lambda r: httpx.Response(200, text=html)) as client:
        content = await nextdata.scrape(JOB_URL, NEXT_CONFIG, client)

    assert content.title == "Platform Engineer"
    assert content.description == "<p>Run the platform.</p>"
    assert content.locations == ["Durham, NC", "Remote"]
    assert content.employment_type == "Full-time"
    assert content.metadata == {"team": "Infrastructure"}
    assert content.base_salary is None and content.extras is None


def test_nextdata_parse_html_injects_script_id_and_does_not_mutate_config(fixture_text):
    cfg = dict(NEXT_CONFIG)
    assert nextdata.parse_html(fixture_text("nextdata_job_synthetic.html"), cfg).title == "Platform Engineer"
    assert "script_id" not in cfg


def test_nextdata_without_fields_or_data_is_empty(fixture_text):
    assert nextdata.parse_html(fixture_text("nextdata_job_synthetic.html"), {}) == JobContent()
    assert nextdata.parse_html("<html></html>", NEXT_CONFIG) == JobContent()


def test_nextdata_can_handle_auto_detects_path_and_fields(fixture_text):
    cfg = nextdata.can_handle([fixture_text("nextdata_job_synthetic.html")])
    assert cfg is not None
    assert cfg["path"] == "props.pageProps.job"
    assert "title" in cfg["fields"]
    assert nextdata.can_handle(["<html></html>"]) is None


async def test_nextdata_non_200_returns_empty_content(make_client):
    async with make_client(lambda r: httpx.Response(500)) as client:
        assert await nextdata.scrape(JOB_URL, NEXT_CONFIG, client) == JobContent()


def test_scraper_registry_contains_jsonld_and_nextdata():
    assert "json-ld" in scrapers._REGISTRY and "nextdata" in scrapers._REGISTRY
