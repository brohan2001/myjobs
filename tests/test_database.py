from __future__ import annotations

import pytest

import src.database as db_module
from src.database import (
    get_conn,
    get_existing_keys,
    get_shortlist,
    get_top_unshortlisted,
    init_db,
    insert_jobs,
    mark_shortlisted,
    upsert_company,
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
