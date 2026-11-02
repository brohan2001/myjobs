"""Lever's createdAt (epoch ms) is the job's publish date (docs/UPSTREAM.md delta 3)."""

from src.core.monitors.lever import _parse_job


def test_created_at_becomes_date_posted():
    job = _parse_job({"hostedUrl": "https://jobs.lever.co/x/1", "text": "SWE", "createdAt": 1792170792681, "categories": {}})
    assert job.date_posted == "2026-10-16T17:13:12.681000+00:00"


def test_missing_created_at_leaves_no_date():
    job = _parse_job({"hostedUrl": "https://jobs.lever.co/x/1", "text": "SWE", "categories": {}})
    assert job.date_posted is None
