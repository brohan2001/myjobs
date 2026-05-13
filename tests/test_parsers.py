"""Parser stability tests.

Each test class loads a static fixture file and runs the corresponding scraper's
fetch_jobs() with a mocked _request to verify that the field-extraction logic
(parsing) produces stable, correctly-typed output.

We test the parsing contract, not HTTP fetching — BaseScraper._request is mocked.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scrapers.base import BaseScraper
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.amazon import AmazonScraper
from src.scrapers.google import GoogleScraper
from src.scrapers.apple import AppleScraper

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# Required fields and their expected types for every job dict.
REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "external_id": str,
    "company_id":  int,
    "title":       str,
    "description": str,
    "location":    str,
    "url":         str,
    "ats_type":    str,
}
NULLABLE_FIELDS: dict[str, type] = {
    "posted_date": str,
    "posted_at":   str,
}

COMPANY_ID = 42


def _load_fixture(filename: str) -> object:
    path = FIXTURE_DIR / filename
    assert path.exists(), f"Fixture missing: {path}. Run: python scripts/capture_fixtures.py"
    return json.loads(path.read_text())


def _mock_response(data: object, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


def _assert_job_contract(jobs: list[dict], ats_type: str) -> None:
    """Shared assertion: all required fields present with correct types."""
    for i, job in enumerate(jobs):
        for field, expected_type in REQUIRED_FIELDS.items():
            assert field in job, f"job[{i}] missing required field '{field}'"
            assert isinstance(job[field], expected_type), (
                f"job[{i}]['{field}'] expected {expected_type.__name__}, "
                f"got {type(job[field]).__name__}: {job[field]!r}"
            )
        for field, expected_type in NULLABLE_FIELDS.items():
            assert field in job, f"job[{i}] missing nullable field '{field}'"
            assert job[field] is None or isinstance(job[field], expected_type), (
                f"job[{i}]['{field}'] must be str or None, "
                f"got {type(job[field]).__name__}: {job[field]!r}"
            )
        assert job["ats_type"] == ats_type, (
            f"job[{i}]['ats_type'] expected '{ats_type}', got '{job['ats_type']}'"
        )
        assert job["company_id"] == COMPANY_ID


# ── Greenhouse ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGreenhouseParser:
    COMPANY = {"name": "Anthropic", "slug": "anthropic", "ats_type": "greenhouse",
               "domain": "anthropic.com", "industry": "tech", "tier": 1}
    FIXTURE = "greenhouse_anthropic.json"

    @pytest.fixture
    def fixture_data(self):
        return _load_fixture(self.FIXTURE)

    @pytest.fixture
    def mock_request(self, fixture_data):
        resp = _mock_response(fixture_data)
        with patch.object(BaseScraper, "_request", new_callable=AsyncMock) as m:
            m.return_value = resp
            yield m

    async def test_returns_list_of_dicts(self, mock_request):
        async with GreenhouseScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    async def test_required_fields_present(self, mock_request, fixture_data):
        async with GreenhouseScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        # fixture has "jobs" list; assert we parsed at least as many as the fixture has
        assert len(jobs) == len(fixture_data.get("jobs", []))
        _assert_job_contract(jobs, "greenhouse")

    async def test_external_id_is_nonempty_string(self, mock_request):
        async with GreenhouseScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["external_id"] != "", "external_id must not be empty"

    async def test_remote_is_binary_int(self, mock_request):
        async with GreenhouseScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["remote"] in (0, 1), f"remote must be 0 or 1, got {job['remote']!r}"

    async def test_url_starts_with_http(self, mock_request):
        async with GreenhouseScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            if job["url"]:
                assert job["url"].startswith("http"), f"url must start with http: {job['url']!r}"


# ── Lever ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLeverParser:
    COMPANY = {"name": "Wealthfront", "slug": "wealthfront", "ats_type": "lever",
               "domain": "wealthfront.com", "industry": "fintech", "tier": 2}
    FIXTURE = "lever_wealthfront.json"

    @pytest.fixture
    def fixture_data(self):
        return _load_fixture(self.FIXTURE)

    @pytest.fixture
    def mock_request(self, fixture_data):
        # First call returns fixture (list of jobs < 50 → stops pagination naturally).
        # Second call returns empty list as safety net.
        resp1 = _mock_response(fixture_data)
        resp2 = _mock_response([])
        with patch.object(BaseScraper, "_request", new_callable=AsyncMock) as m:
            m.side_effect = [resp1, resp2]
            yield m

    async def test_returns_list_of_dicts(self, mock_request):
        async with LeverScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    async def test_required_fields_present(self, mock_request, fixture_data):
        async with LeverScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert len(jobs) == len(fixture_data)
        _assert_job_contract(jobs, "lever")

    async def test_external_id_is_nonempty_string(self, mock_request):
        async with LeverScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["external_id"] != ""

    async def test_remote_is_binary_int(self, mock_request):
        async with LeverScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["remote"] in (0, 1)

    async def test_url_starts_with_http(self, mock_request):
        async with LeverScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            if job["url"]:
                assert job["url"].startswith("http")


# ── Workday ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestWorkdayParser:
    COMPANY = {
        "name": "Cisco", "slug": "cisco", "ats_type": "workday",
        "workday_host": "cisco.wd5.myworkdayjobs.com",
        "workday_slug": "Cisco", "workday_board": "Cisco",
        "domain": "cisco.com", "industry": "tech", "tier": 1,
    }
    FIXTURE = "workday_synthetic.json"

    @pytest.fixture
    def fixture_data(self):
        return _load_fixture(self.FIXTURE)

    @pytest.fixture
    def mock_request(self, fixture_data):
        resp1 = _mock_response(fixture_data)
        resp2 = _mock_response({"jobPostings": [], "total": 0})
        with patch.object(BaseScraper, "_request", new_callable=AsyncMock) as m:
            m.side_effect = [resp1, resp2]
            yield m

    async def test_returns_list_of_dicts(self, mock_request):
        async with WorkdayScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    async def test_required_fields_present(self, mock_request, fixture_data):
        async with WorkdayScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert len(jobs) == len(fixture_data["jobPostings"])
        _assert_job_contract(jobs, "workday")

    async def test_description_is_empty_string(self, mock_request):
        # Workday descriptions are enriched post-scrape; the scraper returns "".
        async with WorkdayScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["description"] == "", (
                "Workday scraper must return empty description (enriched later)"
            )

    async def test_remote_is_binary_int(self, mock_request):
        async with WorkdayScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["remote"] in (0, 1)

    async def test_url_starts_with_http(self, mock_request):
        async with WorkdayScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["url"].startswith("http")


# ── Amazon ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAmazonParser:
    COMPANY = {"name": "Amazon", "slug": "amazon", "ats_type": "amazon",
               "domain": "amazon.jobs", "industry": "tech", "tier": 1}
    FIXTURE = "amazon_amazon.json"

    @pytest.fixture
    def fixture_data(self):
        return _load_fixture(self.FIXTURE)

    @pytest.fixture
    def mock_request(self, fixture_data):
        # Fixture uses new Amazon API format: hits=<int total>, jobs=[...].
        # Set hits equal to len(jobs) so offset >= total stops pagination after one page.
        data = dict(fixture_data)
        job_list = data.get("jobs") if isinstance(data.get("hits"), int) else data.get("hits", [])
        n = len(job_list) if isinstance(job_list, list) else 0
        data["hits"] = n  # make total == page size → stops after first page
        resp = _mock_response(data)
        with patch.object(BaseScraper, "_request", new_callable=AsyncMock) as m:
            m.return_value = resp
            yield m

    async def test_returns_list_of_dicts(self, mock_request):
        async with AmazonScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    async def test_required_fields_present(self, mock_request, fixture_data):
        async with AmazonScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        _assert_job_contract(jobs, "amazon")

    async def test_external_id_is_nonempty_string(self, mock_request):
        async with AmazonScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["external_id"] != ""

    async def test_remote_is_binary_int(self, mock_request):
        async with AmazonScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["remote"] in (0, 1)

    async def test_url_starts_with_http(self, mock_request):
        async with AmazonScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["url"].startswith("http")


# ── Google ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGoogleParser:
    COMPANY = {"name": "Google", "slug": "google", "ats_type": "google",
               "domain": "google.com", "industry": "tech", "tier": 1}
    FIXTURE = "google_synthetic.json"

    @pytest.fixture
    def fixture_data(self):
        return _load_fixture(self.FIXTURE)

    @pytest.fixture
    def mock_request(self, fixture_data):
        # No nextPageToken in fixture → pagination stops after one page.
        resp = _mock_response(fixture_data)
        with patch.object(BaseScraper, "_request", new_callable=AsyncMock) as m:
            m.return_value = resp
            yield m

    async def test_returns_list_of_dicts(self, mock_request):
        async with GoogleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    async def test_required_fields_present(self, mock_request, fixture_data):
        async with GoogleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert len(jobs) == len(fixture_data["jobs"])
        _assert_job_contract(jobs, "google")

    async def test_external_id_is_nonempty_string(self, mock_request):
        async with GoogleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["external_id"] != ""

    async def test_remote_is_binary_int(self, mock_request):
        async with GoogleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["remote"] in (0, 1)

    async def test_url_starts_with_http(self, mock_request):
        async with GoogleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["url"].startswith("http")


# ── Apple ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAppleParser:
    COMPANY = {"name": "Apple", "slug": "apple", "ats_type": "apple",
               "domain": "apple.com", "industry": "tech", "tier": 1}
    FIXTURE = "apple_synthetic.json"

    @pytest.fixture
    def fixture_data(self):
        return _load_fixture(self.FIXTURE)

    @pytest.fixture
    def mock_request(self, fixture_data):
        # totalRecords == len(searchResults) → no second page fetched.
        resp = _mock_response(fixture_data)
        with patch.object(BaseScraper, "_request", new_callable=AsyncMock) as m:
            m.return_value = resp
            yield m

    async def test_returns_list_of_dicts(self, mock_request):
        async with AppleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    async def test_required_fields_present(self, mock_request, fixture_data):
        async with AppleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        assert len(jobs) == len(fixture_data["searchResults"])
        _assert_job_contract(jobs, "apple")

    async def test_external_id_is_nonempty_string(self, mock_request):
        async with AppleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["external_id"] != ""

    async def test_remote_is_binary_int(self, mock_request):
        async with AppleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["remote"] in (0, 1)

    async def test_url_starts_with_http(self, mock_request):
        async with AppleScraper() as scraper:
            jobs = await scraper.fetch_jobs(self.COMPANY, COMPANY_ID)
        for job in jobs:
            assert job["url"].startswith("http")
