from __future__ import annotations

import json

import pytest

import src.database as db_module
from src.database import (
    get_conn,
    get_existing_keys,
    get_shortlist,
    get_top_unshortlisted,
    get_unparsed_raw_jobs,
    get_unscraped_url_only_raw_jobs,
    init_db,
    insert_jobs,
    mark_raw_parsed,
    mark_shortlisted,
    record_raw_job,
    update_board_failure,
    update_board_success,
    update_raw_job_payload,
    upsert_board,
    upsert_company,
    upsert_company_from_board,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp file and initialise a fresh schema."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    init_db()
    return db_file


def _company(**overrides) -> dict:
    data = {
        "name": "Acme Corp",
        "slug": "acme",
        "ats_type": "greenhouse",
        "domain": "acme.com",
        "industry": "tech",
        "tier": 1,
    }
    data.update(overrides)
    return data


def _job(company_id: int, external_id: str = "ext1", **overrides) -> dict:
    data = {
        "external_id": external_id,
        "company_id": company_id,
        "title": "Software Engineer",
        "description": "Python developer needed",
        "location": "Remote",
        "remote": 1,
        "url": f"https://example.com/jobs/{external_id}",
        "posted_date": "2026-05-07",
        "posted_at": None,
        "ats_type": "greenhouse",
    }
    data.update(overrides)
    return data


# ── init_db ───────────────────────────────────────────────────────────────────

class TestInitDb:
    def test_creates_all_tables(self, tmp_db):
        with get_conn() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert {"jobs", "companies", "daily_runs", "applications"}.issubset(tables)

    def test_idempotent(self, tmp_db):
        # Running twice must not raise
        init_db()
        init_db()

    def test_posted_at_column_present(self, tmp_db):
        with get_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        assert "posted_at" in cols


# ── upsert_company ────────────────────────────────────────────────────────────

class TestUpsertCompany:
    def test_inserts_new_company_returns_id(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
        assert isinstance(cid, int) and cid > 0

    def test_duplicate_returns_same_id(self, tmp_db):
        with get_conn() as conn:
            id1 = upsert_company(conn, _company())
            id2 = upsert_company(conn, _company())
        assert id1 == id2

    def test_different_slug_inserts_separately(self, tmp_db):
        with get_conn() as conn:
            id1 = upsert_company(conn, _company(name="Acme", slug="acme"))
            id2 = upsert_company(conn, _company(name="Beta", slug="beta"))
        assert id1 != id2


# ── insert_jobs ───────────────────────────────────────────────────────────────

class TestInsertJobs:
    def test_returns_inserted_count(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            count, ids = insert_jobs(conn, [_job(cid, "a"), _job(cid, "b")])
        assert count == 2
        assert len(ids) == 2

    def test_duplicate_external_id_not_reinserted(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            count, ids = insert_jobs(conn, [_job(cid, "ext1")])
        assert count == 0
        assert ids == []

    def test_missing_posted_at_defaults_to_none(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            job = _job(cid, "ext1")
            del job["posted_at"]  # omit — insert_jobs should default it to None
            count, ids = insert_jobs(conn, [job])
        assert count == 1
        assert len(ids) == 1

    def test_empty_list_returns_zero(self, tmp_db):
        with get_conn() as conn:
            count, ids = insert_jobs(conn, [])
        assert count == 0
        assert ids == []


# ── get_existing_keys ─────────────────────────────────────────────────────────

class TestGetExistingKeys:
    def test_empty_db_returns_empty_set(self, tmp_db):
        with get_conn() as conn:
            keys = get_existing_keys(conn)
        assert keys == set()

    def test_returns_tuple_of_id_and_ats(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            keys = get_existing_keys(conn)
        assert ("ext1", "greenhouse") in keys

    def test_multiple_jobs_all_returned(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1"), _job(cid, "ext2")])
            keys = get_existing_keys(conn)
        assert {("ext1", "greenhouse"), ("ext2", "greenhouse")}.issubset(keys)


# ── get_top_unshortlisted ─────────────────────────────────────────────────────

class TestGetTopUnshortlisted:
    def test_excludes_visa_signal_minus_one(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            conn.execute("UPDATE jobs SET visa_signal=-1, total_score=80")
            results = get_top_unshortlisted(conn, limit=10)
        assert len(results) == 0

    def test_includes_unknown_visa_signal(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            conn.execute("UPDATE jobs SET visa_signal=0, total_score=50")
            results = get_top_unshortlisted(conn, limit=10)
        assert len(results) == 1

    def test_includes_confirmed_visa_signal(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            conn.execute("UPDATE jobs SET visa_signal=1, total_score=70")
            results = get_top_unshortlisted(conn, limit=10)
        assert len(results) == 1

    def test_ordered_by_score_descending(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "low"), _job(cid, "high")])
            conn.execute("UPDATE jobs SET total_score=30 WHERE external_id='low'")
            conn.execute("UPDATE jobs SET total_score=80 WHERE external_id='high'")
            results = get_top_unshortlisted(conn, limit=10)
        assert results[0]["external_id"] == "high"

    def test_respects_limit(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, f"ext{i}") for i in range(5)])
            results = get_top_unshortlisted(conn, limit=3)
        assert len(results) == 3

    def test_excludes_already_shortlisted(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            jid = conn.execute("SELECT id FROM jobs").fetchone()["id"]
            mark_shortlisted(conn, [jid])
            results = get_top_unshortlisted(conn, limit=10)
        assert len(results) == 0


# ── mark_shortlisted ──────────────────────────────────────────────────────────

class TestMarkShortlisted:
    def test_sets_status_to_shortlisted(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            jid = conn.execute("SELECT id FROM jobs WHERE external_id='ext1'").fetchone()["id"]
            mark_shortlisted(conn, [jid])
            status = conn.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()["status"]
        assert status == "shortlisted"

    def test_batch_update(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1"), _job(cid, "ext2")])
            ids = [r["id"] for r in conn.execute("SELECT id FROM jobs").fetchall()]
            mark_shortlisted(conn, ids)
            count = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='shortlisted'"
            ).fetchone()[0]
        assert count == 2


# ── get_shortlist ─────────────────────────────────────────────────────────────

class TestGetShortlist:
    def test_returns_shortlisted_jobs_for_date(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            jid = conn.execute("SELECT id FROM jobs").fetchone()["id"]
            mark_shortlisted(conn, [jid])
            # scraped_at defaults to datetime('now'), so today's date matches
            import datetime
            today = datetime.date.today().isoformat()
            results = get_shortlist(conn, run_date=today, limit=10)
        assert len(results) == 1
        assert results[0]["external_id"] == "ext1"

    def test_wrong_date_returns_empty(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "ext1")])
            jid = conn.execute("SELECT id FROM jobs").fetchone()["id"]
            mark_shortlisted(conn, [jid])
            results = get_shortlist(conn, run_date="2000-01-01", limit=10)
        assert len(results) == 0


# ── boards + raw_jobs helpers ─────────────────────────────────────────────────

def _board_id(conn, company_id: int) -> int:
    return upsert_board(
        conn, company_id, "acme-greenhouse",
        "https://job-boards.greenhouse.io/acme",
        "greenhouse", {"token": "acme"}, "skip", {},
    )


class TestUpsertBoard:
    def test_insert_returns_id(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
        assert isinstance(bid, int) and bid > 0

    def test_idempotent_same_id(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            b1 = _board_id(conn, cid)
            b2 = _board_id(conn, cid)
        assert b1 == b2

    def test_board_url_updated_on_conflict(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            upsert_board(conn, cid, "acme-greenhouse", "https://old.url/",
                         "greenhouse", {}, "skip", {})
            upsert_board(conn, cid, "acme-greenhouse", "https://new.url/",
                         "greenhouse", {}, "skip", {})
            row = conn.execute(
                "SELECT board_url FROM boards WHERE board_slug='acme-greenhouse'"
            ).fetchone()
        assert row["board_url"] == "https://new.url/"

    def test_board_success_clears_failures(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
            update_board_failure(conn, bid, "timeout")
            update_board_failure(conn, bid, "timeout")
            update_board_success(conn, bid)
            row = conn.execute(
                "SELECT consecutive_failures FROM boards WHERE id=?", (bid,)
            ).fetchone()
        assert row["consecutive_failures"] == 0

    def test_board_failure_increments(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
            update_board_failure(conn, bid, "err1")
            update_board_failure(conn, bid, "err2")
            row = conn.execute(
                "SELECT consecutive_failures, last_error FROM boards WHERE id=?", (bid,)
            ).fetchone()
        assert row["consecutive_failures"] == 2
        assert row["last_error"] == "err2"


class TestRecordRawJob:
    def test_insert_returns_id(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
            raw_id = record_raw_job(conn, bid, "https://example.com/jobs/1",
                                    {"url": "https://example.com/jobs/1"}, "monitor_rich")
        assert isinstance(raw_id, int) and raw_id > 0

    def test_duplicate_url_ignored(self, tmp_db):
        url = "https://example.com/jobs/42"
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
            id1 = record_raw_job(conn, bid, url, {"url": url}, "monitor_rich")
            id2 = record_raw_job(conn, bid, url, {"url": url}, "monitor_rich")
        assert id1 == id2

    def test_get_unparsed_returns_new_rows(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
            record_raw_job(conn, bid, "https://example.com/jobs/a",
                           {"url": "https://example.com/jobs/a", "title": "Eng"}, "monitor_rich")
        with get_conn() as conn:
            rows = get_unparsed_raw_jobs(conn)
        assert len(rows) == 1

    def test_mark_raw_parsed_hides_from_queue(self, tmp_db):
        url = "https://example.com/jobs/b"
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
            raw_id = record_raw_job(conn, bid, url, {"url": url}, "monitor_rich")
            mark_raw_parsed(conn, raw_id, None, None)
        with get_conn() as conn:
            rows = get_unparsed_raw_jobs(conn)
        assert len(rows) == 0

    def test_url_only_in_unscraped_queue(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            # board needs scraper (not skip)
            bid = upsert_board(conn, cid, "acme-sitemap",
                               "https://example.com/sitemap.xml",
                               "sitemap", {}, "json-ld", {})
            url = "https://example.com/jobs/x"
            record_raw_job(conn, bid, url, {"url": url}, "monitor")
        with get_conn() as conn:
            rows = get_unscraped_url_only_raw_jobs(conn)
        assert len(rows) == 1
        assert rows[0]["source_url"] == url

    def test_update_raw_job_payload(self, tmp_db):
        url = "https://example.com/jobs/c"
        new_payload = {"url": url, "title": "New Title", "description": "<p>Hi</p>"}
        with get_conn() as conn:
            cid = upsert_company_from_board(conn, "acme", "Acme Corp", 1, 2)
            bid = _board_id(conn, cid)
            raw_id = record_raw_job(conn, bid, url, {"url": url}, "monitor")
            update_raw_job_payload(conn, raw_id, new_payload, "scraper")
            r = conn.execute(
                "SELECT payload, payload_source FROM raw_jobs WHERE id=?", (raw_id,)
            ).fetchone()
        assert r["payload_source"] == "scraper"
        assert json.loads(r["payload"])["title"] == "New Title"
