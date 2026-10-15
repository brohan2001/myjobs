from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.queries import decode_cursor
from src.config import settings

from .conftest import APAC_ID, BLR_ID, IN_ID, KA_ID, make_job_row

SEC_HEADERS = ["X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options", "Content-Security-Policy"]


# --- /api/v1/jobs ---------------------------------------------------------------


def test_jobs_shape(client, pool):
    pool.fetch_rows = [make_job_row(0), make_job_row(1)]
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body["next_cursor"] is None
    assert [j["title"] for j in body["jobs"]] == ["Engineer 0", "Engineer 1"]
    assert body["jobs"][0]["locations"][0]["name"] == "Bengaluru, India"
    assert r.headers["cache-control"] == "public, max-age=30"
    kind, sql, args = pool.calls[0]
    assert kind == "fetch" and args == (51,)


def test_jobs_next_cursor_when_extra_row(client, pool):
    pool.fetch_rows = [make_job_row(i) for i in range(3)]
    r = client.get("/api/v1/jobs?limit=2")
    body = r.json()
    assert len(body["jobs"]) == 2
    ts, pid = decode_cursor(body["next_cursor"])
    assert pid == UUID(int=2)  # last returned row, not the probe row
    assert ts == datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
    assert pool.calls[0][2][-1] == 3


def test_jobs_cursor_round_trip_into_args(client, pool):
    pool.fetch_rows = [make_job_row(i) for i in range(3)]
    cur = client.get("/api/v1/jobs?limit=2").json()["next_cursor"]
    pool.fetch_rows = []
    assert client.get("/api/v1/jobs", params={"cursor": cur}).status_code == 200
    _, sql, args = pool.calls[-1]
    assert "(jp.first_seen_at, jp.id) <" in sql
    assert args[1] == UUID(int=2)


def test_jobs_country_expands_to_location_ids(client, pool):
    client.get("/api/v1/jobs?country=in")
    _, sql, args = pool.calls[0]
    assert "location_ids && $1::int[]" in sql
    assert BLR_ID in args[0] and IN_ID in args[0] and KA_ID in args[0]


def test_jobs_macro_country(client, pool):
    client.get("/api/v1/jobs?country=APAC")
    assert APAC_ID in pool.calls[0][2][0]
    assert BLR_ID in pool.calls[0][2][0]


def test_jobs_location_param_takes_precedence(client, pool):
    client.get("/api/v1/jobs?location=2&country=US")
    assert set(pool.calls[0][2][0]) == {KA_ID, BLR_ID}


def test_jobs_unknown_country_400(client, pool):
    r = client.get("/api/v1/jobs?country=ZZ")
    assert r.status_code == 400
    assert "ZZ" in r.json()["detail"]
    assert pool.calls == []


def test_jobs_bad_cursor_400(client):
    assert client.get("/api/v1/jobs?cursor=garbage!!").status_code == 400


def test_jobs_bad_since_and_work_mode_400(client):
    assert client.get("/api/v1/jobs?since=never").status_code == 400
    assert client.get("/api/v1/jobs?work_mode=moon").status_code == 400


def test_jobs_limit_validation(client):
    assert client.get("/api/v1/jobs?limit=101").status_code == 422
    assert client.get("/api/v1/jobs?limit=0").status_code == 422
    assert client.get("/api/v1/jobs?limit=100").status_code == 200


def test_jobs_filters_become_bind_args(client, pool):
    client.get("/api/v1/jobs", params={"q": "  go%  ", "company": "acme", "work_mode": "remote",
                                       "seniority": "senior", "occupation": "software", "since": "7d"})
    _, sql, args = pool.calls[0]
    assert "go\\%" not in sql
    assert "%go\\%%" in args
    assert "acme" in args and "remote" in args and "senior" in args and "software" in args


def test_jobs_blank_q_ignored(client, pool):
    client.get("/api/v1/jobs?q=%20%20")
    assert "LIKE" not in pool.calls[0][1]


def test_jobs_sql_injection_param(client, pool):
    client.get("/api/v1/jobs", params={"company": "x'; DROP TABLE job_posting;--"})
    assert "DROP" not in pool.calls[0][1]


# --- /api/v1/jobs/{id} ----------------------------------------------------------


def test_job_404(client, pool):
    pool.fetchrow_row = None
    r = client.get(f"/api/v1/jobs/{UUID(int=5)}")
    assert r.status_code == 404
    assert pool.calls[0][2] == (UUID(int=5),)


def test_job_bad_uuid_422(client):
    assert client.get("/api/v1/jobs/not-a-uuid").status_code == 422


def test_job_detail_sanitized(client, pool):
    pool.fetchrow_row = make_job_row(
        0, is_active=True,
        description_html='<p onclick="x()">Hello</p><script>alert(1)</script><a href="https://a.test">l</a>',
    )
    r = client.get(f"/api/v1/jobs/{UUID(int=1)}")
    assert r.status_code == 200
    body = r.json()
    assert body["is_active"] is True
    assert "script" not in body["description_html"]
    assert "onclick" not in body["description_html"]
    assert "Hello" in body["description_html"]
    assert "noopener" in body["description_html"]
    assert r.headers["cache-control"] == "public, max-age=300"


def test_job_detail_no_description(client, pool):
    pool.fetchrow_row = make_job_row(0, is_active=False, description_html=None)
    body = client.get(f"/api/v1/jobs/{UUID(int=1)}").json()
    assert body["description_html"] is None and body["is_active"] is False


# --- companies / locations / stats ---------------------------------------------


def test_companies(client, pool):
    pool.fetch_rows = [{
        "slug": "acme", "name": "Acme", "website": "https://acme.test", "logo": None,
        "active_jobs": 7, "latest_job_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }]
    r = client.get("/api/v1/companies?q=Ac_me&limit=5")
    assert r.status_code == 200
    assert r.json()["companies"] == [{
        "slug": "acme", "name": "Acme", "website": "https://acme.test", "logo": None,
        "active_jobs": 7, "latest_job_at": "2026-01-01T00:00:00+00:00",
    }]
    assert pool.calls[0][2] == ("%ac\\_me%", 5)


def test_companies_limit_validation(client):
    assert client.get("/api/v1/companies?limit=501").status_code == 422


def test_locations_search(client):
    r = client.get("/api/v1/locations?q=ben")
    assert r.status_code == 200
    assert r.json() == {"locations": [{"id": BLR_ID, "name": "Bengaluru, India", "type": "city", "code": None}]}


def test_locations_search_country_has_code(client):
    locs = client.get("/api/v1/locations?q=in").json()["locations"]
    assert locs == [{"id": IN_ID, "name": "India", "type": "country", "code": "IN"}]
    macro = client.get("/api/v1/locations?q=asia").json()["locations"][0]
    assert macro["code"] == "APAC" and macro["type"] == "macro"


def test_locations_requires_q(client):
    assert client.get("/api/v1/locations").status_code == 422
    assert client.get("/api/v1/locations?q=").status_code == 422


def test_stats(client, pool):
    pool.fetchrow_row = {
        "active_jobs": 10, "new_last_24h": 2, "companies_hiring": 3, "boards_enabled": 4,
        "boards_fresh_24h": 3, "boards_failing": 1,
        "last_updated": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    assert r.json()["active_jobs"] == 10
    assert r.json()["last_updated"] == "2026-01-01T00:00:00+00:00"


def test_stats_null_last_updated(client, pool):
    pool.fetchrow_row = {"active_jobs": 0, "last_updated": None}
    assert client.get("/api/v1/stats").json()["last_updated"] is None


# --- rate limit, headers, healthz, CORS ----------------------------------------


def test_rate_limit_429(make_client, pool):
    pool.fetchrow_row = {"last_updated": None}
    c = make_client(limit=2)
    assert c.get("/api/v1/stats").status_code != 429
    assert c.get("/api/v1/stats").status_code != 429
    r = c.get("/api/v1/stats")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert "Too many" in r.json()["detail"]
    for h in SEC_HEADERS:
        assert h in r.headers


def test_rate_limit_only_applies_to_api(make_client):
    c = make_client(limit=1)
    for _ in range(3):
        assert c.get("/healthz").status_code == 200


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}
    for h in SEC_HEADERS:
        assert h in r.headers


def test_security_headers_on_api_and_errors(client, pool):
    for path in ("/api/v1/jobs", "/api/v1/jobs?limit=500", "/api/v1/jobs?country=ZZ"):
        r = client.get(path)
        for h in SEC_HEADERS:
            assert h in r.headers, (path, h)
    r = client.get("/api/v1/jobs")
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_no_cors_by_default(client, pool):
    pool.fetchrow_row = {"last_updated": None}
    r = client.get("/api/v1/stats", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allowed_origin(monkeypatch, make_client, pool):
    monkeypatch.setattr(settings, "api_cors_origins", "https://good.test, https://other.test")
    c = make_client(app=create_app(use_lifespan=False))
    pool.fetchrow_row = {"last_updated": None}
    r = c.get("/api/v1/stats", headers={"Origin": "https://good.test"})
    assert r.headers["access-control-allow-origin"] == "https://good.test"
    r = c.get("/api/v1/stats", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_unset_after_patch_restored(client):
    assert settings.api_cors_origins == ""


def test_coverage_endpoint_shape(monkeypatch):
    from datetime import datetime, timezone

    from fastapi.testclient import TestClient

    from src.api import app as app_mod
    from src.api import queries

    async def fake_coverage(pool):
        return {
            "by_ats": [{"ats": "greenhouse", "boards": 10, "healthy": 9, "failing": 1, "gone": 2,
                        "last_success_at": datetime(2026, 10, 11, tzinfo=timezone.utc)}],
            "by_country": [{"country": "IN", "companies": 5, "companies_hiring": 4}],
            "india_by_city": [{"city": "Bengaluru", "companies": 3}],
        }

    monkeypatch.setattr(queries, "fetch_coverage", fake_coverage)
    application = app_mod.create_app(use_lifespan=False)
    application.state.pool = object()
    with TestClient(application) as client:
        body = client.get("/api/v1/coverage").json()
    assert body["by_ats"][0]["last_success_at"] == "2026-10-11T00:00:00+00:00"
    assert body["india_by_city"][0]["city"] == "Bengaluru"


def test_jobs_company_type_filter(client, pool):
    assert client.get("/api/v1/jobs?company_type=startup,%20gcc").status_code == 200
    _, sql, args = pool.calls[0]
    assert ["startup", "gcc"] in args
    assert client.get("/api/v1/jobs?company_type=moon").status_code == 400


def test_job_includes_company_type(client, pool):
    pool.fetch_rows = [make_job_row(0)]
    body = client.get("/api/v1/jobs").json()
    assert body["jobs"][0]["company"]["type"] == "product"

