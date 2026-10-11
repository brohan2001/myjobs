from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from src.api.queries import (
    MAX_LIMIT,
    InvalidFilter,
    JobFilters,
    build_jobs_query,
    decode_cursor,
    encode_cursor,
    parse_since,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_default_query():
    sql, args = build_jobs_query(JobFilters())
    assert "WHERE jp.is_active\n" in sql
    assert "ORDER BY jp.first_seen_at DESC, jp.id DESC" in sql
    assert sql.rstrip().endswith("LIMIT $1")
    assert args == [51]


def test_q_filter_bind_and_like_escape():
    sql, args = build_jobs_query(JobFilters(q="100%_Fun\\Co"))
    assert "lower(jp.titles[1]) LIKE $1 OR lower(c.name) LIKE $1" in sql
    assert args[0] == "%100\\%\\_fun\\\\co%"
    assert "Fun" not in sql


def test_q_lowercased_and_wrapped():
    _, args = build_jobs_query(JobFilters(q="Python"))
    assert args[0] == "%python%"


def test_location_ids_filter():
    sql, args = build_jobs_query(JobFilters(location_ids=(1, 2, 3)))
    assert "jp.location_ids && $1::int[]" in sql
    assert args[0] == [1, 2, 3]


def test_empty_location_ids_still_filters():
    sql, args = build_jobs_query(JobFilters(location_ids=()))
    assert "jp.location_ids && $1::int[]" in sql
    assert args[0] == []


def test_company_filter():
    sql, args = build_jobs_query(JobFilters(company="acme"))
    assert "c.slug = $1" in sql
    assert args[0] == "acme"


@pytest.mark.parametrize("mode", ["remote", "hybrid", "onsite"])
def test_work_mode_valid(mode):
    sql, args = build_jobs_query(JobFilters(work_mode=mode))
    assert "$1 = ANY(jp.location_types)" in sql
    assert args[0] == mode


@pytest.mark.parametrize("mode", ["Remote", "home", "remote; DROP TABLE job_posting"])
def test_work_mode_invalid(mode):
    with pytest.raises(InvalidFilter):
        build_jobs_query(JobFilters(work_mode=mode))


def test_since_filter():
    sql, args = build_jobs_query(JobFilters(since=NOW))
    assert "jp.first_seen_at >= $1" in sql
    assert args[0] == NOW


def test_seniority_filter():
    sql, args = build_jobs_query(JobFilters(seniority="senior"))
    assert "jp.seniority_id = (SELECT id FROM seniority WHERE slug = $1)" in sql
    assert args == ["senior", 51]


def test_occupation_filter_reuses_one_placeholder():
    sql, args = build_jobs_query(JobFilters(occupation="software"))
    assert "slug = $1 OR parent_id = (SELECT id FROM occupation WHERE slug = $1)" in sql
    assert args == ["software", 51]


def test_cursor_filter():
    pid = uuid4()
    sql, args = build_jobs_query(JobFilters(cursor=(NOW, pid)))
    assert "(jp.first_seen_at, jp.id) < ($1, $2)" in sql
    assert args[:2] == [NOW, pid]


def test_all_filters_placeholders_sequential():
    pid = uuid4()
    f = JobFilters(q="x", location_ids=(1,), company="c", work_mode="remote", since=NOW,
                   seniority="s", occupation="o", cursor=(NOW, pid), limit=10)
    sql, args = build_jobs_query(f)
    # q, loc, company, mode, since, seniority, occupation, cursor ts, cursor id, limit
    assert len(args) == 10
    for i in range(1, 11):
        assert f"${i}" in sql
    assert "$11" not in sql
    assert args[-1] == 11


@pytest.mark.parametrize("limit,expected", [(1, 2), (50, 51), (100, 101), (1000, MAX_LIMIT + 1), (0, 2), (-5, 2)])
def test_limit_plus_one_capped(limit, expected):
    _, args = build_jobs_query(JobFilters(limit=limit))
    assert args[-1] == expected


INJECTIONS = ["'; DROP TABLE job_posting; --", "\" OR 1=1 --", "x') UNION SELECT 1 --"]


@pytest.mark.parametrize("payload", INJECTIONS)
def test_injection_stays_in_args(payload):
    f = JobFilters(q=payload, company=payload, seniority=payload, occupation=payload)
    sql, args = build_jobs_query(f)
    assert "DROP" not in sql and "UNION" not in sql and "1=1" not in sql
    assert any(payload.lower() in str(a).lower() for a in args)
    assert payload in args  # company/seniority bound verbatim


# --- parse_since --------------------------------------------------------------


def test_parse_since_none_and_empty():
    assert parse_since(None) is None
    assert parse_since("") is None


def test_parse_since_hours_days():
    assert parse_since("24h", now=NOW) == NOW - timedelta(hours=24)
    assert parse_since("7d", now=NOW) == NOW - timedelta(days=7)
    assert parse_since(" 7D ", now=NOW) == NOW - timedelta(days=7)


def test_parse_since_default_now_is_aware():
    out = parse_since("1h")
    assert out.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - out) - timedelta(hours=1)) < timedelta(seconds=5)


def test_parse_since_iso_with_tz():
    out = parse_since("2026-01-02T03:04:05+05:30")
    assert out.utcoffset() == timedelta(hours=5, minutes=30)


def test_parse_since_iso_naive_becomes_utc():
    out = parse_since("2026-01-02T03:04:05")
    assert out == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@pytest.mark.parametrize("bad", ["yesterday", "24", "h", "7w", "1000h", "-1d", "2026-13-45", "'; DROP"])
def test_parse_since_garbage(bad):
    with pytest.raises(InvalidFilter):
        parse_since(bad)


# --- cursors ------------------------------------------------------------------


def test_cursor_round_trip():
    ts = datetime(2026, 3, 4, 5, 6, 7, 123456, tzinfo=timezone.utc)
    pid = uuid4()
    token = encode_cursor(ts, pid)
    assert "=" not in token
    assert decode_cursor(token) == (ts, pid)


def test_cursor_accepts_str_id():
    pid = uuid4()
    assert decode_cursor(encode_cursor(NOW, str(pid)))[1] == pid


def test_cursor_empty_is_none():
    assert decode_cursor(None) is None
    assert decode_cursor("") is None


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


@pytest.mark.parametrize("bad", [
    "!!!notbase64",
    "abc",
    base64.urlsafe_b64encode(b"not json").decode(),
    _b64({"a": 1}),
    _b64([1]),
    _b64(["2026-01-01T00:00:00+00:00"]),
    _b64(["garbage", str(UUID(int=1))]),
    _b64(["2026-01-01T00:00:00+00:00", "not-a-uuid"]),
    _b64([None, None]),
    "éééé",
])
def test_cursor_garbage(bad):
    with pytest.raises(InvalidFilter):
        decode_cursor(bad)


def test_cursor_tampered():
    token = encode_cursor(NOW, uuid4())
    tampered = token[:-4] + "AAAA"
    with pytest.raises(InvalidFilter):
        decode_cursor(tampered)


@pytest.mark.xfail(strict=True, reason="decode_cursor: UUID(<int>) raises AttributeError, not caught -> HTTP 500 instead of 400 (queries.py:68-69)")
def test_cursor_non_string_uuid_is_invalid_filter():
    with pytest.raises(InvalidFilter):
        decode_cursor(_b64(["2026-01-01T00:00:00+00:00", 5]))
