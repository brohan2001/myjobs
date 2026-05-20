"""Pipeline normalisation and monitor smoke tests.

Replaces the old per-ATS scraper parser tests. The new pipeline uses jobseek's
monitor_one_stream → raw_jobs → normalize_to_jobs_row → jobs table flow.

These tests verify:
  1. normalize_to_jobs_row output shape (pure unit, no network)
  2. monitor/scraper registry sanity
  3. raw_jobs → jobs DB integration cycle
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

import src.database as db_module
from src.database import (
    get_conn,
    get_existing_keys,
    get_unparsed_raw_jobs,
    init_db,
    insert_jobs,
    mark_raw_parsed,
    record_raw_job,
    update_raw_job_payload,
    upsert_board,
    upsert_company,
    upsert_company_from_board,
)
from src.normalize import normalize_to_jobs_row

FIXTURE_DIR = Path(__file__).parent / "fixtures"

COMPANY_ID = 42
BOARD_ID = 1


def _board(
    company_id: int = COMPANY_ID,
    monitor_type: str = "greenhouse",
    board_slug: str = "acme-greenhouse",
) -> SimpleNamespace:
    """Minimal board-like object for normalize_to_jobs_row."""
    return SimpleNamespace(
        company_id=company_id,
        monitor_type=monitor_type,
        board_slug=board_slug,
    )


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    init_db()
    return db_file


@pytest.fixture()
def db_board_id(tmp_db):
    """Insert one company + board and return the board db id."""
    with get_conn() as conn:
        cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
        bid = upsert_board(
            conn, cid, "acme-greenhouse",
            "https://job-boards.greenhouse.io/acme",
            "greenhouse", {"token": "acme"}, "skip", {},
        )
    return bid


# ── 1. normalize_to_jobs_row — output shape ────────────────────────────────────

class TestNormalizeShape:
    """Verify the jobs-row dict produced by normalize_to_jobs_row."""

    REQUIRED: dict[str, type | tuple] = {
        "external_id": str,
        "company_id":  int,
        "title":       str,
        "url":         str,
        "ats_type":    str,
        "remote":      int,
    }
    NULLABLE: dict[str, type] = {
        "description": str,
        "location":    str,
        "posted_date": str,
        "posted_at":   str,
    }

    def _assert_shape(self, row: dict) -> None:
        for field, t in self.REQUIRED.items():
            assert field in row, f"missing '{field}'"
            assert isinstance(row[field], t), (
                f"'{field}' expected {t}, got {type(row[field])}: {row[field]!r}"
            )
        for field, t in self.NULLABLE.items():
            assert field in row, f"missing nullable '{field}'"
            assert row[field] is None or isinstance(row[field], t), (
                f"'{field}' must be str or None, got {type(row[field])}"
            )

    def test_greenhouse_rich_payload(self):
        payload = {
            "url":         "https://job-boards.greenhouse.io/acme/jobs/12345",
            "title":       "Software Engineer",
            "description": "<p>Build things.</p>",
            "locations":   ["San Francisco, CA", "Remote"],
            "employment_type": "FULL_TIME",
            "job_location_type": "REMOTE",
            "date_posted": "2026-04-01",
        }
        row = normalize_to_jobs_row(payload, _board())
        self._assert_shape(row)
        assert row["external_id"] == "12345"
        assert row["company_id"] == COMPANY_ID
        assert row["remote"] == 1
        assert row["ats_type"] == "greenhouse"

    def test_location_joined_from_list(self):
        payload = {
            "url":      "https://example.com/jobs/7",
            "title":    "Designer",
            "locations": ["New York, NY", "Austin, TX"],
        }
        row = normalize_to_jobs_row(payload, _board(monitor_type="lever"))
        assert row["location"] == "New York, NY; Austin, TX"

    def test_remote_from_location_text(self):
        payload = {
            "url":       "https://example.com/jobs/8",
            "title":     "Engineer",
            "locations": ["Remote - United States"],
        }
        row = normalize_to_jobs_row(payload, _board())
        assert row["remote"] == 1

    def test_non_remote_job(self):
        payload = {
            "url":       "https://example.com/jobs/9",
            "title":     "Analyst",
            "locations": ["New York, NY"],
        }
        row = normalize_to_jobs_row(payload, _board())
        assert row["remote"] == 0

    def test_date_coercion(self):
        payload = {
            "url":         "https://example.com/jobs/10",
            "title":       "PM",
            "date_posted": "2026-03-15T00:00:00Z",
        }
        row = normalize_to_jobs_row(payload, _board())
        assert row["posted_date"] == "2026-03-15"
        assert row["posted_at"] == "2026-03-15"

    def test_missing_title_raises(self):
        payload = {"url": "https://example.com/jobs/11"}
        with pytest.raises(ValueError, match="Missing title or url"):
            normalize_to_jobs_row(payload, _board())

    def test_missing_url_raises(self):
        payload = {"title": "Engineer"}
        with pytest.raises(ValueError, match="Missing title or url"):
            normalize_to_jobs_row(payload, _board())

    def test_english_localisation_preferred(self):
        payload = {
            "url":   "https://example.com/jobs/99",
            "title": "Ingénieur",
            "localizations": {
                "en": {"title": "Software Engineer", "locations": ["Paris, FR"]},
            },
        }
        row = normalize_to_jobs_row(payload, _board())
        assert row["title"] == "Software Engineer"

    def test_external_id_from_url_last_segment(self):
        payload = {
            "url":   "https://jobs.lever.co/acme/abc-def-1234",
            "title": "Backend Engineer",
        }
        row = normalize_to_jobs_row(payload, _board(monitor_type="lever"))
        assert row["external_id"] == "abc-def-1234"


# ── 2. Monitor / scraper registry sanity ──────────────────────────────────────

class TestMonitorRegistry:
    def test_greenhouse_monitor_registered(self):
        from src.core.monitors import get_discoverer
        fn = get_discoverer("greenhouse")
        assert fn is not None

    def test_lever_monitor_registered(self):
        from src.core.monitors import get_discoverer
        assert get_discoverer("lever") is not None

    def test_dom_monitor_registered(self):
        from src.core.monitors import get_discoverer
        assert get_discoverer("dom") is not None

    def test_skip_scraper_registered(self):
        from src.core.scrapers import get_scraper
        assert get_scraper("skip") is not None

    def test_dom_scraper_registered(self):
        from src.core.scrapers import get_scraper
        assert get_scraper("dom") is not None

    def test_browser_detection_dom_render_true(self):
        from src.core.monitors import monitor_needs_browser
        assert monitor_needs_browser("dom", {"render": True}) is True

    def test_browser_detection_dom_render_false(self):
        from src.core.monitors import monitor_needs_browser
        assert monitor_needs_browser("dom", {"render": False}) is False

    def test_browser_detection_greenhouse_never(self):
        from src.core.monitors import monitor_needs_browser
        assert monitor_needs_browser("greenhouse", {}) is False

    def test_scraper_browser_detection(self):
        from src.core.scrapers import scraper_needs_browser
        assert scraper_needs_browser("skip") is False


# ── 3. raw_jobs → jobs DB integration cycle ───────────────────────────────────

class TestRawJobCycle:
    """End-to-end test: record_raw_job → parse → insert_jobs → mark_raw_parsed."""

    PAYLOAD_RICH = {
        "url":         "https://job-boards.greenhouse.io/acme/jobs/9001",
        "title":       "Staff Engineer",
        "description": "<p>Build distributed systems.</p>",
        "locations":   ["Remote"],
        "job_location_type": "REMOTE",
        "date_posted": "2026-05-01",
    }

    def test_rich_monitor_job_inserted(self, tmp_db, db_board_id):
        url = self.PAYLOAD_RICH["url"]
        with get_conn() as conn:
            record_raw_job(conn, db_board_id, url, self.PAYLOAD_RICH, "monitor_rich")

        with get_conn() as conn:
            raw_rows = get_unparsed_raw_jobs(conn)
        assert len(raw_rows) == 1

        row = raw_rows[0]
        with get_conn() as conn:
            existing = get_existing_keys(conn)
            payload = json.loads(row["payload"])
            norm = normalize_to_jobs_row(payload, row)
            assert (norm["external_id"], norm["ats_type"]) not in existing
            inserted, ids = insert_jobs(conn, [norm])
            assert inserted == 1
            mark_raw_parsed(conn, row["id"], ids[0], None)

        with get_conn() as conn:
            unparsed = get_unparsed_raw_jobs(conn)
        assert len(unparsed) == 0

        with get_conn() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (ids[0],)).fetchone()
        assert job["title"] == "Staff Engineer"
        assert job["remote"] == 1
        assert job["ats_type"] == "greenhouse"

    def test_duplicate_url_not_double_inserted(self, tmp_db, db_board_id):
        url = self.PAYLOAD_RICH["url"]
        with get_conn() as conn:
            record_raw_job(conn, db_board_id, url, self.PAYLOAD_RICH, "monitor_rich")
            record_raw_job(conn, db_board_id, url, self.PAYLOAD_RICH, "monitor_rich")  # duplicate
            rows = conn.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
        assert rows == 1

    def test_url_only_flow_updates_payload(self, tmp_db, db_board_id):
        url = "https://example.com/careers/dev-12"
        stub = {"url": url}
        scraped = {
            "url":   url,
            "title": "Frontend Engineer",
            "description": "<p>Build UIs.</p>",
            "locations": ["Austin, TX"],
        }
        with get_conn() as conn:
            record_raw_job(conn, db_board_id, url, stub, "monitor")
            raw_id = conn.execute("SELECT id FROM raw_jobs WHERE source_url=?", (url,)).fetchone()["id"]

        with get_conn() as conn:
            update_raw_job_payload(conn, raw_id, scraped, "scraper")

        with get_conn() as conn:
            r = conn.execute("SELECT payload, payload_source FROM raw_jobs WHERE id=?", (raw_id,)).fetchone()
        assert r["payload_source"] == "scraper"
        assert json.loads(r["payload"])["title"] == "Frontend Engineer"

    def test_parse_error_marks_row_done(self, tmp_db, db_board_id):
        url = "https://example.com/jobs/bad-job"
        with get_conn() as conn:
            record_raw_job(conn, db_board_id, url, {"url": url}, "monitor_rich")
            raw_id = conn.execute("SELECT id FROM raw_jobs WHERE source_url=?", (url,)).fetchone()["id"]
            mark_raw_parsed(conn, raw_id, None, "Missing title or url")

        with get_conn() as conn:
            r = conn.execute("SELECT parsed, parse_error FROM raw_jobs WHERE id=?", (raw_id,)).fetchone()
        assert r["parsed"] == 1
        assert "Missing title" in r["parse_error"]

    def test_salary_structured_stored(self, tmp_db, db_board_id):
        payload = {
            "url":         "https://example.com/jobs/sal1",
            "title":       "Staff Engineer",
            "description": "<p>Build things.</p>",
            "base_salary": {"currency": "USD", "min": 140000, "max": 220000, "unit": "year"},
        }
        with get_conn() as conn:
            record_raw_job(conn, db_board_id, payload["url"], payload, "monitor_rich")
        with get_conn() as conn:
            raw_rows = get_unparsed_raw_jobs(conn)
            row = raw_rows[0]
            payload = json.loads(row["payload"])
            norm = normalize_to_jobs_row(payload, row)
            assert norm["salary_min_usd"] == 140000
            assert norm["salary_max_usd"] == 220000
            inserted, ids = insert_jobs(conn, [norm])
            mark_raw_parsed(conn, row["id"], ids[0] if ids else None, None)
        with get_conn() as conn:
            j = conn.execute("SELECT salary_min_usd, salary_max_usd FROM jobs WHERE id=?", (ids[0],)).fetchone()
        assert j["salary_min_usd"] == 140000
        assert j["salary_max_usd"] == 220000

    def test_experience_extraction_stored(self, tmp_db, db_board_id):
        payload = {
            "url":         "https://example.com/jobs/exp1",
            "title":       "Senior Backend Engineer",
            "description": "<p>We require 5+ years of engineering experience.</p>",
        }
        row = normalize_to_jobs_row(payload, _board())
        assert row["exp_years_max"] == 5

    def test_greenhouse_fixture_normalizes(self, tmp_db, db_board_id):
        """Round-trip test using the real Greenhouse API fixture."""
        fixture = json.loads((FIXTURE_DIR / "greenhouse_anthropic.json").read_text())
        first_raw_job = fixture["jobs"][0]
        payload = {
            "url":         first_raw_job["absolute_url"],
            "title":       first_raw_job["title"],
            "description": first_raw_job.get("content"),
            "locations":   [first_raw_job["location"]["name"]] if first_raw_job.get("location") else [],
        }
        row = normalize_to_jobs_row(payload, _board())
        assert row["title"] == first_raw_job["title"]
        assert row["url"] == first_raw_job["absolute_url"]
        assert isinstance(row["external_id"], str) and row["external_id"]
