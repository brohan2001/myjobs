"""Tests for scripts/discover_companies.py."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import scripts.discover_companies as script_mod
from scripts.discover_companies import main
from src.discovery.pipeline import Candidate, Outcome


@pytest.fixture
def registry_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory with initial companies.csv and boards.csv."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    companies_csv = data_dir / "companies.csv"
    companies_csv.write_text(
        "slug,name,website,industry,tier,enabled\n"
        "anthropic,Anthropic,https://www.anthropic.com,1,1,true\n"
    )

    boards_csv = data_dir / "boards.csv"
    boards_csv.write_text(
        "company_slug,board_slug,board_url,monitor_type,monitor_config,scraper_type,scraper_config\n"
        'anthropic,anthropic-greenhouse,https://job-boards.greenhouse.io/anthropic,greenhouse,"{""token"": ""anthropic""}",skip,\n'
    )

    return data_dir


@pytest.fixture
def candidates_csv(tmp_path: Path) -> Path:
    """Creates a candidate CSV file with 3 candidates."""
    csv_file = tmp_path / "candidates.csv"
    csv_file.write_text(
        "name,website,careers_url,hq_city,category,source,country\n"
        "Acme Corp,https://acme.com,https://jobs.lever.co/acme,Bengaluru,fintech,yc,IN\n"
        "Beta Labs,https://beta.com,https://beta.com/sitemap.xml,Delhi,saas,vc,IN\n"
        "Blocked Portal,https://naukri.com/jobs,,,,portal,IN\n"
    )
    return csv_file


class TestDiscoverCompaniesScript:
    def test_dry_run(
        self,
        registry_dir: Path,
        candidates_csv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(script_mod, "DATA", registry_dir)

        c1 = Candidate(name="Acme Corp", website="https://acme.com", careers_url="https://jobs.lever.co/acme", hq_city="Bengaluru", category="fintech", source="yc", country="IN")
        c2 = Candidate(name="Beta Labs", website="https://beta.com", careers_url="https://beta.com/sitemap.xml", hq_city="Delhi", category="saas", source="vc", country="IN")
        c3 = Candidate(name="Blocked Portal", website="https://naukri.com/jobs", category="portal", country="IN")

        canned_outcomes = [
            Outcome(c1, "accepted", "verified", board_url="https://jobs.lever.co/acme", monitor_type="lever", jobs_found=5),
            Outcome(c2, "review", "generic monitor (sitemap) found 20 URLs; needs a human check", board_url="https://beta.com/sitemap.xml", monitor_type="sitemap", jobs_found=20),
            Outcome(c3, "rejected", "job portal, not an employer site"),
        ]

        async def fake_run(*args, **kwargs):
            return canned_outcomes

        monkeypatch.setattr(script_mod, "run", fake_run)

        rc = main([str(candidates_csv)])
        assert rc == 0

        out_dir = registry_dir / "candidates"
        report_path = out_dir / "discovery_report.json"
        review_path = out_dir / "review_queue.csv"

        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report["candidates"] == 3
        assert report["status"] == {"accepted": 1, "review": 1, "rejected": 1}
        assert report["accepted_by_ats"] == {"lever": 1}
        assert report["accepted_jobs"] == 5
        assert report["review_reasons"] == {"generic monitor (sitemap) found N URLs; needs a human check": 1}

        assert review_path.exists()
        with open(review_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            review_rows = list(reader)

        assert len(review_rows) == 2
        assert review_rows[0]["name"] == "Beta Labs"
        assert review_rows[0]["status"] == "review"
        assert review_rows[0]["monitor_type"] == "sitemap"
        assert review_rows[0]["jobs_found"] == "20"
        assert review_rows[1]["name"] == "Blocked Portal"
        assert review_rows[1]["status"] == "rejected"

        # In dry run, registry files should NOT be modified
        with open(registry_dir / "companies.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert list(reader.fieldnames or []) == ["slug", "name", "website", "industry", "tier", "enabled"]
            assert len(list(reader)) == 1

        with open(registry_dir / "boards.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert len(list(reader)) == 1

    def test_apply_mode(
        self,
        registry_dir: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(script_mod, "DATA", registry_dir)

        # Candidates designed to test slug collisions with existing registry and within the batch
        candidates_file = tmp_path / "colliding_candidates.csv"
        candidates_file.write_text(
            "name,website,careers_url,hq_city,category,source,country\n"
            "Acme Corp,https://acme1.com,,Bengaluru,fintech,,IN\n"
            "Anthropic,https://anthropic.io,,San Francisco,ai,,US\n"  # Collides with existing 'anthropic' in registry -> 'anthropic-2'
            "Acme Corp,https://acme2.com,,Mumbai,fintech,,IN\n"  # Collides with earlier candidate in batch -> 'acme-corp-2'
        )

        c1 = Candidate(name="Acme Corp", website="https://acme1.com", hq_city="Bengaluru", category="fintech", country="IN")
        c2 = Candidate(name="Anthropic", website="https://anthropic.io", hq_city="San Francisco", category="ai", country="US")
        c3 = Candidate(name="Acme Corp", website="https://acme2.com", hq_city="Mumbai", category="fintech", country="IN")

        canned_outcomes = [
            Outcome(c1, "accepted", "verified", board_url="https://jobs.lever.co/acme", monitor_type="lever", jobs_found=3),
            Outcome(c2, "accepted", "verified", board_url="https://jobs.ashbyhq.com/anthropic2", monitor_type="ashby", monitor_config={"token": "anthropic2"}, jobs_found=10),
            Outcome(c3, "accepted", "verified", board_url="https://boards.greenhouse.io/acme2", monitor_type="greenhouse", jobs_found=1),
        ]

        async def fake_run(*args, **kwargs):
            return canned_outcomes

        monkeypatch.setattr(script_mod, "run", fake_run)

        rc = main([str(candidates_file), "--apply"])
        assert rc == 0

        # Verify companies.csv
        with open(registry_dir / "companies.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == [
                "slug", "name", "website", "industry", "tier", "enabled",
                "country", "hq_city", "company_type",
            ]
            rows = list(reader)

        assert len(rows) == 4
        assert rows[0]["slug"] == "anthropic"
        assert rows[0]["name"] == "Anthropic"

        assert rows[1]["slug"] == "acme-corp"
        assert rows[1]["name"] == "Acme Corp"
        assert rows[1]["country"] == "IN"
        assert rows[1]["hq_city"] == "Bengaluru"
        assert rows[1]["company_type"] == "fintech"

        assert rows[2]["slug"] == "anthropic-2"  # Collision with existing registry slug resolved
        assert rows[2]["name"] == "Anthropic"
        assert rows[2]["country"] == "US"
        assert rows[2]["hq_city"] == "San Francisco"
        assert rows[2]["company_type"] == "ai"

        assert rows[3]["slug"] == "acme-corp-2"  # Collision within batch resolved
        assert rows[3]["name"] == "Acme Corp"
        assert rows[3]["country"] == "IN"
        assert rows[3]["hq_city"] == "Mumbai"
        assert rows[3]["company_type"] == "fintech"

        # Verify boards.csv
        with open(registry_dir / "boards.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            b_rows = list(reader)

        assert len(b_rows) == 4
        assert b_rows[1]["company_slug"] == "acme-corp"
        assert b_rows[1]["board_slug"] == "acme-corp-lever"
        assert b_rows[1]["board_url"] == "https://jobs.lever.co/acme"
        assert b_rows[1]["monitor_type"] == "lever"

        assert b_rows[2]["company_slug"] == "anthropic-2"
        assert b_rows[2]["board_slug"] == "anthropic-2-ashby"
        assert b_rows[2]["board_url"] == "https://jobs.ashbyhq.com/anthropic2"
        assert b_rows[2]["monitor_type"] == "ashby"
        assert b_rows[2]["monitor_config"] == '{"token": "anthropic2"}'

        assert b_rows[3]["company_slug"] == "acme-corp-2"
        assert b_rows[3]["board_slug"] == "acme-corp-2-greenhouse"
        assert b_rows[3]["board_url"] == "https://boards.greenhouse.io/acme2"
        assert b_rows[3]["monitor_type"] == "greenhouse"

    def test_limit_flag(
        self,
        registry_dir: Path,
        candidates_csv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(script_mod, "DATA", registry_dir)

        captured_candidates: list[Candidate] = []

        async def fake_run(candidates, *args, **kwargs):
            nonlocal captured_candidates
            captured_candidates = candidates
            return [Outcome(c, "accepted") for c in candidates]

        monkeypatch.setattr(script_mod, "run", fake_run)

        rc = main([str(candidates_csv), "--limit", "1"])
        assert rc == 0
        assert len(captured_candidates) == 1
        assert captured_candidates[0].name == "Acme Corp"

        report_path = registry_dir / "candidates" / "discovery_report.json"
        report = json.loads(report_path.read_text())
        assert report["candidates"] == 1

    def test_custom_out_dir(
        self,
        registry_dir: Path,
        candidates_csv: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(script_mod, "DATA", registry_dir)

        custom_out = tmp_path / "custom_output"
        c1 = Candidate(name="Acme Corp", website="https://acme.com")
        c2 = Candidate(name="Beta Labs", website="https://beta.com")

        async def fake_run(*args, **kwargs):
            return [
                Outcome(c1, "accepted", "verified", monitor_type="lever", jobs_found=1),
                Outcome(c2, "review", "generic monitor (sitemap) found 1 URLs; needs a human check"),
            ]

        monkeypatch.setattr(script_mod, "run", fake_run)

        rc = main([str(candidates_csv), "--out-dir", str(custom_out)])
        assert rc == 0

        assert (custom_out / "discovery_report.json").exists()
        assert (custom_out / "review_queue.csv").exists()

    def test_all_accepted_no_review_queue(
        self,
        registry_dir: Path,
        candidates_csv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(script_mod, "DATA", registry_dir)

        c1 = Candidate(name="Acme Corp", website="https://acme.com")

        async def fake_run(*args, **kwargs):
            return [Outcome(c1, "accepted", "verified", monitor_type="lever", jobs_found=4)]

        monkeypatch.setattr(script_mod, "run", fake_run)

        rc = main([str(candidates_csv)])
        assert rc == 0

        out_dir = registry_dir / "candidates"
        assert (out_dir / "discovery_report.json").exists()
        assert not (out_dir / "review_queue.csv").exists()

    def test_concurrency_and_min_jobs_options(
        self,
        registry_dir: Path,
        candidates_csv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(script_mod, "DATA", registry_dir)

        captured_kwargs: dict = {}

        async def fake_run(candidates, companies, boards, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return [Outcome(candidates[0], "accepted")]

        monkeypatch.setattr(script_mod, "run", fake_run)

        rc = main([str(candidates_csv), "--concurrency", "4", "--min-jobs", "3"])
        assert rc == 0
        assert captured_kwargs.get("concurrency") == 4
        assert captured_kwargs.get("min_jobs") == 3
