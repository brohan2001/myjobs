from __future__ import annotations

from src.api.app import sanitize_description, serialize_job
from src.api.locations import LocationIndex

from .conftest import BLR_ID, SF_ID, make_job_row


def test_basic_shape(index):
    out = serialize_job(make_job_row(0), index)
    assert out["id"] == "00000000-0000-0000-0000-000000000001"
    assert out["company"] == {"slug": "acme", "name": "Acme", "website": "https://acme.test", "logo": None, "type": "product"}
    assert out["locations"] == [{"id": BLR_ID, "name": "Bengaluru, India", "country": "IN", "type": "onsite"}]
    assert out["locations_raw"] == ["Bengaluru"]
    assert out["first_seen_at"] == "2026-01-01T12:00:00+00:00"
    assert out["ats"] == "greenhouse"


def test_remote_entry_with_none_id(index):
    row = make_job_row(location_ids=[None, SF_ID], location_types=["remote", "hybrid"])
    out = serialize_job(row, index)
    assert out["locations"][0] == {"id": None, "name": "Remote", "country": None, "type": "remote"}
    assert out["locations"][1]["country"] == "US"


def test_missing_type_for_location(index):
    out = serialize_job(make_job_row(location_ids=[BLR_ID], location_types=[]), index)
    assert out["locations"][0]["type"] is None


def test_null_locations_lists(index):
    out = serialize_job(make_job_row(location_ids=None, location_types=None, locations_raw=None), index)
    assert out["locations"] == []
    assert out["locations_raw"] == []
    assert out["work_modes"] == []


def test_unloaded_index_gives_null_names():
    out = serialize_job(make_job_row(), LocationIndex())
    assert out["locations"][0]["name"] is None
    assert out["locations"][0]["country"] is None


def test_salary_none_when_both_null(index):
    assert serialize_job(make_job_row(), index)["salary"] is None


def test_salary_present(index):
    row = make_job_row(salary_min=100, salary_max=None, salary_currency="USD", salary_period="year")
    assert serialize_job(row, index)["salary"] == {"min": 100, "max": None, "currency": "USD", "period": "year"}
    row = make_job_row(salary_min=None, salary_max=200)
    assert serialize_job(row, index)["salary"]["max"] == 200


def test_work_modes_deduped_sorted(index):
    row = make_job_row(location_ids=[1, 2, 3, 4], location_types=["remote", "onsite", "remote", "hybrid"])
    assert serialize_job(row, index)["work_modes"] == ["hybrid", "onsite", "remote"]


# --- sanitize_description -------------------------------------------------------


def test_sanitize_none_and_empty():
    assert sanitize_description(None) is None
    assert sanitize_description("") is None


def test_sanitize_strips_dangerous():
    html = (
        '<p onclick="evil()">Hi <b>there</b></p><script>alert(1)</script>'
        '<iframe src="https://evil.test"></iframe><style>p{}</style>'
    )
    out = sanitize_description(html)
    for bad in ("script", "onclick", "iframe", "alert", "<style"):
        assert bad not in out
    assert "<p>Hi <b>there</b></p>" in out


def test_sanitize_keeps_formatting():
    out = sanitize_description("<h2>T</h2><ul><li>a</li><li><em>b</em></li></ul><br>")
    assert "<h2>T</h2>" in out and "<ul>" in out and "<li><em>b</em></li>" in out


def test_sanitize_links_get_rel():
    out = sanitize_description('<a href="https://x.test" target="_blank">x</a>')
    assert 'href="https://x.test"' in out
    assert "noopener" in out and "noreferrer" in out


def test_sanitize_drops_javascript_urls():
    out = sanitize_description('<a href="javascript:alert(1)">x</a>')
    assert "javascript" not in out
