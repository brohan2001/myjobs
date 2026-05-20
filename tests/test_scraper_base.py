"""Deduplication tests for the new pipeline's existing-keys check.

The old BaseScraper.deduplicate() is gone; dedup now happens in pipeline.py by
consulting the `existing_keys` set (pulled from the jobs table) before calling
insert_jobs(). These tests verify that logic directly.
"""
from __future__ import annotations

import src.database as db_module
from src.database import get_conn, get_existing_keys, init_db, insert_jobs, upsert_company

import pytest


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    init_db()
    return db_file


def _company():
    return {
        "name": "Acme", "slug": "acme", "ats_type": "greenhouse",
        "domain": "acme.com", "industry": "tech", "tier": 1,
    }


def _job(cid: int, ext_id: str, url_suffix: str | None = None) -> dict:
    return {
        "external_id":  ext_id,
        "company_id":   cid,
        "title":        "Engineer",
        "description":  None,
        "location":     "Remote",
        "remote":       1,
        "url":          f"https://example.com/jobs/{url_suffix or ext_id}",
        "posted_date":  None,
        "posted_at":    None,
        "ats_type":     "greenhouse",
    }


def _dedup(jobs: list[dict], existing: set) -> list[dict]:
    """Replicate the pipeline's dedup step: skip jobs whose key is in existing."""
    seen: set = set()
    out: list[dict] = []
    for j in jobs:
        key = (j["external_id"], j["ats_type"])
        if key in existing or key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


class TestDedup:
    def test_all_new_returns_all(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
        jobs = [_job(cid, "1"), _job(cid, "2"), _job(cid, "3")]
        result = _dedup(jobs, existing=set())
        assert len(result) == 3

    def test_all_existing_returns_empty(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "1"), _job(cid, "2")])
            existing = get_existing_keys(conn)
        jobs = [_job(cid, "1"), _job(cid, "2")]
        result = _dedup(jobs, existing)
        assert result == []

    def test_mixed_returns_only_new(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
            insert_jobs(conn, [_job(cid, "1")])
            existing = get_existing_keys(conn)
        jobs = [_job(cid, "1"), _job(cid, "2"), _job(cid, "3")]
        result = _dedup(jobs, existing)
        assert len(result) == 2
        assert all(j["external_id"] != "1" for j in result)

    def test_intra_batch_duplicates_deduplicated(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
        jobs = [_job(cid, "1", "1a"), _job(cid, "1", "1b"), _job(cid, "2")]
        result = _dedup(jobs, existing=set())
        assert len(result) == 2

    def test_same_external_id_different_ats_not_deduped(self, tmp_db):
        with get_conn() as conn:
            cid = upsert_company(conn, _company())
        jobs = [
            {**_job(cid, "1"), "ats_type": "greenhouse"},
            {**_job(cid, "1"), "ats_type": "lever", "url": "https://lever.co/jobs/1"},
        ]
        result = _dedup(jobs, existing=set())
        assert len(result) == 2

    def test_empty_jobs_returns_empty(self, tmp_db):
        result = _dedup([], existing=set())
        assert result == []
