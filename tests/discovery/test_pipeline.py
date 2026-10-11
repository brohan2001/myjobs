"""Tests for src/discovery/pipeline.py."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from src.core.monitor import MonitorResult
from src.discovery import pipeline
from src.discovery.pipeline import (
    Candidate,
    Outcome,
    _fetch_robots,
    domain_of,
    evaluate,
    existing_index,
    is_blocked_host,
    load_candidates,
    outcome_dict,
    registry_rows,
    robots_allows,
    run,
    slugify,
    unique_slug,
)
from src.workspace.career_discover import CareerPageCandidate


from tests.discovery.conftest import NetworkAccessError


def test_network_access_blocked() -> None:
    import socket

    s = socket.socket()
    with pytest.raises(NetworkAccessError, match="network access is forbidden"):
        s.connect(("1.1.1.1", 80))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestPureHelpers:
    @pytest.mark.parametrize(
        ("raw_url", "expected"),
        [
            # Scheme-less input
            ("example.com", "example.com"),
            ("example.com/careers", "example.com"),
            ("sub.example.com", "sub.example.com"),
            ("sub.example.com/careers/jobs", "sub.example.com"),
            # WWW stripping
            ("https://www.example.com", "example.com"),
            ("http://www.razorpay.com/jobs", "razorpay.com"),
            ("www.naukri.com", "naukri.com"),
            ("https://www.foo.bar.co.in/path", "foo.bar.co.in"),
            ("http://www.com", "com"),
            # Empty input
            ("", ""),
            # Mixed-case and uppercase
            ("HTTPS://WWW.EXAMPLE.COM", "example.com"),
            ("EXAMPLE.COM", "example.com"),
            # Port numbers
            ("http://www.example.com:8080/foo", "example.com"),
            ("example.com:3000", "example.com"),
        ],
    )
    def test_domain_of(self, raw_url: str, expected: str) -> None:
        assert domain_of(raw_url) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Acme Corp", "acme-corp"),
            ("Google", "google"),
            ("Tata Consultancy Services", "tata-consultancy-services"),
            ("Acme, Inc. & Sons! (Pvt)", "acme-inc-sons-pvt"),
            ("100x Engineers", "100x-engineers"),
            ("---Leading & Trailing---", "leading-trailing"),
            ("", "company"),
            ("   ", "company"),
            ("---", "company"),
            ("!@#$%^&*()", "company"),
        ],
    )
    def test_slugify(self, name: str, expected: str) -> None:
        assert slugify(name) == expected

    def test_unique_slug_no_collision(self) -> None:
        assert unique_slug("Acme", set()) == "acme"
        assert unique_slug("Acme", {"other-company"}) == "acme"

    def test_unique_slug_with_collisions(self) -> None:
        taken = {"acme"}
        assert unique_slug("Acme", taken) == "acme-2"

        taken.add("acme-2")
        assert unique_slug("Acme", taken) == "acme-3"

        taken.add("acme-3")
        assert unique_slug("Acme", taken) == "acme-4"

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            # Blocked hosts from brief and constants
            ("naukri.com", True),
            ("https://naukri.com/jobs", True),
            ("http://www.naukri.com", True),
            ("www.linkedin.com", True),
            ("https://www.linkedin.com/jobs", True),
            ("https://linkedin.com", True),
            ("sub.indeed.co.in", True),
            ("https://sub.indeed.co.in/viewjob", True),
            ("https://indeed.com", True),
            ("https://glassdoor.com", True),
            ("https://glassdoor.co.in", True),
            ("https://foundit.in", True),
            ("https://monsterindia.com", True),
            ("https://instahyre.com", True),
            ("https://cutshort.io", True),
            ("https://wellfound.com", True),
            ("https://angel.co", True),
            ("https://shine.com", True),
            ("https://timesjobs.com", True),
            ("https://iimjobs.com", True),
            ("https://hirist.tech", True),
            ("https://apna.co", True),
            # Allowed hosts
            ("careers.razorpay.com", False),
            ("https://careers.razorpay.com", False),
            ("https://razorpay.com", False),
            ("https://notlinkedin.com", False),
            ("https://linkedin.com.legit.com", False),
            ("", False),
        ],
    )
    def test_is_blocked_host(self, url: str, expected: bool) -> None:
        assert is_blocked_host(url) is expected

    def test_robots_allows_none(self) -> None:
        assert robots_allows(None, "https://example.com/careers") is True

    def test_robots_allows_disallow_all(self) -> None:
        robots = "User-agent: *\nDisallow: /"
        assert robots_allows(robots, "https://example.com/careers") is False

    def test_robots_allows_path_specific(self) -> None:
        robots = (
            "User-agent: *\n"
            "Disallow: /private/\n"
            "Disallow: /careers/confidential\n"
        )
        assert robots_allows(robots, "https://example.com/private/page") is False
        assert robots_allows(robots, "https://example.com/careers/confidential") is False
        assert robots_allows(robots, "https://example.com/careers/openings") is True
        assert robots_allows(robots, "https://example.com/about") is True

    def test_robots_allows_allow_override(self) -> None:
        robots = (
            "User-agent: *\n"
            "Allow: /careers/openings\n"
            "Disallow: /careers/\n"
        )
        assert robots_allows(robots, "https://example.com/careers/closed") is False
        assert robots_allows(robots, "https://example.com/careers/openings") is True

    def test_load_candidates(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "candidates.csv"
        csv_file.write_text(
            "name,website,careers_url,hq_city,category,source,country\n"
            "Acme Corp,https://acme.com,https://acme.com/jobs,Bengaluru,fintech,yc,IN\n"
            ",https://noname.com,,,,\n"  # missing name -> skipped
            "No Website,,,,,,IN\n"  # missing website -> skipped
            ",,,,,,\n"  # both missing -> skipped
            "Default Country,https://default.com,,,saas,vc,\n"  # empty country -> default IN
            "  Padded Co  ,  https://padded.com  ,  https://padded.com/careers  ,  Delhi  ,  dev  ,  dir  ,  US  \n"
        )

        candidates = load_candidates(csv_file)
        assert len(candidates) == 3

        # Row 1
        assert candidates[0].name == "Acme Corp"
        assert candidates[0].website == "https://acme.com"
        assert candidates[0].careers_url == "https://acme.com/jobs"
        assert candidates[0].hq_city == "Bengaluru"
        assert candidates[0].category == "fintech"
        assert candidates[0].source == "yc"
        assert candidates[0].country == "IN"

        # Row 2 (default country)
        assert candidates[1].name == "Default Country"
        assert candidates[1].website == "https://default.com"
        assert candidates[1].country == "IN"

        # Row 3 (stripped whitespace and explicit country)
        assert candidates[2].name == "Padded Co"
        assert candidates[2].website == "https://padded.com"
        assert candidates[2].careers_url == "https://padded.com/careers"
        assert candidates[2].hq_city == "Delhi"
        assert candidates[2].category == "dev"
        assert candidates[2].source == "dir"
        assert candidates[2].country == "US"

    def test_existing_index(self) -> None:
        companies = [
            {"website": "https://www.acme.com", "slug": "acme"},
            {"website": "beta.io", "slug": "beta"},
            {"website": ""},
            {"slug": ""},
        ]
        boards = [
            {"board_url": "https://jobs.lever.co/acme/"},
            {"board_url": "https://jobs.ashbyhq.com/beta"},
            {"board_url": ""},
        ]
        domains, slugs, board_urls = existing_index(companies, boards)
        assert domains == {"acme.com", "beta.io"}
        assert slugs == {"acme", "beta"}
        assert board_urls == {"https://jobs.lever.co/acme", "https://jobs.ashbyhq.com/beta"}

    def test_registry_rows(self) -> None:
        candidate = Candidate(
            name="Acme Corp",
            website="https://acme.com",
            careers_url="https://acme.com/jobs",
            hq_city="Bengaluru",
            category="fintech",
            source="yc",
            country="IN",
        )
        outcome = Outcome(
            candidate=candidate,
            status="accepted",
            reason="verified",
            board_url="https://jobs.lever.co/acme",
            monitor_type="lever",
            monitor_config={"token": "acme"},
            jobs_found=5,
        )
        company, board = registry_rows(outcome, "acme-corp")

        assert company == {
            "slug": "acme-corp",
            "name": "Acme Corp",
            "website": "https://acme.com",
            "industry": "",
            "tier": "2",
            "enabled": "true",
            "country": "IN",
            "hq_city": "Bengaluru",
            "company_type": "fintech",
        }
        assert board == {
            "company_slug": "acme-corp",
            "board_slug": "acme-corp-lever",
            "board_url": "https://jobs.lever.co/acme",
            "monitor_type": "lever",
            "monitor_config": '{"token": "acme"}',
            "scraper_type": "",
            "scraper_config": "",
        }

    def test_registry_rows_empty_config(self) -> None:
        candidate = Candidate(name="Empty Config", website="https://empty.com")
        outcome = Outcome(
            candidate=candidate,
            status="accepted",
            board_url="https://empty.com/jobs",
            monitor_type="greenhouse",
            monitor_config={},
        )
        _, board = registry_rows(outcome, "empty-config")
        assert board["monitor_config"] == ""

    def test_outcome_dict(self) -> None:
        candidate = Candidate(
            name="Test Co",
            website="https://test.com",
            careers_url="https://test.com/careers",
            hq_city="Pune",
            category="saas",
            source="referral",
            country="IN",
        )
        outcome = Outcome(
            candidate=candidate,
            status="accepted",
            reason="verified",
            board_url="https://boards.greenhouse.io/test",
            monitor_type="greenhouse",
            monitor_config={"board_token": "test"},
            jobs_found=7,
        )
        d = outcome_dict(outcome)
        assert d == {
            "name": "Test Co",
            "website": "https://test.com",
            "careers_url": "https://test.com/careers",
            "hq_city": "Pune",
            "category": "saas",
            "source": "referral",
            "country": "IN",
            "slug": "",
            "scraper_type": "",
            "status": "accepted",
            "reason": "verified",
            "board_url": "https://boards.greenhouse.io/test",
            "monitor_type": "greenhouse",
            "monitor_config": '{"board_token": "test"}',
            "jobs_found": 7,
        }


# ---------------------------------------------------------------------------
# _fetch_robots tests
# ---------------------------------------------------------------------------


class TestFetchRobots:
    @pytest.mark.asyncio
    async def test_fetch_robots_caching_and_statuses(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if request.url.host == "example.com":
                return httpx.Response(200, text="User-agent: *\nDisallow: /admin", headers={"content-type": "text/plain"})
            if request.url.host == "notfound.com":
                return httpx.Response(404, text="Not found")
            if request.url.host == "json.com":
                return httpx.Response(200, text="{}", headers={"content-type": "application/json"})
            if request.url.host == "error.com":
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(500)

        cache: dict[str, str | None] = {}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            # 1. Successful text robots.txt
            text = await _fetch_robots(client, "https://example.com/careers", cache)
            assert text == "User-agent: *\nDisallow: /admin"
            assert calls == 1
            assert cache["https://example.com"] == "User-agent: *\nDisallow: /admin"

            # Repeated call should hit cache and not increment calls
            text_cached = await _fetch_robots(client, "https://example.com/other-page", cache)
            assert text_cached == text
            assert calls == 1

            # 2. 404 response
            not_found = await _fetch_robots(client, "https://notfound.com/jobs", cache)
            assert not_found is None
            assert cache["https://notfound.com"] is None

            # 3. Non-text content-type
            json_text = await _fetch_robots(client, "https://json.com/careers", cache)
            assert json_text is None
            assert cache["https://json.com"] is None

            # 4. HTTPError
            err_text = await _fetch_robots(client, "https://error.com/jobs", cache)
            assert err_text is None
            assert cache["https://error.com"] is None


# ---------------------------------------------------------------------------
# evaluate tests
# ---------------------------------------------------------------------------


class TestEvaluate:
    @pytest.mark.asyncio
    async def test_explicit_careers_url_trusted_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com", careers_url="https://jobs.lever.co/acme")

        monkeypatch.setattr(
            "src.core.monitors.detect_monitor_type",
            AsyncMock(return_value=("lever", {"token": "acme"})),
        )
        monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda monitor, config: False)
        monkeypatch.setattr("src.discovery.pipeline._fetch_robots", AsyncMock(return_value=None))
        monkeypatch.setattr(
            "src.core.monitor.monitor_one",
            AsyncMock(return_value=MonitorResult(urls={"https://jobs.lever.co/acme/job1", "https://jobs.lever.co/acme/job2"})),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "accepted"
        assert outcome.reason == "verified"
        assert outcome.jobs_found == 2
        assert outcome.board_url == "https://jobs.lever.co/acme"
        assert outcome.monitor_type == "lever"
        assert outcome.monitor_config == {"token": "acme"}

    @pytest.mark.asyncio
    async def test_trusted_monitor_zero_jobs_review(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com", careers_url="https://jobs.lever.co/acme")

        monkeypatch.setattr(
            "src.core.monitors.detect_monitor_type",
            AsyncMock(return_value=("lever", {"token": "acme"})),
        )
        monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda monitor, config: False)
        monkeypatch.setattr("src.discovery.pipeline._fetch_robots", AsyncMock(return_value=None))
        monkeypatch.setattr(
            "src.core.monitor.monitor_one",
            AsyncMock(return_value=MonitorResult(urls=set())),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "review"
        assert outcome.reason == "only 0 jobs parsed"
        assert outcome.jobs_found == 0

    @pytest.mark.asyncio
    async def test_untrusted_monitor_sitemap_review_generic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com", careers_url="https://acme.com/sitemap.xml")

        monkeypatch.setattr(
            "src.core.monitors.detect_monitor_type",
            AsyncMock(return_value=("sitemap", {})),
        )
        monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda monitor, config: False)
        monkeypatch.setattr("src.discovery.pipeline._fetch_robots", AsyncMock(return_value=None))
        urls = {f"https://acme.com/page/{i}" for i in range(300)}
        monkeypatch.setattr(
            "src.core.monitor.monitor_one",
            AsyncMock(return_value=MonitorResult(urls=urls)),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "review"
        assert outcome.reason == "generic monitor (sitemap) found 300 URLs; needs a human check"
        assert outcome.jobs_found == 300

    @pytest.mark.asyncio
    async def test_browser_only_monitor_review(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com", careers_url="https://careers.accenture.com")

        monkeypatch.setattr(
            "src.core.monitors.detect_monitor_type",
            AsyncMock(return_value=("accenture", {})),
        )
        monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda monitor, config: True)

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "review"
        assert outcome.reason == "needs browser rendering"
        assert outcome.board_url == "https://careers.accenture.com"
        assert outcome.monitor_type == "accenture"

    @pytest.mark.asyncio
    async def test_robots_disallow_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com", careers_url="https://boards.greenhouse.io/acme")

        monkeypatch.setattr(
            "src.core.monitors.detect_monitor_type",
            AsyncMock(return_value=("greenhouse", {"token": "acme"})),
        )
        monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda monitor, config: False)
        monkeypatch.setattr(
            "src.discovery.pipeline._fetch_robots",
            AsyncMock(return_value="User-agent: *\nDisallow: /"),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "rejected"
        assert outcome.reason == "robots.txt disallows board"

    @pytest.mark.asyncio
    async def test_discovery_raising_review(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com", careers_url="https://acme.com/careers")

        monkeypatch.setattr(
            "src.core.monitors.detect_monitor_type",
            AsyncMock(side_effect=httpx.ConnectError("Connection refused")),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "review"
        assert outcome.reason.startswith("discovery error: ConnectError: Connection refused")

    @pytest.mark.asyncio
    async def test_homepage_discovery_highest_score_and_skips_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com")

        # MockTransport responding to GET https://acme.com
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url).rstrip("/") == "https://acme.com"
            return httpx.Response(200, text="<html><body>Welcome to Acme</body></html>")

        discovered_candidates = [
            CareerPageCandidate(
                url="https://naukri.com/acme",
                source="homepage_link",
                monitor_type="dom",
                score=0.99,  # Blocked host! Should be skipped despite highest score.
            ),
            CareerPageCandidate(
                url="https://acme.com/jobs/unsupported",
                source="homepage_link",
                monitor_type="",  # No monitor_type! Should be skipped.
                score=0.95,
            ),
            CareerPageCandidate(
                url="https://jobs.lever.co/acme",
                source="homepage_link",
                monitor_type="lever",
                monitor_config={"token": "acme"},
                score=0.85,  # Valid trusted candidate with highest score among valid ones.
            ),
            CareerPageCandidate(
                url="https://boards.greenhouse.io/acme",
                source="homepage_link",
                monitor_type="greenhouse",
                monitor_config={"token": "acme"},
                score=0.70,  # Valid trusted candidate with lower score.
            ),
        ]

        monkeypatch.setattr(
            "src.workspace.career_discover.discover_career_pages",
            AsyncMock(return_value=discovered_candidates),
        )
        monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda monitor, config: False)
        monkeypatch.setattr("src.discovery.pipeline._fetch_robots", AsyncMock(return_value=None))
        monkeypatch.setattr(
            "src.core.monitor.monitor_one",
            AsyncMock(return_value=MonitorResult(urls={"https://jobs.lever.co/acme/1"})),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "accepted"
        assert outcome.board_url == "https://jobs.lever.co/acme"
        assert outcome.monitor_type == "lever"
        assert outcome.monitor_config == {"token": "acme"}
        assert outcome.jobs_found == 1

    @pytest.mark.asyncio
    async def test_evaluate_no_board_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html><body>No careers</body></html>")

        monkeypatch.setattr(
            "src.workspace.career_discover.discover_career_pages",
            AsyncMock(return_value=[]),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "review"
        assert outcome.reason == "no careers board detected"

    @pytest.mark.asyncio
    async def test_evaluate_monitor_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = Candidate(name="Acme", website="https://acme.com", careers_url="https://jobs.lever.co/acme")

        monkeypatch.setattr(
            "src.core.monitors.detect_monitor_type",
            AsyncMock(return_value=("lever", {"token": "acme"})),
        )
        monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda monitor, config: False)
        monkeypatch.setattr("src.discovery.pipeline._fetch_robots", AsyncMock(return_value=None))
        monkeypatch.setattr(
            "src.core.monitor.monitor_one",
            AsyncMock(side_effect=RuntimeError("ATS API timeout")),
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            outcome = await evaluate(candidate, client)

        assert outcome.status == "review"
        assert outcome.reason.startswith("monitor error: RuntimeError: ATS API timeout")


# ---------------------------------------------------------------------------
# run tests
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.mark.asyncio
    async def test_run_duplicates_by_domain_against_registry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        companies = [{"website": "https://www.acme.com", "slug": "acme"}]
        boards: list[dict] = []
        candidates = [Candidate(name="Acme Candidate", website="https://acme.com")]

        mock_evaluate = AsyncMock()
        monkeypatch.setattr("src.discovery.pipeline.evaluate", mock_evaluate)
        monkeypatch.setattr(
            "src.shared.http.create_http_client",
            lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        )

        outcomes = await run(candidates, companies, boards)
        assert len(outcomes) == 1
        assert outcomes[0].status == "duplicate"
        assert outcomes[0].reason == "already in registry"
        mock_evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_duplicates_within_batch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        companies: list[dict] = []
        boards: list[dict] = []
        candidates = [
            Candidate(name="Beta First", website="https://beta.com"),
            Candidate(name="Beta Second", website="https://www.beta.com"),
        ]

        async def fake_evaluate(c, client, **kwargs):
            return Outcome(c, "accepted", "verified", board_url="https://jobs.lever.co/beta", monitor_type="lever", jobs_found=3)

        monkeypatch.setattr("src.discovery.pipeline.evaluate", fake_evaluate)
        monkeypatch.setattr(
            "src.shared.http.create_http_client",
            lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        )

        outcomes = await run(candidates, companies, boards)
        assert len(outcomes) == 2
        statuses = {o.candidate.name: (o.status, o.reason) for o in outcomes}
        assert statuses["Beta First"] == ("accepted", "verified")
        assert statuses["Beta Second"] == ("duplicate", "already in registry")

    @pytest.mark.asyncio
    async def test_run_blocked_portal_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        companies: list[dict] = []
        boards: list[dict] = []
        candidates = [
            Candidate(name="Naukri Co", website="https://www.naukri.com/jobs"),
            Candidate(name="Indeed Co", website="https://sub.indeed.co.in"),
        ]

        mock_evaluate = AsyncMock()
        monkeypatch.setattr("src.discovery.pipeline.evaluate", mock_evaluate)
        monkeypatch.setattr(
            "src.shared.http.create_http_client",
            lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        )

        outcomes = await run(candidates, companies, boards)
        assert len(outcomes) == 2
        assert all(o.status == "rejected" for o in outcomes)
        assert all(o.reason == "job portal, not an employer site" for o in outcomes)
        mock_evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_per_company_timeout_review(self, monkeypatch: pytest.MonkeyPatch) -> None:
        companies: list[dict] = []
        boards: list[dict] = []
        candidates = [Candidate(name="Slow Co", website="https://slow.com")]

        async def slow_evaluate(c, client, **kwargs):
            await asyncio.sleep(0.5)
            return Outcome(c, "accepted")

        monkeypatch.setattr("src.discovery.pipeline.evaluate", slow_evaluate)
        monkeypatch.setattr(
            "src.shared.http.create_http_client",
            lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        )

        outcomes = await run(candidates, companies, boards, per_company_timeout=0.01)
        assert len(outcomes) == 1
        assert outcomes[0].status == "review"
        assert outcomes[0].reason == "timed out after 0s"

    @pytest.mark.asyncio
    async def test_run_accepted_board_url_already_in_registry_duplicate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        companies: list[dict] = []
        boards = [{"board_url": "https://jobs.lever.co/existing/"}]
        candidates = [Candidate(name="New Co", website="https://newco.com")]

        async def fake_evaluate(c, client, **kwargs):
            return Outcome(
                c,
                "accepted",
                "verified",
                board_url="https://jobs.lever.co/existing",
                monitor_type="lever",
                jobs_found=5,
            )

        monkeypatch.setattr("src.discovery.pipeline.evaluate", fake_evaluate)
        monkeypatch.setattr(
            "src.shared.http.create_http_client",
            lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        )

        outcomes = await run(candidates, companies, boards)
        assert len(outcomes) == 1
        assert outcomes[0].status == "duplicate"
        assert outcomes[0].reason == "board already in registry"

    @pytest.mark.asyncio
    async def test_run_accepted_new_board(self, monkeypatch: pytest.MonkeyPatch) -> None:
        companies: list[dict] = []
        boards: list[dict] = []
        candidates = [Candidate(name="Fresh Co", website="https://fresh.com")]

        async def fake_evaluate(c, client, **kwargs):
            return Outcome(
                c,
                "accepted",
                "verified",
                board_url="https://jobs.lever.co/fresh",
                monitor_type="lever",
                jobs_found=12,
            )

        monkeypatch.setattr("src.discovery.pipeline.evaluate", fake_evaluate)
        monkeypatch.setattr(
            "src.shared.http.create_http_client",
            lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        )

        outcomes = await run(candidates, companies, boards)
        assert len(outcomes) == 1
        assert outcomes[0].status == "accepted"
        assert outcomes[0].reason == "verified"
        assert outcomes[0].jobs_found == 12


def test_has_jobposting_jsonld():
    from src.discovery.pipeline import has_jobposting_jsonld

    assert has_jobposting_jsonld('<script type="application/ld+json">{"@type": "JobPosting", "title": "x"}</script>')
    assert has_jobposting_jsonld('{"@context":"https://schema.org","@type":["JobPosting"]}')
    assert not has_jobposting_jsonld('{"@type": "Organization"}')
    assert not has_jobposting_jsonld("")


async def test_generic_sitemap_accepted_when_samples_are_jobpostings(monkeypatch):
    import httpx

    from src.core.monitor import MonitorResult
    from src.discovery import pipeline

    urls = {f"https://acme.in/careers/job-{i}" for i in range(30)}

    async def fake_find(c, client):
        return "https://acme.in/careers", "sitemap", {}

    async def fake_monitor(board_url, monitor_type, config, client):
        return MonitorResult(urls=set(urls))

    async def fake_robots(client, url, cache):
        return None

    monkeypatch.setattr(pipeline, "_find_board", fake_find)
    monkeypatch.setattr("src.core.monitor.monitor_one", fake_monitor)
    monkeypatch.setattr("src.core.monitors.monitor_needs_browser", lambda *a, **k: False)
    monkeypatch.setattr(pipeline, "_fetch_robots", fake_robots)

    def handler(req):
        return httpx.Response(200, text='<script type="application/ld+json">{"@type":"JobPosting"}</script>')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out = await pipeline.evaluate(pipeline.Candidate(name="Acme", website="https://acme.in"), client)
    assert out.status == "accepted" and out.scraper_type == "json-ld"

    def plain(req):
        return httpx.Response(200, text="<html>About us</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(plain)) as client:
        out = await pipeline.evaluate(pipeline.Candidate(name="Acme", website="https://acme.in"), client)
    assert out.status == "review" and "generic monitor" in out.reason
